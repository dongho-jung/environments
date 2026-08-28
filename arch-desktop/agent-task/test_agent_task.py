from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


SCRIPT = Path(__file__).with_name("agent_task.py")
STATUSLINE_SCRIPT = Path(__file__).with_name("agent_statusline.py")
STATUSLINE_SPEC = importlib.util.spec_from_file_location("agent_statusline_under_test", STATUSLINE_SCRIPT)
assert STATUSLINE_SPEC and STATUSLINE_SPEC.loader
STATUSLINE = importlib.util.module_from_spec(STATUSLINE_SPEC)
STATUSLINE_SPEC.loader.exec_module(STATUSLINE)
SPEC = importlib.util.spec_from_file_location("agent_task_under_test", SCRIPT)
assert SPEC and SPEC.loader
AGENT_TASK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AGENT_TASK)


class LaunchBehaviorTest(unittest.TestCase):
    def test_agent_process_runs_directly_in_the_task_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            worktree = Path(directory)
            nested = worktree / "nested"
            nested.mkdir()
            task = {
                "task_id": "test-task",
                "worktree_path": str(worktree),
                "workdir_relative": "nested",
                "branch": "ai/codex/test-task",
                "target_branch": "main",
            }
            process = mock.Mock(pid=12345)
            process.wait.return_value = 0
            store = mock.Mock()

            with (
                mock.patch.object(AGENT_TASK.subprocess, "Popen", return_value=process) as popen,
                mock.patch.object(AGENT_TASK, "process_start", return_value="start"),
            ):
                exit_code = AGENT_TASK.launch_agent(store, task, ["custom-agent", "instruction"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(popen.call_args.args[0], ["custom-agent", "instruction"])
        self.assertEqual(popen.call_args.kwargs["cwd"], nested)
        self.assertEqual(popen.call_args.kwargs["env"]["AI_TASK_WORKTREE"], str(worktree))
        self.assertEqual(popen.call_args.kwargs["env"]["AI_TASK_WORKDIR"], str(nested))

    def test_interactive_codex_keeps_the_original_session_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            origin = root / "original" / "nested"
            worktree = root / "worktree"
            task_directory = worktree / "nested"
            origin.mkdir(parents=True)
            task_directory.mkdir(parents=True)
            task = {
                "task_id": "stable-history",
                "worktree_path": str(worktree),
                "workdir_relative": "nested",
                "origin_working_directory": str(origin),
                "branch": "ai/codex/stable-history",
                "target_branch": "main",
                "agent": "codex",
            }
            process = mock.Mock(pid=12345)
            process.wait.return_value = 0
            store = mock.Mock()

            with (
                mock.patch.object(AGENT_TASK.subprocess, "Popen", return_value=process) as popen,
                mock.patch.object(AGENT_TASK, "process_start", return_value="start"),
            ):
                exit_code = AGENT_TASK.launch_agent(
                    store,
                    task,
                    ["codex", "--dangerously-bypass-approvals-and-sandbox"],
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(popen.call_args.kwargs["cwd"], origin)
        self.assertEqual(
            popen.call_args.args[0][:3],
            ["codex", "--add-dir", str(worktree)],
        )
        self.assertEqual(popen.call_args.kwargs["env"]["AI_TASK_WORKDIR"], str(task_directory))

    def test_legacy_codex_task_keeps_its_managed_worktree_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            worktree = Path(directory)
            task = {
                "worktree_path": str(worktree),
                "workdir_relative": ".",
            }

            selected = AGENT_TASK.managed_agent_working_directory(task, ["codex"])

        self.assertEqual(selected, worktree.resolve())

    def test_interactive_codex_sigint_is_recorded_as_graceful(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            task = {
                "task_id": "codex-sigint",
                "worktree_path": directory,
                "workdir_relative": ".",
                "branch": "ai/codex/codex-sigint",
                "target_branch": "main",
                "agent": "codex",
            }
            process = mock.Mock(pid=12345)
            process.wait.return_value = AGENT_TASK.SHELL_SIGINT_EXIT_CODE
            store = mock.Mock()

            with (
                mock.patch.object(AGENT_TASK.subprocess, "Popen", return_value=process),
                mock.patch.object(AGENT_TASK, "process_start", return_value="start"),
            ):
                exit_code = AGENT_TASK.launch_agent(
                    store,
                    task,
                    ["codex", "--dangerously-bypass-approvals-and-sandbox", "work here"],
                )

        self.assertEqual(exit_code, 130)
        self.assertEqual(task["agent_exit_code"], 130)
        self.assertIs(task["agent_exit_graceful"], True)
        self.assertFalse(AGENT_TASK.agent_exit_failed(task))

    def test_sigint_is_not_graceful_for_noninteractive_or_non_codex_commands(self) -> None:
        exit_code = AGENT_TASK.SHELL_SIGINT_EXIT_CODE

        self.assertTrue(AGENT_TASK.graceful_codex_interrupt("codex", ["codex"], exit_code))
        self.assertTrue(
            AGENT_TASK.graceful_codex_interrupt("codex", ["codex", "resume", "--last"], exit_code)
        )
        self.assertTrue(AGENT_TASK.graceful_codex_interrupt("codex", ["codex", "fork"], exit_code))
        self.assertFalse(
            AGENT_TASK.graceful_codex_interrupt("codex", ["codex", "exec", "echo", "done"], exit_code)
        )
        self.assertFalse(AGENT_TASK.graceful_codex_interrupt("custom", ["codex"], exit_code))
        self.assertFalse(AGENT_TASK.graceful_codex_interrupt("claude", ["claude"], exit_code))
        self.assertFalse(AGENT_TASK.graceful_codex_interrupt("codex", ["codex"], 1))

        task = {"agent_exit_code": 1, "agent_exit_graceful": True}
        self.assertTrue(AGENT_TASK.agent_exit_failed(task))
        AGENT_TASK.record_agent_exit(task, 1)
        self.assertNotIn("agent_exit_graceful", task)

    def test_graceful_codex_sigint_completes_a_clean_unchanged_task(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "worktrees"
            worktree = root / "repo-id" / "codex-sigint"
            worktree.mkdir(parents=True)
            store = mock.Mock(worktrees=root)
            task = {
                "task_id": "codex-sigint",
                "worktree_path": str(worktree),
                "repository": str(Path(directory) / "repo"),
                "branch": "ai/codex/codex-sigint",
                "base_sha": "base",
                "agent_exit_code": AGENT_TASK.SHELL_SIGINT_EXIT_CODE,
                "agent_exit_graceful": True,
            }
            branch = mock.Mock(stdout=f"{task['branch']}\n")

            with (
                mock.patch.object(AGENT_TASK, "worktree_changes", return_value=([], [])),
                mock.patch.object(AGENT_TASK, "git", return_value=branch),
                mock.patch.object(AGENT_TASK, "current_head", return_value="base"),
                mock.patch.object(AGENT_TASK, "capture_memory_proposal"),
                mock.patch.object(AGENT_TASK, "apply_memory_update"),
                mock.patch.object(AGENT_TASK, "cleanup_task", return_value=True) as cleanup,
            ):
                AGENT_TASK.inspect_result(store, task)

        self.assertEqual(task["status"], AGENT_TASK.COMPLETED)
        cleanup.assert_called_once_with(store, task)

    def test_graceful_parent_sigint_is_propagated_to_attachments(self) -> None:
        attachment = {
            "task_id": "attachment",
            "status": AGENT_TASK.RUNNING,
            "created_at": "2026-08-26T00:00:00+09:00",
            "attachment_session_id": "session",
            "auto_integrate": True,
        }
        store = mock.Mock()
        store.all.return_value = [attachment]
        store.load.return_value = attachment
        store.lock.return_value = contextlib.nullcontext()

        with (
            mock.patch.object(AGENT_TASK, "finalize_task") as finalize,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            AGENT_TASK.finalize_session_attachments(
                store,
                "session",
                AGENT_TASK.SHELL_SIGINT_EXIT_CODE,
                graceful=True,
            )

        self.assertEqual(attachment["agent_exit_code"], 130)
        self.assertIs(attachment["agent_exit_graceful"], True)
        finalize.assert_called_once_with(store, attachment, integrate=True)

    def test_agent_spawn_failure_does_not_leave_launcher_marked_active(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            task = {
                "task_id": "failed-launch",
                "worktree_path": directory,
                "workdir_relative": ".",
                "branch": "ai/custom/failed-launch",
                "target_branch": "main",
                "process": {
                    "pid": os.getpid(),
                    "start": AGENT_TASK.process_start(os.getpid()),
                    "role": "launcher",
                },
            }
            store = mock.Mock()

            with mock.patch.object(AGENT_TASK.subprocess, "Popen", side_effect=OSError("spawn failed")):
                with self.assertRaisesRegex(AGENT_TASK.AgentTaskError, "cannot launch coding agent"):
                    AGENT_TASK.launch_agent(store, task, ["custom-agent"])

            self.assertNotIn("process", task)
            store.save.assert_called()

    def test_launchers_follow_repository_checkout_policy(self) -> None:
        configuration = SCRIPT.parent.parent.joinpath("agent-task.tf").read_text()
        claude_settings = json.loads(SCRIPT.parent.parent.joinpath("claude/settings.json").read_text())

        self.assertIn('if [[ "$${1-}" == "--local" ]]', configuration)
        self.assertIn('if [[ "$${1-}" == "resume" ]]', configuration)
        self.assertIn('if [[ "$${1-}" == "--new" ]]', configuration)
        self.assertIn('if [[ "$${1-}" == "--task" ]]', configuration)
        self.assertIn("agent-task open --auto --agent codex", configuration)
        self.assertIn("agent-task open --managed --new --agent codex", configuration)
        self.assertIn("agent-task resume --agent codex", configuration)
        self.assertIn("agent-task open --auto --agent claude", configuration)
        self.assertIn("agent-task open --managed --new --agent claude", configuration)
        self.assertIn("agent-task open --auto --agent codex -- codex", configuration)
        self.assertIn("agent-task open --auto --agent claude -- env", configuration)
        self.assertIn("agent-task open --auto --fresh --agent codex", configuration)
        self.assertIn("exec|e|apply|a|fork|cloud|cloud-tasks|sandbox", configuration)
        self.assertIn("--require-current", configuration)
        self.assertIn("agent-task resume --agent codex --", configuration)
        self.assertIn("review|resume|apply", configuration)
        self.assertIn("agents|attach|logs|stop|rm)", configuration)
        self.assertIn("claude_owns_lifecycle", configuration)
        self.assertNotIn("require explicit c --local", configuration)
        self.assertIn('command codex --dangerously-bypass-approvals-and-sandbox "$@"', configuration)
        self.assertIn('command env IS_DEMO=1 claude', configuration)
        self.assertNotIn('resource "host_package_pacman" "bubblewrap"', configuration)
        self.assertIn('name = "python-websockets"', configuration)
        self.assertEqual(
            claude_settings["hooks"]["Stop"][0]["hooks"][0]["command"],
            "agent-task __inbox-hook",
        )
        self.assertEqual(
            claude_settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"],
            "agent-task __inbox-hook",
        )
        self.assertEqual(claude_settings["statusLine"]["command"], "agent_statusline.py --claude")
        self.assertEqual(claude_settings["statusLine"]["refreshInterval"], 1)
        self.assertIn('source       = "agent-task/agent_statusline.py"', configuration)
        self.assertEqual(
            AGENT_TASK.CODEX_STATUS_LINE_CONFIG,
            'tui.status_line=["thread-title","model-with-reasoning","task-progress"]',
        )
        self.assertIn('"thread/name/set"', SCRIPT.read_text())
        kitty_configuration = SCRIPT.parent.parent.joinpath("kitty/kitty.conf").read_text()
        self.assertNotIn("tab_bar_min_tabs 1", kitty_configuration)
        self.assertNotIn('tab_title_template " {title} "', kitty_configuration)
        self.assertNotIn("tui.terminal_title", SCRIPT.read_text())

    def test_repository_memory_accepts_only_durable_checkout_modes(self) -> None:
        memory = AGENT_TASK.memory_template("main")
        for mode in AGENT_TASK.AGENT_TASK_MODES:
            memory["settings"]["agent_task_mode"] = mode
            self.assertIs(AGENT_TASK.validate_memory(memory), memory)

        memory["settings"]["agent_task_mode"] = "sometimes"
        with self.assertRaisesRegex(AGENT_TASK.AgentTaskError, "agent_task_mode"):
            AGENT_TASK.validate_memory(memory)

    def test_codex_notification_starts_an_idle_remote_tui_thread(self) -> None:
        class FakeSocket:
            def __init__(self) -> None:
                self.responses: list[str] = []
                self.requests: list[dict[str, object]] = []

            async def send(self, raw: str) -> None:
                request = json.loads(raw)
                self.requests.append(request)
                if "id" not in request:
                    return
                remote_tui = {
                    "id": "thread-1",
                    "cwd": "/repo",
                    "source": "vscode",
                    "status": {"type": "idle"},
                }
                source_kinds = request.get("params", {}).get("sourceKinds")
                thread_data = [
                    {"id": "stored-thread", "cwd": "/repo", "status": {"type": "notLoaded"}},
                ]
                if not source_kinds or remote_tui["source"] in source_kinds:
                    thread_data.append(remote_tui)
                results = {
                    "initialize": {},
                    "thread/list": {"data": thread_data},
                    "turn/start": {"turn": {"id": "turn-1"}},
                }
                self.responses.append(json.dumps({"id": request["id"], "result": results[request["method"]]}))

            async def recv(self) -> str:
                return self.responses.pop(0)

        class FakeConnection:
            def __init__(self, socket: FakeSocket) -> None:
                self.socket = socket

            async def __aenter__(self) -> FakeSocket:
                return self.socket

            async def __aexit__(self, *_args: object) -> None:
                return None

        socket = FakeSocket()
        AGENT_TASK.deliver_codex_prompt(
            Path("/control.sock"),
            Path("/repo"),
            "handoff now",
            connector=lambda: FakeConnection(socket),
        )

        methods = [request.get("method") for request in socket.requests]
        self.assertEqual(methods, ["initialize", "initialized", "thread/list", "turn/start"])
        thread_list = next(request for request in socket.requests if request.get("method") == "thread/list")
        self.assertEqual(thread_list["params"], {"cwd": "/repo"})
        turn_start = next(request for request in socket.requests if request.get("method") == "turn/start")
        self.assertEqual(turn_start["params"]["threadId"], "thread-1")
        self.assertEqual(turn_start["params"]["input"][0]["text"], "handoff now")

    def test_interactive_codex_uses_its_session_app_server(self) -> None:
        socket = Path("/state/controls/session.sock")

        opened = AGENT_TASK.codex_remote_command(
            ["codex", "--dangerously-bypass-approvals-and-sandbox", "work here"],
            socket,
        )
        resumed = AGENT_TASK.codex_remote_command(["codex", "resume", "--last"], socket)
        review = AGENT_TASK.codex_remote_command(["codex", "review", "--uncommitted"], socket)

        prefix = [
            "codex",
            "--remote",
            f"unix://{socket}",
            "-c",
            AGENT_TASK.CODEX_STATUS_LINE_CONFIG,
        ]
        self.assertEqual(opened[:5], prefix)
        self.assertEqual(resumed[:6], [*prefix, "resume"])
        self.assertIsNone(review)

    def test_codex_statusline_decorates_an_auto_title_after_it_exists(self) -> None:
        statusline = (
            "WT#17 · ai/codex/20260828-150920-7fb1e6 · "
            ".../projects/environments/arch-desktop · CAPE-456"
        )
        self.assertIsNone(AGENT_TASK.codex_statusline_thread_title(statusline, None))
        self.assertEqual(
            AGENT_TASK.codex_statusline_thread_title(
                statusline,
                "WT | *codex/backend@21:31[CAPE-123] :: Investigate ordering",
            ),
            f"{statusline} :: Investigate ordering",
        )

        class FakeSocket:
            def __init__(self, name: str | None) -> None:
                self.name = name
                self.responses: list[str] = []
                self.requests: list[dict[str, object]] = []

            async def send(self, raw: str) -> None:
                request = json.loads(raw)
                self.requests.append(request)
                if "id" not in request:
                    return
                method = request["method"]
                if method == "initialize":
                    result: object = {}
                elif method == "thread/loaded/list":
                    result = {"data": ["current"]}
                elif method == "thread/list":
                    result = {
                        "data": [
                            {
                                "id": "current",
                                "cwd": "/repo",
                                "source": "vscode",
                                "status": {"type": "idle"},
                                "recencyAt": 2,
                                "name": self.name,
                            }
                        ]
                    }
                elif method == "thread/name/set":
                    result = {}
                else:
                    raise AssertionError(method)
                self.responses.append(json.dumps({"id": request["id"], "result": result}))

            async def recv(self) -> str:
                return self.responses.pop(0)

        class FakeConnection:
            def __init__(self, socket: FakeSocket) -> None:
                self.socket = socket

            async def __aenter__(self) -> FakeSocket:
                return self.socket

            async def __aexit__(self, *_args: object) -> None:
                return None

        titled = FakeSocket("Investigate ordering")
        thread_id = AGENT_TASK.refresh_codex_statusline(
            Path("/control.sock"),
            Path("/repo"),
            statusline,
            connector=lambda: FakeConnection(titled),
        )
        self.assertEqual(thread_id, "current")
        renamed = next(
            request for request in titled.requests if request.get("method") == "thread/name/set"
        )
        self.assertEqual(
            renamed["params"],
            {"threadId": "current", "name": f"{statusline} :: Investigate ordering"},
        )

        untitled = FakeSocket(None)
        self.assertEqual(
            AGENT_TASK.refresh_codex_statusline(
                Path("/control.sock"),
                Path("/repo"),
                statusline,
                connector=lambda: FakeConnection(untitled),
            ),
            "current",
        )
        self.assertNotIn("thread/name/set", [request.get("method") for request in untitled.requests])

    def test_codex_recovery_resumes_only_an_exact_worktree_thread(self) -> None:
        class FakeSocket:
            def __init__(self) -> None:
                self.responses: list[str] = []
                self.requests: list[dict[str, object]] = []

            async def send(self, raw: str) -> None:
                request = json.loads(raw)
                self.requests.append(request)
                if "id" not in request:
                    return
                results = {
                    "initialize": {},
                    "thread/list": {
                        "data": [
                            {
                                "id": "worktree-thread",
                                "cwd": "/repo/worktree",
                                "status": {"type": "notLoaded"},
                            }
                        ]
                    },
                }
                self.responses.append(
                    json.dumps({"id": request["id"], "result": results[request["method"]]})
                )

            async def recv(self) -> str:
                return self.responses.pop(0)

        class FakeConnection:
            def __init__(self, socket: FakeSocket) -> None:
                self.socket = socket

            async def __aenter__(self) -> FakeSocket:
                return self.socket

            async def __aexit__(self, *_args: object) -> None:
                return None

        socket = FakeSocket()
        thread_id = AGENT_TASK.latest_codex_thread_id(
            Path("/control.sock"),
            Path("/repo/worktree"),
            connector=lambda: FakeConnection(socket),
        )

        self.assertEqual(thread_id, "worktree-thread")
        listed = next(request for request in socket.requests if request.get("method") == "thread/list")
        self.assertEqual(
            listed["params"],
            {
                "cwd": "/repo/worktree",
                "limit": 1,
                "sortKey": "recency_at",
                "sortDirection": "desc",
                "useStateDbOnly": True,
            },
        )

    def test_codex_recovery_starts_fresh_when_worktree_has_no_thread(self) -> None:
        recovery = AGENT_TASK.mark_codex_recovery_command(
            [
                "codex",
                "resume",
                "--last",
                "--dangerously-bypass-approvals-and-sandbox",
                "recover this task",
            ],
            Path("/repo/worktree"),
        )
        unmarked, working_directory = AGENT_TASK.unmark_codex_recovery_command(recovery)

        self.assertEqual(working_directory, Path("/repo/worktree"))
        self.assertEqual(
            AGENT_TASK.resolve_codex_recovery_command(unmarked, "thread-1"),
            [
                "codex",
                "resume",
                "thread-1",
                "--dangerously-bypass-approvals-and-sandbox",
                "recover this task",
            ],
        )
        self.assertEqual(
            AGENT_TASK.resolve_codex_recovery_command(unmarked, None),
            [
                "codex",
                "--dangerously-bypass-approvals-and-sandbox",
                "recover this task",
            ],
        )

    def test_codex_notification_steers_an_active_turn(self) -> None:
        class FakeSocket:
            def __init__(self) -> None:
                self.responses: list[str] = []
                self.requests: list[dict[str, object]] = []

            async def send(self, raw: str) -> None:
                request = json.loads(raw)
                self.requests.append(request)
                if "id" not in request:
                    return
                results = {
                    "initialize": {},
                    "thread/list": {
                        "data": [{"id": "thread-1", "cwd": "/repo", "status": {"type": "active"}}]
                    },
                    "thread/read": {
                        "thread": {"turns": [{"id": "turn-active", "status": "inProgress"}]}
                    },
                    "turn/steer": {"turnId": "turn-active"},
                }
                self.responses.append(json.dumps({"id": request["id"], "result": results[request["method"]]}))

            async def recv(self) -> str:
                return self.responses.pop(0)

        class FakeConnection:
            def __init__(self, socket: FakeSocket) -> None:
                self.socket = socket

            async def __aenter__(self) -> FakeSocket:
                return self.socket

            async def __aexit__(self, *_args: object) -> None:
                return None

        socket = FakeSocket()
        AGENT_TASK.deliver_codex_prompt(
            Path("/control.sock"),
            Path("/repo"),
            "handoff after checkpoint",
            connector=lambda: FakeConnection(socket),
        )

        steer = next(request for request in socket.requests if request.get("method") == "turn/steer")
        self.assertEqual(steer["params"]["expectedTurnId"], "turn-active")

    def test_codex_notification_fallback_does_not_write_to_the_tui(self) -> None:
        with mock.patch.object(AGENT_TASK, "terminal_inbox_alert") as alert:
            AGENT_TASK.fallback_terminal_inbox_alert(
                ["codex", "--remote", "unix:///control.sock"],
                "codex-session",
                2,
            )
            AGENT_TASK.fallback_terminal_inbox_alert(
                ["codex", "resume", "--last"],
                "codex-session",
                2,
            )

        alert.assert_not_called()

    def test_non_codex_notification_keeps_the_terminal_fallback(self) -> None:
        with mock.patch.object(AGENT_TASK, "terminal_inbox_alert") as alert:
            AGENT_TASK.fallback_terminal_inbox_alert(
                ["claude", "--continue"],
                "claude-session",
                1,
            )

        alert.assert_called_once_with("claude-session", 1)

    def test_handoff_uses_a_graceful_signal_for_the_codex_tui(self) -> None:
        self.assertEqual(
            AGENT_TASK.handoff_shutdown_signal(
                ["codex", "--remote", "unix:///control.sock", "resume", "thread-id"]
            ),
            AGENT_TASK.signal.SIGINT,
        )
        self.assertEqual(
            AGENT_TASK.handoff_shutdown_signal(["claude", "--continue"]),
            AGENT_TASK.signal.SIGTERM,
        )

    def test_handoff_accepts_a_durable_inbox_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            with mock.patch.dict(os.environ, {"AGENT_TASK_STATE_DIR": str(state)}, clear=False):
                store = AGENT_TASK.Store()
                session_id = "session-one"
                session_path = store.sessions / "current.json"
                session = {
                    "session_id": session_id,
                    "notification_protocol": AGENT_TASK.NOTIFICATION_PROTOCOL,
                    "notification_state": "ready",
                    "process": AGENT_TASK.process_record(os.getpid(), role="lock-supervisor"),
                }
                AGENT_TASK.atomic_write_private(
                    session_path,
                    (json.dumps(session) + "\n").encode(),
                )
                task = {
                    "task_id": "ready-task",
                    "target_branch": "main",
                    "repository": "/repo",
                }
                event_id = AGENT_TASK.enqueue_integration_notice(store, session, task)
                duplicate_event_id = AGENT_TASK.enqueue_integration_notice(store, session, task)
                environment = {
                    "AGENT_TASK_STATE_DIR": str(state),
                    AGENT_TASK.AGENT_SESSION_ID_ENV: session_id,
                    AGENT_TASK.AGENT_SESSION_PATH_ENV: str(session_path),
                }
                with (
                    mock.patch.dict(os.environ, environment, clear=False),
                    mock.patch.object(AGENT_TASK.os, "kill") as kill,
                ):
                    result = AGENT_TASK.command_handoff(
                        AGENT_TASK.argparse.Namespace(event_id=event_id),
                        store,
                    )

                inbox = AGENT_TASK.read_session_inbox(store, session_id)

        self.assertEqual(result, 0)
        self.assertEqual(duplicate_event_id, event_id)
        self.assertEqual(len(inbox["messages"]), 1)
        self.assertEqual(inbox["messages"][0]["status"], "accepted")
        kill.assert_any_call(os.getpid(), AGENT_TASK.signal.SIGUSR2)

    def test_claude_stop_hook_injects_and_delivers_an_inbox_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            session_id = "claude-session"
            with mock.patch.dict(os.environ, {"AGENT_TASK_STATE_DIR": str(state)}, clear=False):
                store = AGENT_TASK.Store()
                session = {"session_id": session_id}
                event_id = AGENT_TASK.enqueue_integration_notice(
                    store,
                    session,
                    {"task_id": "ready-task", "target_branch": "main", "repository": "/repo"},
                )
                stdin = mock.Mock()
                stdin.buffer = io.BytesIO(json.dumps({"hook_event_name": "Stop"}).encode())
                stdout = io.StringIO()
                with (
                    mock.patch.dict(
                        os.environ,
                        {AGENT_TASK.AGENT_SESSION_ID_ENV: session_id},
                        clear=False,
                    ),
                    mock.patch.object(AGENT_TASK.sys, "stdin", stdin),
                    contextlib.redirect_stdout(stdout),
                ):
                    result = AGENT_TASK.command_inbox_hook()
                inbox = AGENT_TASK.read_session_inbox(store, session_id)

        output = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(output["decision"], "block")
        self.assertIn(event_id, output["reason"])
        self.assertEqual(inbox["messages"][0]["status"], "delivered")

    def test_checkout_lock_detects_contention_and_releases_automatically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            with (
                mock.patch.dict(os.environ, {"AGENT_TASK_STATE_DIR": str(checkout / "state")}),
                mock.patch.object(AGENT_TASK, "common_dir", return_value=checkout / ".git"),
            ):
                store = AGENT_TASK.Store()
                with AGENT_TASK.checkout_session_lock(store, checkout) as first:
                    with AGENT_TASK.checkout_session_lock(store, checkout) as second:
                        self.assertTrue(first)
                        self.assertFalse(second)
                with AGENT_TASK.checkout_session_lock(store, checkout) as after_release:
                    self.assertTrue(after_release)
                self.assertTrue(store.checkout_lock_path(checkout).exists())
                self.assertFalse((checkout / ".ai-lock").exists())

    def test_auto_open_uses_the_current_checkout_when_available(self) -> None:
        arguments = AGENT_TASK.build_parser().parse_args(["open", "work here", "--auto"])
        arguments.command = []
        completed = mock.Mock(returncode=0)

        with (
            mock.patch.object(AGENT_TASK, "repo_root", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "primary_worktree", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "repository_agent_task_mode", return_value="current"),
            mock.patch.object(
                AGENT_TASK,
                "checkout_session_lock",
                return_value=contextlib.nullcontext(True),
            ),
            mock.patch.object(AGENT_TASK, "prepare_native_repository_memory"),
            mock.patch.object(AGENT_TASK, "retry_ready_integrations_for_repository"),
            mock.patch.object(AGENT_TASK.subprocess, "run", return_value=completed) as run,
        ):
            exit_code = AGENT_TASK.command_open(arguments, mock.Mock())

        self.assertEqual(exit_code, 0)
        self.assertEqual(run.call_args.args[0][-1], "work here")

    def test_direct_open_defaults_to_the_safe_auto_path(self) -> None:
        arguments = AGENT_TASK.build_parser().parse_args(["open", "safe default"])
        arguments.command = []
        completed = mock.Mock(returncode=0)

        with (
            mock.patch.object(AGENT_TASK, "repo_root", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "primary_worktree", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "repository_agent_task_mode", return_value=None),
            mock.patch.object(
                AGENT_TASK,
                "checkout_session_lock",
                return_value=contextlib.nullcontext(True),
            ) as checkout_lock,
            mock.patch.object(AGENT_TASK, "prepare_native_repository_memory"),
            mock.patch.object(AGENT_TASK, "retry_ready_integrations_for_repository"),
            mock.patch.object(AGENT_TASK.subprocess, "run", return_value=completed),
        ):
            exit_code = AGENT_TASK.command_open(arguments, mock.Mock())

        self.assertEqual(exit_code, 0)
        self.assertTrue(arguments.auto)
        checkout_lock.assert_called_once()

    def test_auto_open_falls_back_to_a_worktree_when_busy(self) -> None:
        arguments = AGENT_TASK.build_parser().parse_args(["open", "parallel work", "--auto"])
        arguments.command = []

        with (
            mock.patch.object(AGENT_TASK, "repo_root", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "primary_worktree", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "repository_agent_task_mode", return_value=None),
            mock.patch.object(
                AGENT_TASK,
                "checkout_session_lock",
                return_value=contextlib.nullcontext(False),
            ),
            mock.patch.object(AGENT_TASK, "read_active_checkout_session", return_value=None),
            mock.patch.object(AGENT_TASK, "refresh_interrupted_tasks", return_value=[]),
            mock.patch.object(AGENT_TASK, "command_start", return_value=0) as start,
        ):
            exit_code = AGENT_TASK.command_open(arguments, mock.Mock())

        self.assertEqual(exit_code, 0)
        self.assertTrue(start.call_args.args[0].new)
        self.assertTrue(start.call_args.args[0].isolate_from_active_checkout)
        self.assertIsNone(start.call_args.args[0].active_session_base_sha)

    def test_worktree_policy_skips_the_current_checkout(self) -> None:
        arguments = AGENT_TASK.build_parser().parse_args(["open", "isolated work", "--auto"])
        arguments.command = []

        with (
            mock.patch.object(AGENT_TASK, "repo_root", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "primary_worktree", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "repository_agent_task_mode", return_value="worktree"),
            mock.patch.object(AGENT_TASK, "checkout_session_lock") as checkout_lock,
            mock.patch.object(AGENT_TASK, "refresh_interrupted_tasks", return_value=[]),
            mock.patch.object(AGENT_TASK, "command_start", return_value=0) as start,
        ):
            exit_code = AGENT_TASK.command_open(arguments, mock.Mock())

        self.assertEqual(exit_code, 0)
        checkout_lock.assert_not_called()
        self.assertTrue(start.call_args.args[0].managed)

    def test_current_policy_refuses_a_busy_checkout_without_fallback(self) -> None:
        arguments = AGENT_TASK.build_parser().parse_args(["open", "serialized work", "--auto"])
        arguments.command = []

        with (
            mock.patch.object(AGENT_TASK, "repo_root", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "primary_worktree", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "repository_agent_task_mode", return_value="current"),
            mock.patch.object(
                AGENT_TASK,
                "checkout_session_lock",
                return_value=contextlib.nullcontext(False),
            ),
            mock.patch.object(AGENT_TASK, "command_start") as start,
            self.assertRaisesRegex(AGENT_TASK.AgentTaskError, "repository policy"),
        ):
            AGENT_TASK.command_open(arguments, mock.Mock())

        start.assert_not_called()

    def test_managed_open_starts_separately_when_another_task_is_active(self) -> None:
        arguments = AGENT_TASK.build_parser().parse_args(["open", "parallel work", "--managed"])
        arguments.command = []
        active = {
            "task_id": "active-task",
            "agent": "codex",
            "status": AGENT_TASK.RUNNING,
            "worktree_path": "/state/active-task",
            "process": {"pid": 123, "start": "456"},
            "updated_at": "now",
        }

        with (
            mock.patch.object(AGENT_TASK, "repo_root", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "primary_worktree", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "refresh_interrupted_tasks", return_value=[active]),
            mock.patch.object(AGENT_TASK, "process_alive", return_value=True),
            mock.patch.object(AGENT_TASK, "command_start", return_value=0) as start,
        ):
            exit_code = AGENT_TASK.command_open(arguments, mock.Mock())

        self.assertEqual(exit_code, 0)
        self.assertTrue(start.call_args.args[0].new)

    def test_cross_worktree_resume_uses_the_current_new_worktree(self) -> None:
        command = AGENT_TASK.default_chat_resume_command(
            "codex",
            None,
            last=False,
            include_non_interactive=False,
        )

        self.assertEqual(command[:2], ["codex", "resume"])
        self.assertIn("--all", command)
        self.assertIn('tui.resume_cwd="current"', command)
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", command)

    def test_resume_prefers_a_preserved_task_before_the_global_picker(self) -> None:
        arguments = AGENT_TASK.build_parser().parse_args(["resume"])
        task = {
            "task_id": "preserved-task",
            "agent": "codex",
            "status": AGENT_TASK.RECOVERY,
            "worktree_path": "/state/worktrees/preserved-task",
        }

        with (
            mock.patch.object(AGENT_TASK, "repo_root", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "primary_worktree", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "refresh_interrupted_tasks", return_value=[task]),
            mock.patch.object(AGENT_TASK, "command_recover", return_value=0) as recover,
        ):
            exit_code = AGENT_TASK.command_resume(arguments, mock.Mock())

        self.assertEqual(exit_code, 0)
        self.assertEqual(recover.call_args.args[0].task_id, "preserved-task")
        self.assertEqual(recover.call_args.args[0].command, [])

    def test_resume_without_preserved_work_uses_a_fresh_worktree(self) -> None:
        arguments = AGENT_TASK.build_parser().parse_args(["resume"])

        with (
            mock.patch.object(AGENT_TASK, "repo_root", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "primary_worktree", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "refresh_interrupted_tasks", return_value=[]),
            mock.patch.object(AGENT_TASK, "repository_agent_task_mode", return_value="worktree"),
            mock.patch.object(AGENT_TASK, "checkout_session_lock") as checkout_lock,
            mock.patch.object(AGENT_TASK, "command_start", return_value=0) as start,
        ):
            exit_code = AGENT_TASK.command_resume(arguments, mock.Mock())

        self.assertEqual(exit_code, 0)
        checkout_lock.assert_not_called()
        command = start.call_args.args[0].command
        self.assertEqual(command[:2], ["codex", "resume"])
        self.assertIn("--all", command)
        self.assertIn('tui.resume_cwd="current"', command)

    def test_resume_passthrough_preserves_global_options_and_prompt(self) -> None:
        command = AGENT_TASK.passthrough_chat_resume_command(
            ["--last", "-m", "gpt-5.6", "continue the audit"]
        )

        self.assertEqual(command[:2], ["codex", "resume"])
        self.assertEqual(command[-4:], ["--last", "-m", "gpt-5.6", "continue the audit"])
        self.assertNotIn("--all", command)

        picker = AGENT_TASK.passthrough_chat_resume_command(["-m", "gpt-5.6"])
        self.assertIn("--all", picker)

    def test_codex_cd_is_normalized_before_checkout_selection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            origin = Path(directory) / "origin"
            target = Path(directory) / "target"
            origin.mkdir()
            target.mkdir()
            command, selected = AGENT_TASK.normalize_codex_working_directory(
                ["codex", "-C", "../target", "work here"],
                origin,
            )

        self.assertEqual(selected, target.resolve())
        self.assertEqual(command[2], str(target.resolve()))

    def test_review_style_command_refuses_a_busy_current_checkout(self) -> None:
        arguments = AGENT_TASK.build_parser().parse_args(
            ["open", "--auto", "--require-current", "--agent", "custom"]
        )
        arguments.command = ["true"]

        with (
            mock.patch.object(AGENT_TASK, "repo_root", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "primary_worktree", return_value=Path("/repo")),
            mock.patch.object(
                AGENT_TASK,
                "checkout_session_lock",
                return_value=contextlib.nullcontext(False),
            ),
            self.assertRaisesRegex(AGENT_TASK.AgentTaskError, "different snapshot"),
        ):
            AGENT_TASK.command_open(arguments, mock.Mock())

    def test_review_is_detected_after_codex_global_options(self) -> None:
        command = [
            "codex",
            "-m",
            "gpt-5.6",
            "--enable",
            "example",
            "-C",
            "/tmp",
            "review",
            "--uncommitted",
        ]

        self.assertEqual(AGENT_TASK.codex_subcommand(command), "review")
        self.assertIsNone(AGENT_TASK.codex_subcommand(["codex", "--", "review"]))

    def test_new_takes_precedence_over_auto(self) -> None:
        arguments = AGENT_TASK.build_parser().parse_args(
            ["open", "--auto", "--new", "--agent", "custom"]
        )
        arguments.command = ["true"]

        with (
            mock.patch.object(AGENT_TASK, "repo_root", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "primary_worktree", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "refresh_interrupted_tasks", return_value=[]),
            mock.patch.object(AGENT_TASK, "checkout_session_lock") as checkout_lock,
            mock.patch.object(AGENT_TASK, "command_start", return_value=0) as start,
        ):
            exit_code = AGENT_TASK.command_open(arguments, mock.Mock())

        self.assertEqual(exit_code, 0)
        checkout_lock.assert_not_called()
        self.assertTrue(start.call_args.args[0].new)

    def test_nested_claude_worktree_lifecycles_are_refused(self) -> None:
        for flag in ("--background", "--bg", "--tmux", "--worktree", "-w"):
            with self.subTest(flag=flag), self.assertRaisesRegex(
                AGENT_TASK.AgentTaskError,
                "separate worktree lifecycle",
            ):
                AGENT_TASK.validate_foreground_agent_command(
                    "claude",
                    ["claude", flag],
                    lock_managed=True,
                )

    def test_malformed_process_records_are_not_treated_as_live(self) -> None:
        self.assertFalse(AGENT_TASK.process_alive({"pid": "not-a-pid", "start": "1"}))
        self.assertFalse(AGENT_TASK.process_alive({"pid": 1, "start": "1"}))
        self.assertFalse(AGENT_TASK.process_alive({"pid": os.getpid(), "start": None}))

    def test_store_refuses_symlinked_task_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            os.environ,
            {"AGENT_TASK_STATE_DIR": str(Path(directory) / "state")},
        ):
            store = AGENT_TASK.Store()
            outside = Path(directory) / "outside.json"
            outside.write_text('{"task_id":"unsafe"}\n')
            store.task_path("unsafe").symlink_to(outside)

            with self.assertRaisesRegex(AGENT_TASK.AgentTaskError, "safely read"):
                store.load("unsafe")

            self.assertEqual(outside.read_text(), '{"task_id":"unsafe"}\n')

    def test_bubblewrap_is_forgotten_without_removing_the_package(self) -> None:
        configuration = SCRIPT.parent.parent.joinpath("agent-task.tf").read_text()

        self.assertIn("from = host_package_pacman.bubblewrap", configuration)
        self.assertIn("destroy = false", configuration)

    def test_agent_lock_is_globally_ignored(self) -> None:
        configuration = SCRIPT.parent.parent.joinpath("git.tf").read_text()

        self.assertIn(".ai-memory", configuration)
        self.assertIn(".ai-lock", configuration)

    def test_global_agents_preflight_shared_operational_resources(self) -> None:
        root = SCRIPT.parent.parent

        for relative_path in ("codex/AGENTS.md", "claude/CLAUDE.md"):
            with self.subTest(relative_path=relative_path):
                instructions = root.joinpath(relative_path).read_text()
                self.assertIn("## Shared operational resources", instructions)
                self.assertIn("Never assume a Git branch or worktree isolates", instructions)
                self.assertIn("Do not invent or require a new launcher flag", instructions)
                self.assertIn("Repository memory is learned context, not a mutex", instructions)
                self.assertIn("agent-task attach ABSOLUTE_PATH", instructions)
                self.assertIn("never ask the operator to run it", instructions)

    def test_local_open_invocation_launches_the_native_agent(self) -> None:
        arguments = AGENT_TASK.build_parser().parse_args(["open", "continue here", "--agent", "codex", "--local"])
        arguments.command = []
        environment = {
            "AI_TASK_HARNESS": "agent-task",
            "AI_TASK_WORKTREE": "/managed/worktree",
            "AGENT_TASK_POLICY": "/managed/policy.json",
        }
        completed = mock.Mock(returncode=0)

        with (
            mock.patch.dict(os.environ, environment, clear=True),
            mock.patch.object(AGENT_TASK.subprocess, "run", return_value=completed) as run,
        ):
            exit_code = AGENT_TASK.command_open(arguments, mock.Mock())

        self.assertEqual(exit_code, 0)
        self.assertEqual(run.call_args.args[0][0], "codex")
        self.assertEqual(run.call_args.args[0][-1], "continue here")
        self.assertNotIn("AI_TASK_HARNESS", run.call_args.kwargs["env"])
        self.assertNotIn("AGENT_TASK_POLICY", run.call_args.kwargs["env"])
        self.assertNotIn("AI_TASK_WORKDIR", run.call_args.kwargs["env"])


class WorktreeStatuslineTest(unittest.TestCase):
    def make_store(self, root: Path) -> object:
        with mock.patch.dict(os.environ, {"AGENT_TASK_STATE_DIR": str(root / "state")}, clear=False):
            return AGENT_TASK.Store()

    def task(
        self,
        task_id: str,
        repository: str,
        *,
        description: str = "interactive agent task",
        live: bool = True,
    ) -> dict[str, object]:
        return {
            "task_id": task_id,
            "repository": f"/projects/{repository}",
            "worktree_path": f"/state/worktrees/{repository}/{task_id}",
            "status": AGENT_TASK.RUNNING,
            "process": (
                AGENT_TASK.process_record(os.getpid(), role="agent")
                if live
                else {"pid": 1, "start": "dead", "role": "agent"}
            ),
            "agent": "codex",
            "description": description,
            "created_at": f"2026-08-26T{task_id[9:11]}:{task_id[11:13]}:00+09:00",
        }

    def test_statusline_filters_dead_tasks_and_pins_current_jira(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(Path(directory))
            current_id = "20260826-204635-a5bc90"
            other_id = "20260826-213159-dbda5e"
            store.save(self.task(current_id, "environments"))
            store.save(self.task(other_id, "backend"))
            store.save(self.task("20260826-190000-dead00", "stale", live=False))
            AGENT_TASK.write_task_context(store, current_id, {"jira_issue": "CAPE-123"})

            first = AGENT_TASK.worktree_statusline(
                store,
                width=58,
                epoch=0,
                current_task_id=current_id,
            )
            second = AGENT_TASK.worktree_statusline(
                store,
                width=58,
                epoch=1,
                current_task_id=current_id,
            )
            environment = os.environ.copy()
            environment["AGENT_TASK_STATE_DIR"] = str(store.root)
            environment["AI_TASK_ID"] = current_id
            standalone = subprocess.run(
                [sys.executable, str(STATUSLINE_SCRIPT), "--width", "58", "--epoch", "0"],
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            ).stdout.strip()

        prefix = "WT 2 | *codex/environments@20:46[CAPE-123] | "
        self.assertTrue(first.startswith(prefix), first)
        self.assertTrue(second.startswith(prefix), second)
        self.assertNotEqual(first, second)
        self.assertNotIn("stale", first)
        self.assertEqual(standalone, first)

    def test_jira_context_can_be_set_and_cleared_without_the_task_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(Path(directory))
            task_id = "20260826-204635-a5bc90"
            store.save(self.task(task_id, "environments"))
            arguments = argparse.Namespace(task_id=task_id, jira="cape-456", clear_jira=False)

            with (
                store.lock(f"task:{task_id}"),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                AGENT_TASK.command_context(arguments, store)
            self.assertEqual(AGENT_TASK.read_task_context(store, task_id)["jira_issue"], "CAPE-456")

            arguments.clear_jira = True
            with contextlib.redirect_stdout(io.StringIO()):
                AGENT_TASK.command_context(arguments, store)
            self.assertNotIn("jira_issue", AGENT_TASK.read_task_context(store, task_id))

    def test_statusline_scroll_does_not_repeat_the_fixed_separator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(Path(directory))
            current_id = "20260826-204635-a5bc90"
            store.save(self.task(current_id, "environments"))
            store.save(self.task("20260826-213159-dbda5e", "backend"))
            store.save(self.task("20260826-211200-bcde12", "frontend"))

            with mock.patch.object(AGENT_TASK, "render_worktree_statusline", STATUSLINE.render):
                lines = [
                    AGENT_TASK.worktree_statusline(
                        store,
                        width=54,
                        epoch=epoch,
                        current_task_id=current_id,
                    )
                    for epoch in range(80)
                ]

        self.assertTrue(any("·" in line for line in lines))
        self.assertTrue(all("|  |" not in line for line in lines))

    def test_codex_statusline_shows_number_branch_path_and_optional_jira(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(Path(directory))
            task_id = "20260828-150920-7fb1e6"
            task = self.task(task_id, "environments")
            task.update(
                {
                    "worktree_number": 17,
                    "branch": f"ai/codex/{task_id}",
                    "origin_working_directory": "/home/dongho/projects/environments/arch-desktop",
                }
            )
            store.save(task)

            without_jira = AGENT_TASK.codex_worktree_statusline(store, task_id)
            AGENT_TASK.write_task_context(store, task_id, {"jira_issue": "CAPE-123"})
            with_jira = AGENT_TASK.codex_worktree_statusline(store, task_id)

        expected = (
            "WT#17 · ai/codex/20260828-150920-7fb1e6 · "
            ".../projects/environments/arch-desktop"
        )
        self.assertEqual(without_jira, expected)
        self.assertEqual(with_jira, f"{expected} · CAPE-123")

    def test_codex_statusline_path_keeps_three_tail_parts_with_a_hard_limit(self) -> None:
        compact = AGENT_TASK.compact_statusline_path(
            "/one/two/three/this-directory-name-is-far-too-long/another-long-directory/final",
            limit=36,
        )

        self.assertEqual(len(compact), 36)
        self.assertTrue(compact.startswith("..."))
        self.assertTrue(compact.endswith("/final"))
        self.assertEqual(
            AGENT_TASK.next_worktree_number(
                [{"task_id": "old"}, {"task_id": "new", "worktree_number": 7}]
            ),
            8,
        )

    def test_jira_issue_is_detected_from_the_launch_description(self) -> None:
        task = {"description": "Implement CAPE-789 without changing the API"}

        self.assertEqual(AGENT_TASK.jira_issue_from_task_text(task), "CAPE-789")
        with self.assertRaisesRegex(AGENT_TASK.AgentTaskError, "invalid Jira issue"):
            AGENT_TASK.jira_issue_key("not a ticket")

    def test_claude_native_worktree_is_visible_without_a_harness_task(self) -> None:
        store = mock.Mock()
        store.all.return_value = []
        payload = {
            "cwd": "/tmp/example",
            "workspace": {
                "current_dir": "/tmp/example",
                "project_dir": "/tmp/example",
                "git_worktree": "feature-demo",
                "repo": {"name": "example"},
            },
        }

        line = AGENT_TASK.worktree_statusline(
            store,
            width=80,
            epoch=0,
            current_directory="/tmp/example",
            claude_payload=payload,
        )

        self.assertEqual(line, "WT 1 | *claude/example@feature-demo")

    def test_staged_lifecycle_cli_loads_the_installed_statusline_module(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staged = root / "version" / "agent-task"
            module = root / "home" / ".local/bin/agent_statusline.py"
            staged.parent.mkdir()
            module.parent.mkdir(parents=True)
            shutil.copy2(SCRIPT, staged)
            shutil.copy2(STATUSLINE_SCRIPT, module)
            environment = os.environ.copy()
            environment["HOME"] = str(root / "home")

            result = subprocess.run(
                [sys.executable, str(staged), "--help"],
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Run coding agents", result.stdout)


class HarnessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.repository = root / "repo"
        self.state = root / "state"
        self.git("init", "-b", "main", str(self.repository), cwd=root)
        self.git("config", "user.name", "Test Agent")
        self.git("config", "user.email", "agent@example.com")
        self.git("config", "commit.gpgsign", "false")
        exclude = self.repository / ".git/info/exclude"
        exclude.write_text(exclude.read_text() + "\n.ai-memory\n.ai-lock\n")
        (self.repository / ".gitignore").write_text(".agent-cache/\n")
        (self.repository / "shared.txt").write_text("base\n")
        self.git("add", ".")
        self.git("commit", "-m", "base")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git(self, *args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=cwd or self.repository,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=check,
        )

    def cli_environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment["AGENT_TASK_STATE_DIR"] = str(self.state)
        environment["GIT_CONFIG_GLOBAL"] = os.devnull
        environment["XDG_CONFIG_HOME"] = str(self.state / "xdg")
        environment.pop("SSH_AUTH_SOCK", None)
        return environment

    def cli(self, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=self.repository,
            env=self.cli_environment(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if check and result.returncode:
            self.fail(f"command failed ({result.returncode})\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        return result

    def store(self) -> object:
        with mock.patch.dict(os.environ, {"AGENT_TASK_STATE_DIR": str(self.state)}):
            return AGENT_TASK.Store()

    def task_from(self, result: subprocess.CompletedProcess[str]) -> dict[str, object]:
        task_id = next(line.removeprefix("task: ") for line in result.stdout.splitlines() if line.startswith("task: "))
        return json.loads((self.state / "tasks" / f"{task_id}.json").read_text())

    def test_auto_open_runs_natively_when_the_checkout_is_free(self) -> None:
        memory = AGENT_TASK.memory_template("main")
        memory["settings"]["agent_task_mode"] = "current"
        AGENT_TASK.write_memory(self.repository / ".ai-memory", memory)
        result = self.cli(
            "open",
            "--auto",
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            f"test \"$PWD\" = {shlex.quote(str(self.repository))}",
            check=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(list((self.state / "tasks").glob("*.json")), [])
        self.assertEqual(self.git("status", "--porcelain").stdout, "")

    def test_worktree_policy_isolates_and_integrates_the_first_task(self) -> None:
        memory = AGENT_TASK.memory_template("main")
        memory["settings"]["agent_task_mode"] = "worktree"
        AGENT_TASK.write_memory(self.repository / ".ai-memory", memory)

        result = self.cli(
            "open",
            "isolated by repository policy",
            "--auto",
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            (
                "printf 'isolated\\n' > policy-result.txt && "
                "git add policy-result.txt && git commit -m 'feat: add policy result'"
            ),
            check=True,
        )
        task = self.task_from(result)

        self.assertEqual(task["status"], AGENT_TASK.INTEGRATED)
        self.assertEqual(task["worktree_number"], 1)
        self.assertEqual(task["origin_working_directory"], str(self.repository))
        self.assertEqual((self.repository / "policy-result.txt").read_text(), "isolated\n")

    def test_native_session_records_main_as_target_before_branch_contention(self) -> None:
        self.git("branch", "develop")

        self.cli("open", "--auto", "--agent", "custom", "--", "true", check=True)
        memory = json.loads((self.repository / ".ai-memory").read_text())

        self.assertEqual(memory["settings"]["integration_target"], "main")

    def test_managed_session_attaches_and_integrates_a_secondary_repository(self) -> None:
        secondary = Path(self.temporary.name) / "secondary"
        self.git("init", "-b", "main", str(secondary), cwd=Path(self.temporary.name))
        self.git("config", "user.name", "Test Agent", cwd=secondary)
        self.git("config", "user.email", "agent@example.com", cwd=secondary)
        self.git("config", "commit.gpgsign", "false", cwd=secondary)
        exclude = secondary / ".git/info/exclude"
        exclude.write_text(exclude.read_text() + "\n.ai-memory\n.ai-lock\n")
        (secondary / "base.txt").write_text("base\n")
        self.git("add", ".", cwd=secondary)
        self.git("commit", "-m", "base", cwd=secondary)

        agent_code = (
            "import subprocess,sys; from pathlib import Path; "
            f"script={str(SCRIPT)!r}; secondary={str(secondary)!r}; "
            "attached=subprocess.run([sys.executable,script,'attach',secondary],"
            "check=True,text=True,stdout=subprocess.PIPE); "
            "worktree=Path(next(line.removeprefix('worktree: ') for line in "
            "attached.stdout.splitlines() if line.startswith('worktree: '))); "
            "worktree.joinpath('secondary.txt').write_text('attached\\n'); "
            "subprocess.run(['git','add','secondary.txt'],cwd=worktree,check=True); "
            "subprocess.run(['git','commit','-m','feat: add attached result'],cwd=worktree,check=True)"
        )
        result = self.cli(
            "open",
            "--managed",
            "--new",
            "--agent",
            "custom",
            "--task",
            "work in two repositories",
            "--",
            sys.executable,
            "-c",
            agent_code,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((secondary / "secondary.txt").read_text(), "attached\n")
        self.assertEqual(self.git("branch", "--show-current", cwd=secondary).stdout.strip(), "main")
        tasks = [json.loads(path.read_text()) for path in (self.state / "tasks").glob("*.json")]
        attachment = next(task for task in tasks if task.get("attachment_parent_task_id"))
        parent = next(task for task in tasks if task["task_id"] == attachment["attachment_parent_task_id"])
        self.assertEqual(attachment["status"], AGENT_TASK.INTEGRATED)
        self.assertIn(attachment["task_id"], parent["attachments"])

    def test_secondary_attachment_preserves_uncommitted_work(self) -> None:
        secondary = Path(self.temporary.name) / "secondary-uncommitted"
        self.git("init", "-b", "main", str(secondary), cwd=Path(self.temporary.name))
        self.git("config", "user.name", "Test Agent", cwd=secondary)
        self.git("config", "user.email", "agent@example.com", cwd=secondary)
        self.git("config", "commit.gpgsign", "false", cwd=secondary)
        exclude = secondary / ".git/info/exclude"
        exclude.write_text(exclude.read_text() + "\n.ai-memory\n.ai-lock\n")
        (secondary / "base.txt").write_text("base\n")
        self.git("add", ".", cwd=secondary)
        self.git("commit", "-m", "base", cwd=secondary)

        agent_code = (
            "import subprocess,sys; from pathlib import Path; "
            f"script={str(SCRIPT)!r}; secondary={str(secondary)!r}; "
            "attached=subprocess.run([sys.executable,script,'attach',secondary],"
            "check=True,text=True,stdout=subprocess.PIPE); "
            "worktree=Path(next(line.removeprefix('worktree: ') for line in "
            "attached.stdout.splitlines() if line.startswith('worktree: '))); "
            "worktree.joinpath('unfinished.txt').write_text('preserve me\\n')"
        )
        result = self.cli(
            "open",
            "--managed",
            "--new",
            "--agent",
            "custom",
            "--task",
            "leave secondary work unfinished",
            "--",
            sys.executable,
            "-c",
            agent_code,
        )

        self.assertEqual(result.returncode, 2)
        tasks = [json.loads(path.read_text()) for path in (self.state / "tasks").glob("*.json")]
        attachment = next(task for task in tasks if task.get("attachment_parent_task_id"))
        preserved = Path(attachment["worktree_path"])
        self.assertEqual(attachment["status"], AGENT_TASK.RECOVERY)
        self.assertEqual((preserved / "unfinished.txt").read_text(), "preserve me\n")
        self.assertFalse((secondary / "unfinished.txt").exists())
        self.assertEqual(self.git("branch", "--show-current", cwd=secondary).stdout.strip(), "main")

    def test_regular_exit_75_is_not_mistaken_for_a_handoff(self) -> None:
        result = self.cli(
            "open",
            "--auto",
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            "exit 75",
        )

        self.assertEqual(result.returncode, 75)

    def test_auto_open_isolates_busy_dirty_work_and_queues_integration(self) -> None:
        local_only = self.repository / "local-only.txt"
        local_only.write_text("owned by the in-place session\n")
        with AGENT_TASK.checkout_session_lock(self.store(), self.repository) as acquired:
            self.assertTrue(acquired)
            result = self.cli(
                "open",
                "--auto",
                "--agent",
                "custom",
                "--task",
                "parallel work",
                "--",
                "sh",
                "-lc",
                "printf 'parallel\\n' > parallel.txt && git add parallel.txt && git commit -m 'feat: add parallel result'",
            )
            task = self.task_from(result)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(task["status"], AGENT_TASK.READY)
        self.assertEqual(task["base_source"], "integration_target")
        self.assertTrue(local_only.exists())
        self.assertFalse((self.repository / "parallel.txt").exists())

        local_only.unlink()
        self.cli("reconcile", check=True)
        task = json.loads((self.state / "tasks" / f"{task['task_id']}.json").read_text())
        self.assertEqual(task["status"], AGENT_TASK.INTEGRATED)
        self.assertEqual((self.repository / "parallel.txt").read_text(), "parallel\n")

    def test_active_session_handoff_retries_queued_integration(self) -> None:
        ready = self.state / "owner-ready"
        agent_code = (
            "import json,os,subprocess,sys,time; "
            "from pathlib import Path; "
            f"ready=Path({str(ready)!r}); script={str(SCRIPT)!r}; "
            "ready.parent.mkdir(parents=True,exist_ok=True); ready.write_text('ready'); "
            "inbox=Path(os.environ['AGENT_TASK_STATE_DIR'])/'inboxes'/"
            "(os.environ['AGENT_TASK_SESSION_ID']+'.json'); "
            "event=None; "
            "deadline=time.monotonic()+15; "
            "\nwhile time.monotonic()<deadline and event is None:\n"
            " try:\n"
            "  data=json.loads(inbox.read_text())\n"
            "  event=next((m['id'] for m in data['messages'] if m['status'] in ('pending','delivered')),None)\n"
            " except (FileNotFoundError,json.JSONDecodeError): pass\n"
            " time.sleep(0.05)\n"
            "\nif event is None: raise SystemExit(3)\n"
            "subprocess.run([sys.executable,script,'handoff',event],check=True); time.sleep(30)"
        )
        owner = subprocess.Popen(
            [
                sys.executable,
                str(SCRIPT),
                "open",
                "--auto",
                "--agent",
                "custom",
                "--task",
                "hold the native checkout",
                "--",
                sys.executable,
                "-c",
                agent_code,
            ],
            cwd=self.repository,
            env=self.cli_environment(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            deadline = time.monotonic() + 10
            while not ready.exists() and owner.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(ready.exists(), "native owner did not become ready")

            queued = self.cli(
                "open",
                "parallel handoff work",
                "--auto",
                "--agent",
                "custom",
                "--task",
                "parallel handoff work",
                "--",
                "sh",
                "-lc",
                (
                    "printf 'integrated by handoff\\n' > handed-off.txt && "
                    "git add handed-off.txt && git commit -m 'feat: add handed-off result'"
                ),
            )
            task = self.task_from(queued)
            owner_stdout, owner_stderr = owner.communicate(timeout=20)
        finally:
            if owner.poll() is None:
                owner.terminate()
                owner.wait(timeout=5)

        self.assertEqual(queued.returncode, 2, queued.stderr)
        self.assertEqual(owner.returncode, 0, f"stdout:\n{owner_stdout}\nstderr:\n{owner_stderr}")
        updated = json.loads((self.state / "tasks" / f"{task['task_id']}.json").read_text())
        self.assertEqual(updated["status"], AGENT_TASK.INTEGRATED)
        self.assertEqual((self.repository / "handed-off.txt").read_text(), "integrated by handoff\n")

    def test_normal_session_exit_drains_ready_integrations(self) -> None:
        ready = self.state / "normal-owner-ready"
        release = self.state / "normal-owner-release"
        agent_code = (
            "import time; from pathlib import Path; "
            f"ready=Path({str(ready)!r}); release=Path({str(release)!r}); "
            "ready.parent.mkdir(parents=True,exist_ok=True); ready.write_text('ready'); "
            "deadline=time.monotonic()+15; "
            "\nwhile not release.exists() and time.monotonic()<deadline: time.sleep(0.05)\n"
            "\nif not release.exists(): raise SystemExit(3)"
        )
        owner = subprocess.Popen(
            [
                sys.executable,
                str(SCRIPT),
                "open",
                "--auto",
                "--agent",
                "custom",
                "--task",
                "hold until normal exit",
                "--",
                sys.executable,
                "-c",
                agent_code,
            ],
            cwd=self.repository,
            env=self.cli_environment(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            deadline = time.monotonic() + 10
            while not ready.exists() and owner.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(ready.exists(), "normal native owner did not become ready")

            queued = self.cli(
                "open",
                "normal exit drain work",
                "--auto",
                "--agent",
                "custom",
                "--task",
                "normal exit drain work",
                "--",
                "sh",
                "-lc",
                (
                    "printf 'integrated after exit\\n' > exit-drained.txt && "
                    "git add exit-drained.txt && git commit -m 'feat: add exit-drained result'"
                ),
            )
            task = self.task_from(queued)
            release.write_text("exit\n")
            owner_stdout, owner_stderr = owner.communicate(timeout=20)
        finally:
            if owner.poll() is None:
                owner.terminate()
                owner.wait(timeout=5)

        self.assertEqual(queued.returncode, 2, queued.stderr)
        self.assertEqual(owner.returncode, 0, f"stdout:\n{owner_stdout}\nstderr:\n{owner_stderr}")
        updated = json.loads((self.state / "tasks" / f"{task['task_id']}.json").read_text())
        self.assertEqual(updated["status"], AGENT_TASK.INTEGRATED)
        self.assertEqual((self.repository / "exit-drained.txt").read_text(), "integrated after exit\n")

    def test_auto_open_uses_the_active_session_start_before_later_commits(self) -> None:
        session_base = self.git("rev-parse", "HEAD").stdout.strip()
        store = self.store()
        with AGENT_TASK.checkout_session_lock(store, self.repository, record_session_base=True) as acquired:
            self.assertTrue(acquired)
            metadata = AGENT_TASK.read_active_checkout_session(store, self.repository)
            self.assertIsNotNone(metadata)
            self.assertEqual(metadata["base_sha"], session_base)

            (self.repository / "target-before-branch.txt").write_text("safe target work\n")
            self.git("add", "target-before-branch.txt")
            self.git("commit", "-m", "chore: advance target before branch")
            fork_point = self.git("rev-parse", "HEAD").stdout.strip()
            self.git("switch", "-c", "feature/active-agent")
            (self.repository / "active-agent.txt").write_text("must stay on J\n")
            self.git("add", "active-agent.txt")
            self.git("commit", "-m", "feat: add active agent work")

            result = self.cli(
                "open",
                "parallel work",
                "--auto",
                "--agent",
                "custom",
                "--task",
                "parallel work",
                "--",
                "sh",
                "-lc",
                "printf 'parallel only\\n' > parallel-only.txt && git add parallel-only.txt && git commit -m 'feat: add parallel-only result'",
            )
            task = self.task_from(result)

        self.assertEqual(result.returncode, 2)
        self.cli("reconcile", check=True)
        task = json.loads((self.state / "tasks" / f"{task['task_id']}.json").read_text())
        self.assertEqual(task["base_sha"], fork_point)
        self.assertNotEqual(task["base_sha"], session_base)
        self.assertEqual(task["base_source"], "active_branch_creation")
        self.assertEqual(task["source_branch"], "main")
        self.assertEqual(self.git("show", "main:parallel-only.txt").stdout, "parallel only\n")
        self.assertNotEqual(self.git("show", "main:active-agent.txt", check=False).returncode, 0)
        self.assertEqual(self.git("show", "feature/active-agent:active-agent.txt").stdout, "must stay on J\n")
        self.assertFalse((self.repository / ".ai-lock").exists())

    def test_auto_open_excludes_commits_made_on_target_by_the_active_session(self) -> None:
        session_base = self.git("rev-parse", "HEAD").stdout.strip()
        store = self.store()
        with AGENT_TASK.checkout_session_lock(store, self.repository, record_session_base=True) as acquired:
            self.assertTrue(acquired)
            (self.repository / "active-target-only.txt").write_text("X owns this commit\n")
            self.git("add", "active-target-only.txt")
            self.git("commit", "-m", "feat: add active target work")

            result = self.cli(
                "open",
                "parallel without active target work",
                "--auto",
                "--agent",
                "custom",
                "--task",
                "parallel without active target work",
                "--",
                "sh",
                "-lc",
                (
                    "test ! -e active-target-only.txt && "
                    "printf 'K only\n' > isolated-target-result.txt && "
                    "git add isolated-target-result.txt && git commit -m 'feat: add isolated target result'"
                ),
            )
            task = self.task_from(result)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(task["base_sha"], session_base)
        self.assertEqual(task["base_source"], "checkout_session_start")
        self.cli("reconcile", check=True)
        self.assertEqual((self.repository / "active-target-only.txt").read_text(), "X owns this commit\n")
        self.assertEqual((self.repository / "isolated-target-result.txt").read_text(), "K only\n")

    def test_auto_open_uses_branch_creation_point_after_active_branch_rebase(self) -> None:
        store = self.store()
        with AGENT_TASK.checkout_session_lock(
            store,
            self.repository,
            record_session_base=True,
        ) as acquired:
            self.assertTrue(acquired)
            (self.repository / "before-branch.txt").write_text("shared before J\n")
            self.git("add", "before-branch.txt")
            self.git("commit", "-m", "chore: add pre-branch commit")
            branch_creation = self.git("rev-parse", "HEAD").stdout.strip()

            self.git("switch", "-c", "feature/rebased-active-agent")
            (self.repository / "active-branch.txt").write_text("J only\n")
            self.git("add", "active-branch.txt")
            self.git("commit", "-m", "feat: add active branch result")

            target_worktree = self.repository.parent / "advance-main"
            self.git("worktree", "add", str(target_worktree), "main")
            (target_worktree / "target-after-branch.txt").write_text("later target\n")
            self.git("-C", str(target_worktree), "add", "target-after-branch.txt")
            self.git("-C", str(target_worktree), "commit", "-m", "chore: advance target after branch")
            self.git("worktree", "remove", str(target_worktree))
            target_after_branch = self.git("rev-parse", "main").stdout.strip()

            self.git("rebase", "main")
            self.assertEqual(self.git("merge-base", "HEAD", "main").stdout.strip(), target_after_branch)

            result = self.cli(
                "open",
                "parallel from the real branch parent",
                "--auto",
                "--agent",
                "custom",
                "--task",
                "parallel from the real branch parent",
                "--",
                "sh",
                "-lc",
                (
                    "test ! -e target-after-branch.txt && "
                    "test ! -e active-branch.txt && "
                    "printf 'K only\\n' > isolated-from-creation.txt && "
                    "git add isolated-from-creation.txt && "
                    "git commit -m 'feat: add branch-creation-isolated result'"
                ),
            )
            task = self.task_from(result)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(task["base_sha"], branch_creation)
        self.assertEqual(task["base_source"], "active_branch_creation")
        self.cli("reconcile", check=True)
        self.assertEqual(self.git("show", "main:isolated-from-creation.txt").stdout, "K only\n")
        self.assertEqual(self.git("show", "main:target-after-branch.txt").stdout, "later target\n")
        self.assertNotEqual(self.git("show", "main:active-branch.txt", check=False).returncode, 0)

    def test_git_clean_cannot_bypass_the_stable_lock(self) -> None:
        legacy = self.repository / ".ai-lock"
        legacy.write_text("")
        store = self.store()

        with AGENT_TASK.checkout_session_lock(store, self.repository) as first:
            self.assertTrue(first)
            self.git("clean", "-fdx")
            self.assertFalse(legacy.exists())
            with AGENT_TASK.checkout_session_lock(store, self.repository) as second:
                self.assertFalse(second)

        with AGENT_TASK.checkout_session_lock(store, self.repository) as released:
            self.assertTrue(released)

    def test_legacy_session_is_never_sent_the_handoff_signal(self) -> None:
        store = self.store()
        with AGENT_TASK.checkout_lock_files(store, self.repository) as reservation:
            self.assertTrue(reservation)
            metadata = AGENT_TASK.checkout_session_metadata(self.repository, "legacy-session")
            metadata["process"] = AGENT_TASK.process_record(os.getpid(), role="lock-supervisor")
            AGENT_TASK.atomic_write_private(
                store.checkout_session_path(self.repository),
                (json.dumps(metadata) + "\n").encode(),
            )
            with mock.patch.object(AGENT_TASK.os, "kill") as kill:
                notified = AGENT_TASK.notify_active_sessions(
                    store,
                    self.repository,
                    {
                        "task_id": "ready-task",
                        "target_branch": "main",
                        "repository": str(self.repository),
                    },
                )

        self.assertEqual(notified, 0)
        kill.assert_not_called()

    def test_agent_child_keeps_the_checkout_lock_after_launcher_release(self) -> None:
        store = self.store()
        descriptors_seen = self.repository.parent / "agent-fds.txt"
        with AGENT_TASK.checkout_session_lock(store, self.repository) as reservation:
            self.assertTrue(reservation)
            agent_code = (
                "import os,time; from pathlib import Path; "
                f"p=Path({str(descriptors_seen)!r}); "
                "p.write_text('\\n'.join(os.readlink(f'/proc/self/fd/{fd}') "
                "for fd in os.listdir('/proc/self/fd') if os.path.exists(f'/proc/self/fd/{fd}'))); "
                "time.sleep(0.4)"
            )
            command, environment = AGENT_TASK.guarded_agent_invocation(
                [sys.executable, "-c", agent_code],
                os.environ.copy(),
                tuple(reservation),
            )
            child = subprocess.Popen(
                command,
                env=environment,
                pass_fds=tuple(reservation),
            )

        try:
            for _ in range(100):
                if descriptors_seen.exists():
                    break
                time.sleep(0.01)
            self.assertTrue(descriptors_seen.exists())
            self.assertNotIn(str(store.checkout_lock_path(self.repository)), descriptors_seen.read_text())
            with AGENT_TASK.checkout_session_lock(store, self.repository) as while_child_runs:
                self.assertFalse(while_child_runs)
        finally:
            child.wait(timeout=5)

        with AGENT_TASK.checkout_session_lock(store, self.repository) as after_child:
            self.assertTrue(after_child)

    def test_daemonized_descendant_keeps_the_checkout_reserved_until_exit(self) -> None:
        store = self.store()
        with AGENT_TASK.checkout_session_lock(store, self.repository) as reservation:
            self.assertTrue(reservation)
            command, environment = AGENT_TASK.guarded_agent_invocation(
                ["sh", "-lc", "sleep 0.4 &"],
                os.environ.copy(),
                tuple(reservation),
            )
            supervisor = subprocess.Popen(
                command,
                env=environment,
                pass_fds=tuple(reservation),
            )

        time.sleep(0.1)
        self.assertIsNone(supervisor.poll())
        with AGENT_TASK.checkout_session_lock(store, self.repository) as while_descendant_runs:
            self.assertFalse(while_descendant_runs)

        supervisor.wait(timeout=5)
        with AGENT_TASK.checkout_session_lock(store, self.repository) as after_descendant:
            self.assertTrue(after_descendant)

    def test_session_base_survives_launcher_exit_while_supervisor_is_alive(self) -> None:
        store = self.store()
        session_base = self.git("rev-parse", "HEAD").stdout.strip()
        supervisor: subprocess.Popen[bytes] | None = None
        with AGENT_TASK.checkout_session_lock(
            store,
            self.repository,
            record_session_base=True,
        ) as reservation:
            self.assertIsInstance(reservation, AGENT_TASK.CheckoutReservation)
            (self.repository / "active-after-session-start.txt").write_text("X only\n")
            self.git("add", "active-after-session-start.txt")
            self.git("commit", "-m", "feat: add active session commit")
            command, environment = AGENT_TASK.guarded_agent_invocation(
                ["sleep", "1"],
                os.environ.copy(),
                tuple(reservation),
                checkout_reservation=reservation,
            )
            supervisor = subprocess.Popen(
                command,
                env=environment,
                pass_fds=tuple(reservation),
            )

            for _ in range(100):
                active = AGENT_TASK.read_active_checkout_session(store, self.repository, attempts=1)
                if active and active.get("process", {}).get("pid") == supervisor.pid:
                    break
                time.sleep(0.01)
            else:
                self.fail("lock supervisor did not take ownership of session metadata")

        try:
            active = AGENT_TASK.read_active_checkout_session(store, self.repository)
            self.assertIsNotNone(active)
            self.assertEqual(active["base_sha"], session_base)
            self.assertEqual(active["process"]["pid"], supervisor.pid)

            result = self.cli(
                "open",
                "parallel after launcher exit",
                "--auto",
                "--agent",
                "custom",
                "--task",
                "parallel after launcher exit",
                "--",
                "sh",
                "-lc",
                (
                    "test ! -e active-after-session-start.txt && "
                    "printf 'K only\\n' > isolated-after-launcher.txt && "
                    "git add isolated-after-launcher.txt && "
                    "git commit -m 'feat: add isolated result after launcher exit'"
                ),
            )
            task = self.task_from(result)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(task["base_sha"], session_base)
            self.assertEqual(task["base_source"], "checkout_session_start")
        finally:
            if supervisor is not None:
                supervisor.wait(timeout=5)

        self.cli("reconcile", check=True)
        self.assertEqual((self.repository / "isolated-after-launcher.txt").read_text(), "K only\n")

    def test_symlinked_legacy_lock_is_refused_without_touching_its_target(self) -> None:
        important = self.repository.parent / "important.txt"
        important.write_text("must survive\n")
        (self.repository / ".ai-lock").symlink_to(important)

        with self.assertRaisesRegex(AGENT_TASK.AgentTaskError, "cannot safely open lock file"):
            with AGENT_TASK.checkout_session_lock(self.store(), self.repository):
                pass

        self.assertEqual(important.read_text(), "must survive\n")

    def test_live_legacy_session_is_detected_during_upgrade(self) -> None:
        legacy = self.repository / ".ai-lock"
        metadata = AGENT_TASK.checkout_session_metadata(self.repository, "legacy-session")
        legacy.write_text(json.dumps(metadata) + "\n")
        descriptor = os.open(legacy, os.O_RDWR)
        AGENT_TASK.fcntl.flock(descriptor, AGENT_TASK.fcntl.LOCK_EX)
        try:
            store = self.store()
            active = AGENT_TASK.read_active_checkout_session(store, self.repository)
            with AGENT_TASK.checkout_session_lock(store, self.repository) as reservation:
                self.assertFalse(reservation)
        finally:
            AGENT_TASK.fcntl.flock(descriptor, AGENT_TASK.fcntl.LOCK_UN)
            os.close(descriptor)

        self.assertEqual(active["base_sha"], metadata["base_sha"])

    def test_explicit_managed_task_does_not_inherit_the_current_feature(self) -> None:
        target_base = self.git("rev-parse", "main").stdout.strip()
        self.git("switch", "-c", "feature/current-agent")
        (self.repository / "feature-only.txt").write_text("J only\n")
        self.git("add", "feature-only.txt")
        self.git("commit", "-m", "feat: add feature-only work")

        result = self.cli(
            "start",
            "isolated explicit work",
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            "printf 'K only\n' > explicit-only.txt && git add explicit-only.txt && git commit -m 'feat: add explicit result'",
            check=True,
        )
        task = self.task_from(result)

        self.assertEqual(task["base_sha"], target_base)
        self.assertEqual(task["base_source"], "integration_target")
        self.assertEqual(self.git("show", "main:explicit-only.txt").stdout, "K only\n")
        self.assertNotEqual(self.git("show", "main:feature-only.txt", check=False).returncode, 0)
        self.assertEqual(self.git("show", "feature/current-agent:feature-only.txt").stdout, "J only\n")

    def test_open_new_uses_the_target_instead_of_the_current_feature(self) -> None:
        target_base = self.git("rev-parse", "main").stdout.strip()
        self.git("switch", "-c", "feature/open-new")
        (self.repository / "open-new-feature.txt").write_text("feature\n")
        self.git("add", "open-new-feature.txt")
        self.git("commit", "-m", "feat: add open-new feature")

        result = self.cli(
            "open",
            "new managed work",
            "--managed",
            "--new",
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            "printf 'managed\n' > open-new-result.txt && git add open-new-result.txt && git commit -m 'feat: add open-new result'",
            check=True,
        )
        task = self.task_from(result)

        self.assertEqual(task["base_sha"], target_base)
        self.assertNotEqual(self.git("show", "main:open-new-feature.txt", check=False).returncode, 0)
        self.assertEqual(self.git("show", "main:open-new-result.txt").stdout, "managed\n")

    def test_clean_commit_integrates_and_cleans(self) -> None:
        result = self.cli(
            "start",
            "add feature",
            "--agent",
            "custom",
            "--check",
            "test -f feature.txt",
            "--",
            "sh",
            "-lc",
            "printf 'ready\\n' > feature.txt && git add feature.txt && git commit -m 'feat: add feature'",
            check=True,
        )
        task = self.task_from(result)

        self.assertEqual(task["status"], "INTEGRATED")
        self.assertEqual((self.repository / "feature.txt").read_text(), "ready\n")
        self.assertFalse(Path(str(task["worktree_path"])).exists())
        self.assertFalse((self.state / "scratch" / str(task["task_id"])).exists())
        self.assertNotEqual(self.git("show-ref", "--verify", "--quiet", f"refs/heads/{task['branch']}", check=False).returncode, 0)
        self.assertEqual(self.git("log", "-1", "--format=%s", "main").stdout.strip(), "feat: add feature")
        self.assertEqual(task["integration_strategy"], "fast-forward")
        self.assertEqual(len(self.git("rev-list", "--parents", "-1", "main").stdout.split()), 2)

    def test_diverged_task_uses_a_meaningful_merge_message(self) -> None:
        result = self.cli(
            "start",
            "add divergent result",
            "--agent",
            "custom",
            "--no-integrate",
            "--",
            "sh",
            "-lc",
            "printf 'task\\n' > task-only.txt && git add task-only.txt && "
            "git commit -m 'feat: add divergent result'",
            check=True,
        )
        task = self.task_from(result)
        (self.repository / "target-only.txt").write_text("target\n")
        self.git("add", "target-only.txt")
        self.git("commit", "-m", "fix: advance target independently")

        self.cli("integrate", str(task["task_id"]), check=True)
        updated = json.loads((self.state / "tasks" / f"{task['task_id']}.json").read_text())
        message = self.git("show", "-s", "--format=%B", "main").stdout

        self.assertEqual(updated["integration_strategy"], "merge")
        self.assertEqual(len(self.git("rev-list", "--parents", "-1", "main").stdout.split()), 3)
        self.assertTrue(message.startswith("feat: add divergent result\n"), message)
        self.assertIn(f"작업 ID: {task['task_id']}", message)
        self.assertIn("feat: add divergent result", message)
        self.assertIn(f"{task['branch']} -> main", message)

    def test_equivalent_diverged_result_does_not_add_an_empty_merge(self) -> None:
        result = self.cli(
            "start",
            "add equivalent result",
            "--agent",
            "custom",
            "--no-integrate",
            "--",
            "sh",
            "-lc",
            "printf 'same\\n' > equivalent.txt && git add equivalent.txt && "
            "git commit -m 'feat: add equivalent result'",
            check=True,
        )
        task = self.task_from(result)
        (self.repository / "equivalent.txt").write_text("same\n")
        self.git("add", "equivalent.txt")
        self.git("commit", "-m", "feat: add equivalent target result")
        target_before = self.git("rev-parse", "main").stdout.strip()

        self.cli("integrate", str(task["task_id"]), check=True)
        updated = json.loads((self.state / "tasks" / f"{task['task_id']}.json").read_text())

        self.assertEqual(self.git("rev-parse", "main").stdout.strip(), target_before)
        self.assertEqual(updated["status"], AGENT_TASK.INTEGRATED)
        self.assertEqual(updated["integration_strategy"], "redundant")
        self.assertEqual(updated["integration_redundant_result"], task["result_commit"])
        self.assertNotEqual(
            self.git("show-ref", "--verify", "--quiet", f"refs/heads/{task['branch']}", check=False).returncode,
            0,
        )

    def test_successful_no_change_task_is_completed_and_cleaned(self) -> None:
        result = self.cli(
            "start",
            "read-only inspection",
            "--agent",
            "custom",
            "--",
            "true",
            check=True,
        )
        task = self.task_from(result)

        self.assertEqual(task["status"], AGENT_TASK.COMPLETED)
        self.assertFalse(Path(str(task["worktree_path"])).exists())
        self.assertFalse(self.git("show-ref", "--verify", "--quiet", f"refs/heads/{task['branch']}", check=False).returncode == 0)

    def test_successful_no_change_task_publishes_repository_memory(self) -> None:
        result = self.cli(
            "start",
            "record a read-only finding",
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            (
                "python -c \"import json; from pathlib import Path; "
                "p=Path('.ai-memory'); d=json.loads(p.read_text()); "
                "d['memories']['inspection.fact']={'summary':'Verified during read-only inspection.'}; "
                "p.write_text(json.dumps(d, indent=2, sort_keys=True) + '\\\\n')\""
            ),
            check=True,
        )
        task = self.task_from(result)
        memory = json.loads((self.repository / ".ai-memory").read_text())

        self.assertEqual(task["status"], AGENT_TASK.COMPLETED)
        self.assertEqual(
            memory["memories"]["inspection.fact"]["summary"],
            "Verified during read-only inspection.",
        )
        self.assertNotIn("memory_update", task)
        self.assertFalse(Path(str(task["worktree_path"])).exists())

    def test_validation_cannot_publish_files_it_mutates(self) -> None:
        result = self.cli(
            "start",
            "reject validation mutation",
            "--agent",
            "custom",
            "--no-integrate",
            "--check",
            "printf 'validated-only\n' > value.txt",
            "--",
            "sh",
            "-lc",
            "printf 'unvalidated\n' > value.txt && git add value.txt && git commit -m 'feat: add value'",
            check=True,
        )
        task = self.task_from(result)
        integrated = self.cli("integrate", str(task["task_id"]))
        updated = json.loads((self.state / "tasks" / f"{task['task_id']}.json").read_text())

        self.assertEqual(integrated.returncode, 2)
        self.assertEqual(updated["status"], AGENT_TASK.RECOVERY)
        self.assertIn("changed candidate files", updated["validation_failure"]["reason"])
        self.assertFalse((self.repository / "value.txt").exists())

    def test_validation_cannot_replace_the_candidate_commit(self) -> None:
        result = self.cli(
            "start",
            "reject validation head rewrite",
            "--agent",
            "custom",
            "--no-integrate",
            "--check",
            "git commit --amend -m 'tampered candidate'",
            "--",
            "sh",
            "-lc",
            "printf 'original\n' > original.txt && git add original.txt && git commit -m 'feat: add original'",
            check=True,
        )
        task = self.task_from(result)
        integrated = self.cli("integrate", str(task["task_id"]))
        updated = json.loads((self.state / "tasks" / f"{task['task_id']}.json").read_text())

        self.assertEqual(integrated.returncode, 2)
        self.assertIn("changed candidate HEAD", updated["validation_failure"]["reason"])
        self.assertFalse((self.repository / "original.txt").exists())

    def test_validation_timeout_preserves_the_result_without_integrating(self) -> None:
        result = self.cli(
            "start",
            "timeout validation",
            "--agent",
            "custom",
            "--no-integrate",
            "--check-timeout",
            "0.1",
            "--check",
            "sleep 5",
            "--",
            "sh",
            "-lc",
            "printf 'timeout\n' > timeout.txt && git add timeout.txt && git commit -m 'feat: add timeout result'",
            check=True,
        )
        task = self.task_from(result)
        started = time.monotonic()
        integrated = self.cli("integrate", str(task["task_id"]))
        elapsed = time.monotonic() - started
        updated = json.loads((self.state / "tasks" / f"{task['task_id']}.json").read_text())

        self.assertEqual(integrated.returncode, 2)
        self.assertLess(elapsed, 3)
        self.assertIn("exceeded 0.1 seconds", updated["validation_failure"]["reason"])
        self.assertFalse((self.repository / "timeout.txt").exists())

    def test_explicit_checks_run_from_the_original_relative_directory(self) -> None:
        nested = self.repository / "nested"
        nested.mkdir()
        (nested / ".keep").write_text("keep\n")
        self.git("add", "nested/.keep")
        self.git("commit", "-m", "chore: add nested directory")
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "start",
                "validate nested cwd",
                "--agent",
                "custom",
                "--check",
                'test "$(basename "$PWD")" = nested',
                "--",
                "sh",
                "-lc",
                "printf 'nested\n' > result.txt && git add result.txt && git commit -m 'feat: add nested result'",
            ],
            cwd=nested,
            env=self.cli_environment(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode:
            self.fail(f"nested task failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")

        self.assertEqual((self.repository / "nested" / "result.txt").read_text(), "nested\n")

    def test_forbidden_file_in_intermediate_commit_blocks_integration(self) -> None:
        secret = "never-copy-this-secret"
        result = self.cli(
            "start",
            "reject hidden memory history",
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            (
                f"printf '{secret}' > .ai-memory && git add -f .ai-memory && "
                "git commit -m 'chore: accidentally add memory' && "
                "git rm .ai-memory && git commit -m 'chore: remove memory' && "
                "printf 'code\n' > safe.txt && git add safe.txt && git commit -m 'feat: add safe code'"
            ),
        )
        task = self.task_from(result)
        serialized = (self.state / "tasks" / f"{task['task_id']}.json").read_text()

        self.assertEqual(result.returncode, 2)
        self.assertEqual(task["status"], AGENT_TASK.RECOVERY)
        self.assertIn(".ai-memory", task["status_reason"])
        self.assertNotIn(secret, serialized)
        self.assertFalse((self.repository / "safe.txt").exists())

    def test_tracked_legacy_lock_is_forbidden_too(self) -> None:
        result = self.cli(
            "start",
            "reject tracked lock",
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            "printf 'not metadata\n' > .ai-lock && git add -f .ai-lock && git commit -m 'chore: track lock'",
        )
        task = self.task_from(result)

        self.assertEqual(result.returncode, 2)
        self.assertIn(".ai-lock", task["status_reason"])
        self.assertNotEqual(self.git("cat-file", "-e", "main:.ai-lock", check=False).returncode, 0)

    def test_memory_selects_target_and_persists_general_knowledge(self) -> None:
        self.git("branch", "develop")
        memory = {
            "schema_version": 1,
            "settings": {"integration_target": "develop"},
            "memories": {
                "branching.strategy": {
                    "summary": "The repository uses Git Flow with develop as its integration branch."
                }
            },
        }
        (self.repository / ".ai-memory").write_text(json.dumps(memory, indent=2) + "\n")
        result = self.cli(
            "start",
            "record repository knowledge",
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            "python -c \"import json; from pathlib import Path; p=Path('.ai-memory'); d=json.loads(p.read_text()); d['memories']['deployment.stage']={'summary':'Stage deployments use the release MCP.','required_mcp_tools':['mcp__release__deploy']}; p.write_text(json.dumps(d, indent=2, sort_keys=True) + '\\\\n')\" && printf 'done\\n' > memory.txt && git add memory.txt && git commit -m 'feat: add memory test'",
            check=True,
        )
        task = self.task_from(result)
        updated = json.loads((self.repository / ".ai-memory").read_text())

        self.assertEqual(task["target_branch"], "develop")
        self.assertEqual(task["status"], "INTEGRATED")
        self.assertEqual(updated["memories"]["deployment.stage"]["required_mcp_tools"], ["mcp__release__deploy"])
        self.assertEqual(self.git("show", "develop:memory.txt").stdout, "done\n")
        self.assertNotEqual(self.git("show", "develop:.ai-memory", check=False).returncode, 0)

    def test_memory_three_way_merge_preserves_parallel_knowledge(self) -> None:
        base = AGENT_TASK.memory_template("main")
        current = json.loads(json.dumps(base))
        proposed = json.loads(json.dumps(base))
        current["memories"]["branching.strategy"] = {"summary": "Use short-lived branches."}
        proposed["memories"]["testing.command"] = {"summary": "Run make test."}
        overwrites: list[str] = []

        merged = AGENT_TASK.merge_memory(base, current, proposed, "", overwrites)
        self.assertEqual(overwrites, [])
        self.assertEqual(merged["memories"]["branching.strategy"]["summary"], "Use short-lived branches.")
        self.assertEqual(merged["memories"]["testing.command"]["summary"], "Run make test.")

        proposed["memories"]["branching.strategy"] = {"summary": "Use trunk-based development."}
        overwrites = []
        merged = AGENT_TASK.merge_memory(base, current, proposed, "", overwrites)
        self.assertEqual(overwrites, ["memories.branching.strategy"])
        self.assertEqual(merged["memories"]["branching.strategy"]["summary"], "Use trunk-based development.")

    def test_memory_entries_require_a_summary(self) -> None:
        memory = AGENT_TASK.memory_template("main")
        memory["memories"]["testing.command"] = {"details": "make test"}

        with self.assertRaisesRegex(AGENT_TASK.AgentTaskError, "non-empty summary"):
            AGENT_TASK.validate_memory(memory)

    def test_memory_update_waits_for_successful_code_integration(self) -> None:
        result = self.cli(
            "start",
            "defer memory with code",
            "--agent",
            "custom",
            "--no-integrate",
            "--",
            "sh",
            "-lc",
            "python -c \"import json; from pathlib import Path; p=Path('.ai-memory'); d=json.loads(p.read_text()); d['memories']['deferred.fact']={'summary':'Apply only with code.'}; p.write_text(json.dumps(d, indent=2, sort_keys=True) + '\\\\n')\" && printf 'code\n' > deferred.txt && git add deferred.txt && git commit -m 'feat: add deferred result'",
            check=True,
        )
        task = self.task_from(result)
        before = json.loads((self.repository / ".ai-memory").read_text())

        self.assertEqual(task["status"], AGENT_TASK.READY)
        self.assertIn("memory_update", task)
        self.assertNotIn("deferred.fact", before["memories"])

        self.cli("integrate", str(task["task_id"]), check=True)
        after = json.loads((self.repository / ".ai-memory").read_text())
        updated = json.loads((self.state / "tasks" / f"{task['task_id']}.json").read_text())
        self.assertEqual(after["memories"]["deferred.fact"]["summary"], "Apply only with code.")
        self.assertNotIn("memory_update", updated)

    def test_failed_validation_does_not_publish_memory(self) -> None:
        result = self.cli(
            "start",
            "reject memory with invalid code",
            "--agent",
            "custom",
            "--no-integrate",
            "--check",
            "false",
            "--",
            "sh",
            "-lc",
            "python -c \"import json; from pathlib import Path; p=Path('.ai-memory'); d=json.loads(p.read_text()); d['memories']['rejected.fact']={'summary':'Must not publish.'}; p.write_text(json.dumps(d, indent=2, sort_keys=True) + '\\\\n')\" && printf 'code\n' > rejected.txt && git add rejected.txt && git commit -m 'feat: add rejected result'",
            check=True,
        )
        task = self.task_from(result)

        integrated = self.cli("integrate", str(task["task_id"]))
        updated = json.loads((self.state / "tasks" / f"{task['task_id']}.json").read_text())
        canonical = json.loads((self.repository / ".ai-memory").read_text())

        self.assertEqual(integrated.returncode, 2)
        self.assertEqual(updated["status"], AGENT_TASK.RECOVERY)
        self.assertIn("memory_update", updated)
        self.assertNotIn("rejected.fact", canonical["memories"])

    def test_memory_race_does_not_retain_worktrees(self) -> None:
        environment = os.environ.copy()
        environment["AGENT_TASK_STATE_DIR"] = str(self.state)
        environment["GIT_CONFIG_GLOBAL"] = os.devnull
        environment["XDG_CONFIG_HOME"] = str(self.state / "xdg")
        environment.pop("SSH_AUTH_SOCK", None)
        first = subprocess.Popen(
            [
                sys.executable,
                str(SCRIPT),
                "start",
                "first memory writer",
                "--agent",
                "custom",
                "--",
                "sh",
                "-lc",
                "python -c \"import json; from pathlib import Path; p=Path('.ai-memory'); d=json.loads(p.read_text()); d['memories']['workflow.review']={'summary':'Use the first review workflow.'}; p.write_text(json.dumps(d, indent=2, sort_keys=True) + '\\\\n')\" && printf 'first\\n' > first.txt && git add first.txt && git commit -m 'feat: add first' && sleep 1",
            ],
            cwd=self.repository,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(100):
            entries = list((self.state / "tasks").glob("*.json")) if (self.state / "tasks").exists() else []
            if entries and json.loads(entries[0].read_text()).get("status") == "RUNNING":
                break
            time.sleep(0.02)
        else:
            first.kill()
            self.fail("first task did not start")

        second = self.cli(
            "start",
            "second memory writer",
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            "python -c \"import json; from pathlib import Path; p=Path('.ai-memory'); d=json.loads(p.read_text()); d['memories']['workflow.review']={'summary':'Use the second review workflow.'}; p.write_text(json.dumps(d, indent=2, sort_keys=True) + '\\\\n')\" && printf 'second\\n' > second.txt && git add second.txt && git commit -m 'feat: add second'",
        )
        self.assertEqual(second.returncode, 2)
        first_stdout, first_stderr = first.communicate(timeout=10)
        if first.returncode:
            self.fail(f"first task failed ({first.returncode})\nstdout:\n{first_stdout}\nstderr:\n{first_stderr}")

        self.cli("reconcile", check=True)
        tasks = {
            task["description"]: task
            for task in (json.loads(path.read_text()) for path in (self.state / "tasks").glob("*.json"))
        }
        first_task = tasks["first memory writer"]
        second_task = self.task_from(second)
        memory = json.loads((self.repository / ".ai-memory").read_text())

        self.assertEqual(first_task["status"], "INTEGRATED")
        self.assertNotIn("memory_overwrites", first_task)
        self.assertEqual(second_task["status"], "INTEGRATED")
        self.assertEqual(second_task["memory_overwrites"]["fields"], ["memories.workflow.review"])
        self.assertEqual(memory["memories"]["workflow.review"]["summary"], "Use the second review workflow.")
        self.assertFalse(Path(first_task["worktree_path"]).exists())
        self.assertFalse(Path(str(second_task["worktree_path"])).exists())

    def test_invalid_memory_is_recorded_without_blocking_code(self) -> None:
        result = self.cli(
            "start",
            "write invalid memory",
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            "printf '{invalid' > .ai-memory && printf 'done\\n' > valid.txt && git add valid.txt && git commit -m 'feat: add valid result'",
            check=True,
        )
        task = self.task_from(result)
        canonical = json.loads((self.repository / ".ai-memory").read_text())

        self.assertEqual(task["status"], "INTEGRATED")
        self.assertIn("memory_warning", task)
        self.assertIsNotNone(task["memory_proposal"]["fingerprint"])
        self.assertNotIn("{invalid", json.dumps(task))
        self.assertEqual(Path(task["memory_proposal"]["preserved_path"]).read_text(), "{invalid")
        self.assertEqual(canonical["schema_version"], 1)
        self.assertFalse(Path(str(task["worktree_path"])).exists())

    def test_unignored_memory_is_refused_and_removed(self) -> None:
        (self.repository / ".git/info/exclude").write_text("")
        result = self.cli(
            "start",
            "unsafe memory setup",
            "--agent",
            "custom",
            "--",
            "true",
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("is not ignored", result.stderr)
        self.assertFalse((self.repository / ".ai-memory").exists())

    def test_symlinked_memory_is_refused_without_overwriting_its_target(self) -> None:
        important = self.repository.parent / "important-memory-target.txt"
        important.write_text("must survive\n")
        (self.repository / ".ai-memory").symlink_to(important)

        result = self.cli("start", "unsafe memory link", "--agent", "custom", "--", "true")

        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot safely open", result.stderr)
        self.assertEqual(important.read_text(), "must survive\n")
        self.assertTrue((self.repository / ".ai-memory").is_symlink())

    def test_native_manual_worktree_memory_merges_back_to_primary(self) -> None:
        self.cli("open", "--auto", "--agent", "custom", "--", "true", check=True)
        manual = self.repository.parent / "manual-worktree"
        self.git("worktree", "add", "-b", "manual-memory", str(manual), "main")
        store = self.store()

        session = AGENT_TASK.prepare_native_repository_memory(store, self.repository, manual)
        local = json.loads((manual / ".ai-memory").read_text())
        local["memories"]["manual.worktree"] = {"summary": "Manual worktrees merge memory back."}
        AGENT_TASK.write_memory(manual / ".ai-memory", local)
        AGENT_TASK.finalize_native_repository_memory(store, session)
        canonical = json.loads((self.repository / ".ai-memory").read_text())

        self.assertTrue(session["secondary"])
        self.assertEqual(
            canonical["memories"]["manual.worktree"]["summary"],
            "Manual worktrees merge memory back.",
        )

    def test_dirty_exit_is_preserved(self) -> None:
        result = self.cli(
            "start",
            "leave work in progress",
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            "printf 'unfinished\\n' > draft.txt",
        )
        task = self.task_from(result)
        worktree = Path(str(task["worktree_path"]))

        self.assertEqual(result.returncode, 2)
        self.assertEqual(task["status"], "RECOVERY_REQUIRED")
        self.assertEqual((worktree / "draft.txt").read_text(), "unfinished\n")
        cleanup = self.cli("cleanup", str(task["task_id"]))
        self.assertEqual(cleanup.returncode, 2)
        self.assertTrue(worktree.exists())
        reconciled = self.cli("reconcile", "--quiet")
        self.assertEqual(reconciled.returncode, 2)
        self.assertIn("1 task(s) require recovery", reconciled.stderr)

    def test_open_resumes_the_only_interrupted_task(self) -> None:
        started = self.cli(
            "start",
            "resume this task",
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            "printf 'unfinished\n' > resumed.txt",
        )
        task = self.task_from(started)
        worktree = Path(str(task["worktree_path"]))

        resumed = self.cli(
            "open",
            "finish it",
            "--managed",
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            "git add resumed.txt && git commit -m 'feat: resume task'",
            check=True,
        )
        updated = json.loads((self.state / "tasks" / f"{task['task_id']}.json").read_text())

        self.assertIn(f"resuming: {task['task_id']}", resumed.stdout)
        self.assertEqual(updated["status"], "INTEGRATED")
        self.assertEqual((self.repository / "resumed.txt").read_text(), "unfinished\n")
        self.assertEqual(len(list((self.state / "tasks").glob("*.json"))), 1)
        self.assertEqual(worktree.parent.name, AGENT_TASK.repo_key(self.repository))
        self.assertTrue(worktree.parent.name.startswith("repo-"))

    def test_open_does_not_guess_between_interrupted_tasks_without_a_tty(self) -> None:
        for name in ("first", "second"):
            self.cli(
                "start",
                f"{name} interrupted task",
                "--agent",
                "custom",
                "--",
                "sh",
                "-lc",
                f"printf '{name}\\n' > {name}.txt",
            )

        opened = self.cli("open", "another instruction", "--managed", "--agent", "custom", "--", "true")

        self.assertEqual(opened.returncode, 2)
        self.assertIn("multiple interrupted tasks require a terminal selection", opened.stderr)
        self.assertEqual(len(list((self.state / "tasks").glob("*.json"))), 2)

    def test_reconcile_never_integrates_an_interrupted_clean_commit(self) -> None:
        started = self.cli(
            "start",
            "commit before interruption",
            "--agent",
            "custom",
            "--no-integrate",
            "--",
            "sh",
            "-lc",
            "printf 'checkpoint\n' > checkpoint.txt && git add checkpoint.txt && git commit -m 'chore: checkpoint'",
            check=True,
        )
        task = self.task_from(started)
        task_path = self.state / "tasks" / f"{task['task_id']}.json"
        task["status"] = "RUNNING"
        task["process"] = {"pid": 99999999, "start": "missing"}
        task.pop("integrated_commit", None)
        task_path.write_text(json.dumps(task, indent=2, sort_keys=True) + "\n")

        reconciled = self.cli("reconcile", "--quiet")
        updated = json.loads(task_path.read_text())

        self.assertEqual(reconciled.returncode, 2)
        self.assertEqual(updated["status"], "RECOVERY_REQUIRED")
        self.assertIn("interrupted_at", updated)
        self.assertFalse((self.repository / "checkpoint.txt").exists())
        self.assertFalse(updated.get("integrated_commit"))

    def test_native_recovery_commands_reuse_the_task_working_directory(self) -> None:
        codex = AGENT_TASK.default_recovery_command("codex", "continue")
        claude = AGENT_TASK.default_recovery_command("claude", "continue")

        self.assertEqual(codex[:3], ["codex", "resume", "--last"])
        self.assertIn("--continue", claude)

    def test_conflict_recreates_worktree_only_for_recovery(self) -> None:
        started = self.cli(
            "start",
            "change shared file",
            "--agent",
            "custom",
            "--no-integrate",
            "--",
            "sh",
            "-lc",
            "printf 'task\\n' > shared.txt && git add shared.txt && git commit -m 'feat: change shared'",
            check=True,
        )
        task = self.task_from(started)
        (self.repository / "shared.txt").write_text("target\n")
        self.git("add", "shared.txt")
        self.git("commit", "-m", "fix: change target")

        integrated = self.cli("integrate", str(task["task_id"]))
        updated = json.loads((self.state / "tasks" / f"{task['task_id']}.json").read_text())
        self.assertEqual(integrated.returncode, 2)
        self.assertEqual(updated["status"], "RECOVERY_REQUIRED")
        self.assertFalse(Path(str(updated["worktree_path"])).exists())
        self.assertEqual(
            self.git("show-ref", "--verify", "--quiet", f"refs/heads/{updated['branch']}", check=False).returncode,
            0,
        )
        self.assertEqual((self.repository / "shared.txt").read_text(), "target\n")

        self.cli(
            "recover",
            str(task["task_id"]),
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            "printf 'resolved\\n' > shared.txt && git add shared.txt && git commit -m 'fix: resolve shared conflict'",
            check=True,
        )
        recovered = json.loads((self.state / "tasks" / f"{task['task_id']}.json").read_text())
        self.assertEqual(recovered["status"], "INTEGRATED")
        self.assertEqual((self.repository / "shared.txt").read_text(), "resolved\n")
        self.assertFalse(Path(str(recovered["worktree_path"])).exists())

    def test_ignored_build_artifact_is_recorded_and_cleaned_after_success(self) -> None:
        result = self.cli(
            "start",
            "create an ignored build artifact",
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            "printf 'done\\n' > result.txt && git add result.txt && git commit -m 'feat: add result' && mkdir .agent-cache && touch .agent-cache/output",
        )
        task = self.task_from(result)
        worktree = Path(str(task["worktree_path"]))

        self.assertEqual(result.returncode, 0)
        self.assertEqual(task["status"], AGENT_TASK.INTEGRATED)
        self.assertTrue(task.get("integrated_commit"))
        self.assertEqual(task["discarded_ignored_artifacts"]["count"], 1)
        self.assertFalse(worktree.exists())
        self.assertEqual((self.repository / "result.txt").read_text(), "done\n")
        self.assertNotEqual(
            self.git("show-ref", "--verify", "--quiet", f"refs/heads/{task['branch']}", check=False).returncode,
            0,
        )

    def test_tracked_memory_never_reaches_target(self) -> None:
        result = self.cli(
            "start",
            "try to commit repository memory",
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            "git add -f .ai-memory && git commit -m 'chore: track memory'",
        )
        task = self.task_from(result)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(task["status"], "RECOVERY_REQUIRED")
        self.assertIn("forbidden paths: .ai-memory", task["status_reason"])
        self.assertFalse(Path(str(task["worktree_path"])).exists())
        self.assertNotEqual(self.git("cat-file", "-e", "main:.ai-memory", check=False).returncode, 0)
        self.assertEqual(
            self.git("show-ref", "--verify", "--quiet", f"refs/heads/{task['branch']}", check=False).returncode,
            0,
        )

    def test_no_integrate_survives_reconcile_until_explicit_integration(self) -> None:
        result = self.cli(
            "start",
            "queue a committed task",
            "--agent",
            "custom",
            "--no-integrate",
            "--",
            "sh",
            "-lc",
            "printf 'queued\\n' > queued.txt && git add queued.txt && git commit -m 'feat: queue result'",
            check=True,
        )
        task = self.task_from(result)
        self.assertEqual(task["status"], "READY_TO_INTEGRATE")
        self.assertFalse(Path(str(task["worktree_path"])).exists())

        self.cli("reconcile", check=True)
        updated = json.loads((self.state / "tasks" / f"{task['task_id']}.json").read_text())
        self.assertEqual(updated["status"], AGENT_TASK.READY)
        self.assertFalse(updated["auto_integrate"])
        self.assertFalse((self.repository / "queued.txt").exists())
        self.assertFalse(Path(str(updated["worktree_path"])).exists())
        self.cli("integrate", str(task["task_id"]), check=True)
        self.assertEqual((self.repository / "queued.txt").read_text(), "queued\n")

    def test_recovery_preserves_a_task_no_integrate_policy(self) -> None:
        started = self.cli(
            "start",
            "recover without auto integration",
            "--agent",
            "custom",
            "--no-integrate",
            "--",
            "sh",
            "-lc",
            "printf 'draft\n' > recovered-policy.txt",
        )
        task = self.task_from(started)
        recovered = self.cli(
            "recover",
            str(task["task_id"]),
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            "git add recovered-policy.txt && git commit -m 'feat: finish recovered policy'",
            check=True,
        )
        updated = json.loads((self.state / "tasks" / f"{task['task_id']}.json").read_text())

        self.assertEqual(updated["status"], AGENT_TASK.READY)
        self.assertFalse(updated["auto_integrate"])
        self.assertFalse((self.repository / "recovered-policy.txt").exists())
        self.cli("reconcile", check=True)
        self.assertFalse((self.repository / "recovered-policy.txt").exists())
        self.cli("integrate", str(task["task_id"]), check=True)
        self.assertEqual((self.repository / "recovered-policy.txt").read_text(), "draft\n")

    def test_target_rewind_is_refused_without_reintroducing_removed_history(self) -> None:
        (self.repository / "removed-target-history.txt").write_text("target commit\n")
        self.git("add", "removed-target-history.txt")
        self.git("commit", "-m", "chore: add target history")
        rewound_to = self.git("rev-parse", "HEAD^").stdout.strip()

        result = self.cli(
            "start",
            "result based on rewound history",
            "--agent",
            "custom",
            "--no-integrate",
            "--",
            "sh",
            "-lc",
            "printf 'result\n' > rewind-result.txt && git add rewind-result.txt && git commit -m 'feat: add rewind result'",
            check=True,
        )
        task = self.task_from(result)
        self.git("reset", "--hard", rewound_to)

        integrated = self.cli("integrate", str(task["task_id"]))
        updated = json.loads((self.state / "tasks" / f"{task['task_id']}.json").read_text())

        self.assertEqual(integrated.returncode, 2)
        self.assertEqual(updated["status"], AGENT_TASK.RECOVERY)
        self.assertIn("no longer descends", updated["status_reason"])
        self.assertNotEqual(self.git("show", "main:removed-target-history.txt", check=False).returncode, 0)
        self.assertNotEqual(self.git("show", "main:rewind-result.txt", check=False).returncode, 0)

    def test_target_checkout_switch_during_validation_is_queued(self) -> None:
        marker = self.repository.parent / "validation-started"
        release = self.repository.parent / "release-validation"
        self.git("switch", "-c", "feature/switch-during-validation")
        check_command = (
            f"touch {shlex.quote(str(marker))}; "
            f"while [ ! -e {shlex.quote(str(release))} ]; do sleep 0.02; done"
        )
        result = self.cli(
            "start",
            "guard target topology",
            "--agent",
            "custom",
            "--no-integrate",
            "--check",
            check_command,
            "--",
            "sh",
            "-lc",
            "printf 'guarded\n' > topology-result.txt && git add topology-result.txt && git commit -m 'feat: add topology result'",
            check=True,
        )
        task = self.task_from(result)
        integrator = subprocess.Popen(
            [sys.executable, str(SCRIPT), "integrate", str(task["task_id"])],
            cwd=self.repository,
            env=self.cli_environment(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(250):
            if marker.exists():
                break
            if integrator.poll() is not None:
                stdout, stderr = integrator.communicate()
                self.fail(f"integration ended before validation switch\nstdout:\n{stdout}\nstderr:\n{stderr}")
            time.sleep(0.02)
        else:
            integrator.kill()
            self.fail("validation did not start")

        self.git("switch", "main")
        release.touch()
        stdout, stderr = integrator.communicate(timeout=10)
        updated = json.loads((self.state / "tasks" / f"{task['task_id']}.json").read_text())

        self.assertEqual(integrator.returncode, 2, f"stdout:\n{stdout}\nstderr:\n{stderr}")
        self.assertEqual(updated["status"], AGENT_TASK.READY)
        self.assertIn("topology changed", updated["status_reason"])
        self.assertFalse((self.repository / "topology-result.txt").exists())

        self.cli("integrate", str(task["task_id"]), check=True)
        self.assertEqual((self.repository / "topology-result.txt").read_text(), "guarded\n")

    def test_reconcile_recovers_a_killed_validation_parent_and_child(self) -> None:
        marker = self.repository.parent / "crash-validation-started"
        release = self.repository.parent / "never-release-validation"
        check_command = (
            f"touch {shlex.quote(str(marker))}; "
            f"while [ ! -e {shlex.quote(str(release))} ]; do sleep 0.02; done"
        )
        result = self.cli(
            "start",
            "recover killed integration",
            "--agent",
            "custom",
            "--no-integrate",
            "--check",
            check_command,
            "--",
            "sh",
            "-lc",
            "printf 'recovered\n' > crash-result.txt && git add crash-result.txt && git commit -m 'feat: add crash result'",
            check=True,
        )
        task = self.task_from(result)
        task_path = self.state / "tasks" / f"{task['task_id']}.json"
        integrator = subprocess.Popen(
            [sys.executable, str(SCRIPT), "integrate", str(task["task_id"])],
            cwd=self.repository,
            env=self.cli_environment(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(250):
            if marker.exists():
                snapshot = json.loads(task_path.read_text())
                if snapshot.get("status") == AGENT_TASK.VALIDATING and snapshot.get("validation_process"):
                    break
            if integrator.poll() is not None:
                stdout, stderr = integrator.communicate()
                self.fail(f"integration ended before crash injection\nstdout:\n{stdout}\nstderr:\n{stderr}")
            time.sleep(0.02)
        else:
            integrator.kill()
            self.fail("validation process metadata did not appear")

        validation_process = snapshot["validation_process"]
        candidate = Path(snapshot["integration_candidate"])
        integrator.kill()
        integrator.wait(timeout=5)
        snapshot["checks"] = []
        task_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")

        self.cli("reconcile", check=True)
        integrator.communicate(timeout=5)
        updated = json.loads(task_path.read_text())

        self.assertEqual(updated["status"], AGENT_TASK.INTEGRATED)
        self.assertFalse(AGENT_TASK.process_alive(validation_process))
        self.assertFalse(candidate.exists())
        self.assertNotIn("integration_process", updated)
        self.assertNotIn("validation_process", updated)
        self.assertEqual((self.repository / "crash-result.txt").read_text(), "recovered\n")

    def test_legacy_transient_state_requires_explicit_integration(self) -> None:
        result = self.cli(
            "start",
            "preserve legacy transient state",
            "--agent",
            "custom",
            "--no-integrate",
            "--",
            "sh",
            "-lc",
            "printf 'legacy\n' > legacy-result.txt && git add legacy-result.txt && git commit -m 'feat: add legacy result'",
            check=True,
        )
        task = self.task_from(result)
        task_path = self.state / "tasks" / f"{task['task_id']}.json"
        task["status"] = AGENT_TASK.VALIDATING
        task.pop("integration_process", None)
        task_path.write_text(json.dumps(task, indent=2, sort_keys=True) + "\n")

        reconciled = self.cli("reconcile", "--quiet")
        preserved = json.loads(task_path.read_text())

        self.assertEqual(reconciled.returncode, 2)
        self.assertEqual(preserved["status"], AGENT_TASK.RECOVERY)
        self.assertTrue(preserved["legacy_integration_interrupted"])
        self.assertFalse((self.repository / "legacy-result.txt").exists())

        self.cli("integrate", str(task["task_id"]), check=True)
        self.assertEqual((self.repository / "legacy-result.txt").read_text(), "legacy\n")

    def test_reconcile_closes_a_legacy_record_whose_result_is_already_on_target(self) -> None:
        result = self.cli(
            "start",
            "recognize an already applied legacy result",
            "--agent",
            "custom",
            "--no-integrate",
            "--",
            "sh",
            "-lc",
            "printf 'already applied\n' > applied.txt && git add applied.txt && git commit -m 'feat: add applied result'",
            check=True,
        )
        task = self.task_from(result)
        task_path = self.state / "tasks" / f"{task['task_id']}.json"
        self.git("merge", "--no-ff", "-m", "chore: apply result outside harness", task["result_commit"])
        task["status"] = AGENT_TASK.RECOVERY
        task["legacy_integration_interrupted"] = True
        task["status_reason"] = "legacy interrupted integration has no owner metadata"
        task_path.write_text(json.dumps(task, indent=2, sort_keys=True) + "\n")

        self.cli("reconcile", "--quiet", check=True)
        updated = json.loads(task_path.read_text())

        self.assertEqual(updated["status"], AGENT_TASK.INTEGRATED)
        self.assertNotIn("legacy_integration_interrupted", updated)
        self.assertNotEqual(
            self.git("show-ref", "--verify", "--quiet", f"refs/heads/{task['branch']}", check=False).returncode,
            0,
        )

    def test_task_lock_blocks_overlapping_integration(self) -> None:
        result = self.cli(
            "start",
            "queue a locked task",
            "--agent",
            "custom",
            "--no-integrate",
            "--",
            "sh",
            "-lc",
            "printf 'locked\\n' > locked.txt && git add locked.txt && git commit -m 'feat: add locked result'",
            check=True,
        )
        task = self.task_from(result)

        with mock.patch.dict(os.environ, {"AGENT_TASK_STATE_DIR": str(self.state)}):
            store = AGENT_TASK.Store()
            with store.lock(f"task:{task['task_id']}"):
                blocked = self.cli("integrate", str(task["task_id"]))

        self.assertEqual(blocked.returncode, 2)
        self.assertIn("operation already running", blocked.stderr)
        self.cli("integrate", str(task["task_id"]), check=True)
        self.assertEqual((self.repository / "locked.txt").read_text(), "locked\n")

    def test_managed_agent_can_work_in_another_repository(self) -> None:
        dependency = self.repository.parent / "dependency"
        self.git("init", "-b", "main", str(dependency), cwd=self.repository.parent)
        self.git("config", "user.name", "Test Agent", cwd=dependency)
        self.git("config", "user.email", "agent@example.com", cwd=dependency)
        self.git("config", "commit.gpgsign", "false", cwd=dependency)
        (dependency / "dependency.txt").write_text("base\n")
        self.git("add", "dependency.txt", cwd=dependency)
        self.git("commit", "-m", "base", cwd=dependency)

        dependency_argument = shlex.quote(str(dependency))
        dependency_file = shlex.quote(str(dependency / "dependency.txt"))
        result = self.cli(
            "start",
            "update two repositories",
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            (
                "printf 'primary\\n' > primary.txt && "
                "git add primary.txt && git commit -m 'feat: update primary' && "
                f"git -C {dependency_argument} switch -c cross-repo-change && "
                f"printf 'dependency\\n' > {dependency_file} && "
                f"git -C {dependency_argument} add dependency.txt && "
                f"git -C {dependency_argument} commit -m 'feat: update dependency'"
            ),
            check=True,
        )
        task = self.task_from(result)

        self.assertEqual(task["status"], "INTEGRATED")
        self.assertEqual((self.repository / "primary.txt").read_text(), "primary\n")
        self.assertEqual((dependency / "dependency.txt").read_text(), "dependency\n")
        self.assertEqual(self.git("branch", "--show-current", cwd=dependency).stdout.strip(), "cross-repo-change")
        self.assertEqual(
            self.git("log", "-1", "--format=%s", cwd=dependency).stdout.strip(),
            "feat: update dependency",
        )


if __name__ == "__main__":
    unittest.main()

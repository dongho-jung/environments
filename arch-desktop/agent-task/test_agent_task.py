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
import signal
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

    def test_pending_codex_reserves_its_future_worktree_without_a_branch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            origin = root / "original" / "nested"
            worktree = root / "worktree"
            origin.mkdir(parents=True)
            worktree.mkdir()
            task = {
                "task_id": "20260828-180610-d84970",
                "worktree_path": str(worktree),
                "workdir_relative": "nested",
                "origin_working_directory": str(origin),
                "branch": None,
                "target_branch": "main",
                "agent": "codex",
                "worktree_state": AGENT_TASK.WORKTREE_PENDING,
            }

            command = AGENT_TASK.managed_agent_command(
                task,
                ["codex", "--dangerously-bypass-approvals-and-sandbox"],
            )
            repeated = AGENT_TASK.managed_agent_command(task, command)
            with mock.patch.dict(os.environ, {"AI_TASK_BRANCH": "stale"}, clear=False):
                environment = AGENT_TASK.task_environment(task)

        self.assertEqual(command, repeated)
        self.assertIn("--add-dir", command)
        self.assertIn(str(worktree), command)
        self.assertNotIn("--dangerously-bypass-hook-trust", command)
        self.assertNotIn("AI_TASK_BRANCH", environment)
        self.assertEqual(environment["AI_TASK_WORKDIR"], str(worktree / "nested"))

    def test_pending_codex_reload_preserves_hook_provisioning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            worktree = Path(directory) / "worktree"
            origin = Path(directory) / "origin"
            worktree.mkdir()
            origin.mkdir()
            task = {
                "task_id": "20260828-180610-d84970",
                "worktree_path": str(worktree),
                "workdir_relative": ".",
                "origin_working_directory": str(origin),
                "branch": None,
                "target_branch": "main",
                "agent": "codex",
                "worktree_state": AGENT_TASK.WORKTREE_PENDING,
            }
            registry: dict[str, object] = {}
            store = mock.Mock()

            def save(value: dict[str, object]) -> None:
                registry.clear()
                registry.update(value)

            def wait() -> int:
                registry["branch"] = "fix-login"
                registry["worktree_state"] = AGENT_TASK.WORKTREE_READY
                registry["provisioning_slug"] = "fix-login"
                return 0

            store.save.side_effect = save
            store.load.side_effect = lambda _task_id: dict(registry)
            process = mock.Mock(pid=12345)
            process.wait.side_effect = wait

            with (
                mock.patch.object(AGENT_TASK.subprocess, "Popen", return_value=process),
                mock.patch.object(AGENT_TASK, "process_start", return_value="start"),
            ):
                exit_code = AGENT_TASK.launch_agent(
                    store,
                    task,
                    ["codex", "--dangerously-bypass-approvals-and-sandbox"],
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(task["branch"], "fix-login")
        self.assertEqual(task["worktree_state"], AGENT_TASK.WORKTREE_READY)

    def test_interactive_codex_sigint_is_recorded_as_graceful(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            task = {
                "task_id": "codex-sigint",
                "worktree_path": directory,
                "workdir_relative": ".",
                "origin_working_directory": directory,
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

    def test_launchers_always_use_quiet_managed_worktrees(self) -> None:
        configuration = SCRIPT.parent.parent.joinpath("agent-task.tf").read_text()
        claude_settings = json.loads(SCRIPT.parent.parent.joinpath("claude/settings.json").read_text())

        self.assertIn('if [[ "$${1-}" == "--local" ]]', configuration)
        self.assertIn('if [[ "$${1-}" == "resume" ]]', configuration)
        self.assertIn('if [[ "$${1-}" == "--new" ]]', configuration)
        self.assertNotIn('if [[ "$${1-}" == "--task" ]]', configuration)
        self.assertIn("agent-task open --quiet --agent codex", configuration)
        self.assertIn("agent-task open --quiet --new --agent codex", configuration)
        self.assertIn("agent-task resume --quiet --agent codex", configuration)
        self.assertIn("agent-task open --quiet --agent claude", configuration)
        self.assertIn("agent-task open --quiet --new --agent claude", configuration)
        self.assertIn("agent-task open --quiet --fresh --agent codex", configuration)
        self.assertNotIn("agent-task open --auto", configuration)
        self.assertNotIn("agent-task open --managed", configuration)
        self.assertIn("exec|e|apply|a|fork|cloud|cloud-tasks|sandbox", configuration)
        self.assertIn("--require-current", configuration)
        self.assertIn("agent-task resume --quiet --agent codex --", configuration)
        self.assertIn("review|resume|apply", configuration)
        self.assertIn("agents|attach|logs|stop|rm)", configuration)
        self.assertIn("claude_owns_lifecycle", configuration)
        self.assertNotIn("require explicit c --local", configuration)
        self.assertIn("tui.show_tooltips=false", configuration)
        self.assertIn('command codex "$${codex_tui[@]}"', configuration)
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
            'tui.status_line=["current-dir","thread-title","model-with-reasoning"]',
        )
        self.assertEqual(AGENT_TASK.CODEX_PENDING_THREAD_NAME, "\u200b")
        self.assertEqual(AGENT_TASK.CODEX_SHOW_TOOLTIPS_CONFIG, "tui.show_tooltips=false")
        self.assertIn('"thread/name/set"', SCRIPT.read_text())
        self.assertNotIn('"task-progress"', AGENT_TASK.CODEX_STATUS_LINE_CONFIG)
        kitty_configuration = SCRIPT.parent.parent.joinpath("kitty/kitty.conf").read_text()
        self.assertNotIn("tab_bar_min_tabs 1", kitty_configuration)
        self.assertNotIn('tab_title_template " {title} "', kitty_configuration)
        self.assertNotIn("tui.terminal_title", SCRIPT.read_text())

    def test_repository_memory_has_no_checkout_mode(self) -> None:
        memory = AGENT_TASK.memory_template("main")
        self.assertEqual(memory["settings"], {"integration_target": "main"})
        help_text = AGENT_TASK.build_parser().format_help()
        self.assertNotIn("agent_task_mode", help_text)

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
            [Path("/repo")],
        )
        resumed = AGENT_TASK.codex_remote_command(
            ["codex", "resume", "--last"], socket, [Path("/repo")]
        )
        review = AGENT_TASK.codex_remote_command(
            ["codex", "review", "--uncommitted"], socket, [Path("/repo")]
        )

        prefix = [
            "codex",
            "--remote",
            f"unix://{socket}",
            "-c",
            'projects={"/repo"={trust_level="trusted"}}',
            "-c",
            AGENT_TASK.CODEX_SHOW_TOOLTIPS_CONFIG,
            "-c",
            AGENT_TASK.CODEX_STATUS_LINE_CONFIG,
        ]
        self.assertEqual(opened[:9], prefix)
        self.assertEqual(resumed[:10], [*prefix, "resume"])
        self.assertIsNone(review)

    def test_pending_title_bootstrap_only_wraps_a_fresh_promptless_tui(self) -> None:
        self.assertTrue(
            AGENT_TASK.fresh_interactive_codex_command(
                ["codex", "-c", 'model="gpt-5.6"', "--dangerously-bypass-approvals-and-sandbox"]
            )
        )
        self.assertTrue(AGENT_TASK.fresh_interactive_codex_command(["env", "MODE=test", "codex"]))
        self.assertFalse(AGENT_TASK.fresh_interactive_codex_command(["codex", "work here"]))
        self.assertFalse(AGENT_TASK.fresh_interactive_codex_command(["codex", "resume", "thread-one"]))
        self.assertFalse(AGENT_TASK.fresh_interactive_codex_command(["codex", "fork", "thread-one"]))
        self.assertFalse(AGENT_TASK.fresh_interactive_codex_command(["codex", "--help"]))
        self.assertFalse(AGENT_TASK.fresh_interactive_codex_command(["codex", "-V"]))
        self.assertFalse(AGENT_TASK.fresh_interactive_codex_command(["codex", "--"]))

    def test_pending_title_bootstrap_resumes_the_pre_named_thread(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            socket = Path(directory) / "control.sock"
            environment = os.environ.copy()
            environment["AI_TASK_HARNESS"] = "agent-task"
            environment["AI_TASK_ID"] = "task-one"
            environment.pop("AI_TASK_BRANCH", None)

            def fork() -> int:
                socket.touch()
                return 12345

            with (
                mock.patch.dict(os.environ, environment, clear=True),
                mock.patch.object(AGENT_TASK.os, "fork", side_effect=fork),
                mock.patch.object(
                    AGENT_TASK,
                    "start_named_codex_thread",
                    return_value="thread-one",
                ) as start_thread,
            ):
                started = AGENT_TASK.start_codex_app_server(
                    ["codex", "--dangerously-bypass-approvals-and-sandbox"],
                    socket,
                    (),
                    [Path("/repo")],
                )

        assert started is not None
        server_pid, command = started
        self.assertEqual(server_pid, 12345)
        self.assertEqual(command[-2:], ["resume", "thread-one"])
        start_thread.assert_called_once_with(
            socket,
            Path.cwd(),
            AGENT_TASK.CODEX_PENDING_THREAD_NAME,
        )

    def test_managed_codex_replaces_stale_launcher_footer_configs(self) -> None:
        stale_status = 'tui.status_line=["current-dir","task-progress"]'
        command = AGENT_TASK.codex_remote_command(
            [
                "codex",
                "-c",
                stale_status,
                "--config=tui.show_tooltips=true",
                "-c",
                'model="gpt-5.6"',
                "inspect this",
            ],
            Path("/state/controls/session.sock"),
            [Path("/repo")],
        )

        assert command is not None
        self.assertNotIn(stale_status, command)
        self.assertNotIn("--config=tui.show_tooltips=true", command)
        self.assertEqual(command.count(AGENT_TASK.CODEX_STATUS_LINE_CONFIG), 1)
        self.assertEqual(command.count(AGENT_TASK.CODEX_SHOW_TOOLTIPS_CONFIG), 1)
        self.assertIn('model="gpt-5.6"', command)

    def test_codex_app_server_owns_the_first_prompt_provisioning_hook(self) -> None:
        socket = Path("/state/controls/session.sock")
        hook = AGENT_TASK.codex_provision_hook_config()
        cow_hook = AGENT_TASK.codex_cow_hook_config()

        pending = AGENT_TASK.codex_app_server_command(
            ["codex", "--add-dir", "/state/worktree"],
            socket,
            provision_hook=True,
        )
        ready = AGENT_TASK.codex_app_server_command(
            ["codex", "--add-dir", "/state/worktree"],
            socket,
            provision_hook=False,
        )

        self.assertEqual(
            pending,
            [
                "codex",
                "--dangerously-bypass-hook-trust",
                "-c",
                hook,
                "-c",
                cow_hook,
                "app-server",
                "--listen",
                f"unix://{socket}",
            ],
        )
        self.assertEqual(ready, ["codex", "app-server", "--listen", f"unix://{socket}"])
        self.assertIn(AGENT_TASK.PROVISION_HOOK_SUBCOMMAND, hook)
        self.assertIn("PreToolUse", cow_hook)
        self.assertIn("Bash|apply_patch", cow_hook)

    def test_codex_hooks_preserve_the_stable_launcher_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            version = root / "versions" / "version-one"
            version.parent.mkdir()
            version.touch()
            launcher = root / "bin" / "agent-task"
            launcher.parent.mkdir()
            launcher.symlink_to(version)

            with mock.patch.object(AGENT_TASK, "__file__", str(launcher)):
                hook = AGENT_TASK.codex_provision_hook_config()
                cow_hook = AGENT_TASK.codex_cow_hook_config()

        expected = shlex.join(
            [sys.executable, str(launcher), AGENT_TASK.PROVISION_HOOK_SUBCOMMAND]
        )
        self.assertIn(json.dumps(expected), hook)
        self.assertIn(json.dumps(expected), cow_hook)
        self.assertNotIn(str(version), hook)

    def test_codex_trusted_projects_config_is_stable_and_quoted(self) -> None:
        self.assertEqual(
            AGENT_TASK.codex_trusted_projects_config(
                [Path('/repo/with "quotes"'), Path("/repo/with spaces"), Path("/repo/with spaces")]
            ),
            'projects={"/repo/with \\"quotes\\""={trust_level="trusted"},'
            '"/repo/with spaces"={trust_level="trusted"}}',
        )

    def test_codex_app_server_inherits_handoff_session_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session_path = root / "session.json"
            observed: dict[str, str | None] = {}

            def start_server(*_args: object) -> None:
                observed["id"] = os.environ.get(AGENT_TASK.AGENT_SESSION_ID_ENV)
                observed["path"] = os.environ.get(AGENT_TASK.AGENT_SESSION_PATH_ENV)
                return None

            environment = {
                AGENT_TASK.LOCK_FDS_ENV: "9",
                AGENT_TASK.LOCK_SESSION_PATH_ENV: str(session_path),
                AGENT_TASK.LOCK_SESSION_ID_ENV: "session-one",
            }
            metadata = {
                "working_directory": str(root),
                "control_socket": str(root / "control.sock"),
            }
            with (
                mock.patch.dict(os.environ, environment, clear=True),
                mock.patch.object(AGENT_TASK, "become_child_subreaper"),
                mock.patch.object(AGENT_TASK, "transfer_checkout_session_owner"),
                mock.patch.object(AGENT_TASK, "read_json_file_safely", return_value=metadata),
                mock.patch.object(AGENT_TASK, "Store", return_value=mock.Mock()),
                mock.patch.object(
                    AGENT_TASK,
                    "start_codex_app_server",
                    side_effect=start_server,
                ),
                mock.patch.object(AGENT_TASK.os, "fork", side_effect=OSError("stop")),
            ):
                with self.assertRaisesRegex(AGENT_TASK.AgentTaskError, "cannot start supervised agent"):
                    AGENT_TASK.command_lock_exec(["--", "codex"])

        self.assertEqual(observed["id"], "session-one")
        self.assertEqual(observed["path"], str(session_path))

    def test_codex_tui_shows_branch_route_without_task_count(self) -> None:
        self.assertIn('"current-dir"', AGENT_TASK.CODEX_STATUS_LINE_CONFIG)
        self.assertIn('"thread-title"', AGENT_TASK.CODEX_STATUS_LINE_CONFIG)
        self.assertNotIn('"fast-mode"', AGENT_TASK.CODEX_STATUS_LINE_CONFIG)
        self.assertNotIn('"task-progress"', AGENT_TASK.CODEX_STATUS_LINE_CONFIG)
        self.assertIn('"thread/name/set"', SCRIPT.read_text())

    def test_codex_task_slug_uses_an_ephemeral_luna_turn(self) -> None:
        class FakeSocket:
            def __init__(self) -> None:
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
                elif method == "thread/start":
                    result = {"thread": {"id": "slug-thread"}}
                elif method == "turn/start":
                    result = {"turn": {"id": "slug-turn"}}
                else:
                    raise AssertionError(method)
                self.responses.append(json.dumps({"id": request["id"], "result": result}))
                if method == "turn/start":
                    self.responses.extend(
                        (
                            json.dumps(
                                {
                                    "method": "item/completed",
                                    "params": {
                                        "item": {
                                            "id": "message",
                                            "text": (
                                                '{"slug":"status-line-fix",'
                                                '"requires_worktree":false}'
                                            ),
                                            "type": "agentMessage",
                                        },
                                        "threadId": "slug-thread",
                                        "turnId": "slug-turn",
                                    },
                                }
                            ),
                            json.dumps(
                                {
                                    "method": "turn/completed",
                                    "params": {
                                        "threadId": "slug-thread",
                                        "turn": {"id": "slug-turn", "status": "completed"},
                                    },
                                }
                            ),
                        )
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
        intent = AGENT_TASK.generate_codex_task_intent(
            Path("/control.sock"),
            "상태 표시줄을 짧게 정리해줘",
            connector=lambda: FakeConnection(socket),
        )

        self.assertEqual(intent, ("status-line-fix", False))
        thread_start = next(
            request for request in socket.requests if request.get("method") == "thread/start"
        )
        self.assertEqual(thread_start["params"]["model"], "gpt-5.6-luna")
        self.assertEqual(thread_start["params"]["cwd"], "/tmp")
        self.assertTrue(thread_start["params"]["ephemeral"])
        self.assertEqual(thread_start["params"]["sandbox"], "read-only")
        turn_start = next(
            request for request in socket.requests if request.get("method") == "turn/start"
        )
        self.assertEqual(turn_start["params"]["effort"], "none")
        self.assertEqual(
            turn_start["params"]["outputSchema"]["properties"]["slug"]["pattern"],
            "^[a-z0-9]+(?:-[a-z0-9]+)*$",
        )
        self.assertEqual(
            turn_start["params"]["outputSchema"]["required"],
            ["slug", "requires_worktree"],
        )
        self.assertEqual(AGENT_TASK.task_slug("status-line-fix"), "status-line-fix")
        for invalid in (
            "Status-Line",
            "-status",
            "status-",
            "status--line",
            "status-line-title-that-is-far-too-long-for-a-branch",
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(AGENT_TASK.AgentTaskError, "invalid task slug"):
                    AGENT_TASK.task_slug(invalid)

    def test_codex_task_slug_fallback_keeps_complete_words(self) -> None:
        self.assertEqual(
            AGENT_TASK.fallback_task_slug("Fix login flow in the app"),
            "fix-login-flow",
        )
        self.assertEqual(
            AGENT_TASK.fallback_task_slug("supercalifragilistic"),
            "supercalifragilistic",
        )
        self.assertEqual(AGENT_TASK.fallback_task_slug("상태 표시줄 정리"), "task")

    def test_copy_on_write_shell_guard_is_conservative(self) -> None:
        for command in (
            "rg -n worktree .",
            "git status --short",
            "cat README.md | rg policy",
            "sed -n '1,20p' README.md",
            "LC_ALL=C git log -1 --oneline",
            "rg missing . 2>/dev/null || true",
        ):
            with self.subTest(command=command):
                self.assertTrue(AGENT_TASK.shell_command_is_read_only(command))

        for command in (
            "printf 'changed\\n' > result.txt",
            "git add README.md",
            "git show HEAD --output=result.txt",
            "find . -delete",
            "sed -i 's/old/new/' README.md",
            "sed -n '1w result.txt' README.md",
            "python -m unittest",
            "EDITOR=writer git status",
        ):
            with self.subTest(command=command):
                self.assertFalse(AGENT_TASK.shell_command_is_read_only(command))

    def test_codex_thread_name_uses_the_branch_route(self) -> None:
        class FakeSocket:
            def __init__(self) -> None:
                self.requests: list[dict[str, object]] = []
                self.responses: list[str] = []

            async def send(self, raw: str) -> None:
                request = json.loads(raw)
                self.requests.append(request)
                if "id" in request:
                    self.responses.append(json.dumps({"id": request["id"], "result": {}}))

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
        AGENT_TASK.set_codex_thread_name(
            Path("/control.sock"),
            "thread-one",
            "skip-read-worktree -> main",
            connector=lambda: FakeConnection(socket),
        )

        self.assertEqual(
            [request.get("method") for request in socket.requests],
            ["initialize", "initialized", "thread/name/set"],
        )
        self.assertEqual(
            socket.requests[-1]["params"],
            {"threadId": "thread-one", "name": "skip-read-worktree -> main"},
        )

    def test_codex_pending_title_bootstrap_names_the_thread_before_resume(self) -> None:
        class FakeSocket:
            def __init__(self) -> None:
                self.requests: list[dict[str, object]] = []
                self.responses: list[str] = []

            async def send(self, raw: str) -> None:
                request = json.loads(raw)
                self.requests.append(request)
                if "id" not in request:
                    return
                result: object = {}
                if request["method"] == "thread/start":
                    result = {"thread": {"id": "thread-one"}}
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

        socket = FakeSocket()
        thread_id = AGENT_TASK.start_named_codex_thread(
            Path("/control.sock"),
            Path("/repo"),
            AGENT_TASK.CODEX_PENDING_THREAD_NAME,
            connector=lambda: FakeConnection(socket),
        )

        self.assertEqual(thread_id, "thread-one")
        self.assertEqual(
            [request.get("method") for request in socket.requests],
            ["initialize", "initialized", "thread/start", "thread/name/set"],
        )
        self.assertEqual(socket.requests[-2]["params"], {"cwd": "/repo"})
        self.assertEqual(
            socket.requests[-1]["params"],
            {"threadId": "thread-one", "name": AGENT_TASK.CODEX_PENDING_THREAD_NAME},
        )

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

    def test_current_session_requires_the_inherited_session_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            environment = {
                "AGENT_TASK_STATE_DIR": str(Path(directory) / "state"),
                "AI_TASK_ID": "managed-task",
                AGENT_TASK.AGENT_SESSION_ID_ENV: "",
                AGENT_TASK.AGENT_SESSION_PATH_ENV: "",
            }
            with mock.patch.dict(os.environ, environment, clear=False):
                store = AGENT_TASK.Store()
                with self.assertRaisesRegex(AGENT_TASK.AgentTaskError, "managed agent session"):
                    AGENT_TASK.current_agent_session(store)


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

    def test_open_always_uses_a_managed_task(self) -> None:
        arguments = AGENT_TASK.build_parser().parse_args(["open", "isolated work"])
        arguments.command = []
        arguments.launch_cwd = Path("/repo")

        with (
            mock.patch.object(AGENT_TASK, "prepare_launch_working_directory"),
            mock.patch.object(AGENT_TASK, "repo_root", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "primary_worktree", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "validate_foreground_agent_command"),
            mock.patch.object(AGENT_TASK, "refresh_interrupted_tasks", return_value=[]),
            mock.patch.object(AGENT_TASK, "checkout_session_lock") as checkout_lock,
            mock.patch.object(AGENT_TASK, "command_start", return_value=17) as start,
        ):
            result = AGENT_TASK.command_open(arguments, mock.Mock())

        self.assertEqual(result, 17)
        checkout_lock.assert_not_called()
        start.assert_called_once_with(arguments, mock.ANY)

    def test_open_starts_quietly_when_another_managed_task_is_active(self) -> None:
        arguments = AGENT_TASK.build_parser().parse_args(["open", "parallel work", "--quiet"])
        arguments.command = []
        arguments.launch_cwd = Path("/repo")
        active = {
            "task_id": "active-task",
            "agent": "codex",
            "status": AGENT_TASK.RUNNING,
            "process": {"pid": 123},
        }

        with (
            mock.patch.object(AGENT_TASK, "prepare_launch_working_directory"),
            mock.patch.object(AGENT_TASK, "repo_root", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "primary_worktree", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "validate_foreground_agent_command"),
            mock.patch.object(AGENT_TASK, "refresh_interrupted_tasks", return_value=[active]),
            mock.patch.object(AGENT_TASK, "process_alive", return_value=True),
            mock.patch.object(AGENT_TASK, "command_start", return_value=0) as start,
            contextlib.redirect_stdout(io.StringIO()) as stdout,
        ):
            result = AGENT_TASK.command_open(arguments, mock.Mock())

        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue(), "")
        start.assert_called_once_with(arguments, mock.ANY)

    def test_open_prefers_preserved_work_when_no_task_is_live(self) -> None:
        arguments = AGENT_TASK.build_parser().parse_args(["open", "finish it", "--quiet"])
        arguments.command = []
        arguments.launch_cwd = Path("/repo")
        preserved = {
            "task_id": "preserved-task",
            "agent": "codex",
            "status": AGENT_TASK.RECOVERY,
            "worktree_path": "/state/worktrees/preserved-task",
        }

        with (
            mock.patch.object(AGENT_TASK, "prepare_launch_working_directory"),
            mock.patch.object(AGENT_TASK, "repo_root", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "primary_worktree", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "validate_foreground_agent_command"),
            mock.patch.object(AGENT_TASK, "refresh_interrupted_tasks", return_value=[preserved]),
            mock.patch.object(AGENT_TASK, "command_recover", return_value=23) as recover,
        ):
            result = AGENT_TASK.command_open(arguments, mock.Mock())

        self.assertEqual(result, 23)
        recovery_args = recover.call_args.args[0]
        self.assertEqual(recovery_args.task_id, "preserved-task")
        self.assertTrue(recovery_args.quiet)

    def test_saved_chat_resume_uses_a_managed_task(self) -> None:
        arguments = AGENT_TASK.build_parser().parse_args(
            ["resume", "01a0479b-3a2a-77a0-8bc5-c2913ebe5247", "--quiet"]
        )
        arguments.command = []
        arguments.launch_cwd = Path("/repo")

        with (
            mock.patch.object(AGENT_TASK, "prepare_launch_working_directory"),
            mock.patch.object(AGENT_TASK, "repo_root", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "primary_worktree", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "refresh_interrupted_tasks", return_value=[]),
            mock.patch.object(AGENT_TASK, "checkout_session_lock") as checkout_lock,
            mock.patch.object(AGENT_TASK, "command_start", return_value=29) as start,
        ):
            result = AGENT_TASK.command_resume(arguments, mock.Mock())

        self.assertEqual(result, 29)
        checkout_lock.assert_not_called()
        start.assert_called_once_with(arguments, mock.ANY)
        self.assertIn("resume", arguments.command)
        self.assertIn("01a0479b-3a2a-77a0-8bc5-c2913ebe5247", arguments.command)

    def test_review_style_command_refuses_a_busy_current_checkout(self) -> None:
        arguments = AGENT_TASK.build_parser().parse_args(
            ["open", "--require-current", "--agent", "custom"]
        )
        arguments.command = ["custom-agent"]
        arguments.launch_cwd = Path("/repo")

        with (
            mock.patch.object(AGENT_TASK, "prepare_launch_working_directory"),
            mock.patch.object(AGENT_TASK, "repo_root", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "primary_worktree", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "validate_foreground_agent_command"),
            mock.patch.object(
                AGENT_TASK,
                "checkout_session_lock",
                return_value=contextlib.nullcontext(None),
            ),
        ):
            with self.assertRaisesRegex(AGENT_TASK.AgentTaskError, "current checkout is busy"):
                AGENT_TASK.command_open(arguments, mock.Mock())


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

    def test_only_repository_memory_is_globally_ignored(self) -> None:
        configuration = SCRIPT.parent.parent.joinpath("git.tf").read_text()

        self.assertIn(".ai-memory", configuration)
        self.assertNotIn(".ai-lock", configuration)

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

    def test_display_context_can_be_set_and_cleared_without_the_task_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(Path(directory))
            task_id = "20260826-204635-a5bc90"
            store.save(self.task(task_id, "environments"))
            AGENT_TASK.write_task_context(store, task_id, {"external_label": "preserved"})
            arguments = argparse.Namespace(
                task_id=task_id,
                jira="cape-456",
                clear_jira=False,
                pr=None,
                clear_pr=False,
            )

            with (
                store.lock(f"task:{task_id}"),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                AGENT_TASK.command_context(arguments, store)
            self.assertEqual(AGENT_TASK.read_task_context(store, task_id)["jira_issue"], "CAPE-456")
            self.assertEqual(
                AGENT_TASK.read_task_context(store, task_id)["external_label"],
                "preserved",
            )

            arguments.jira = None
            arguments.pr = "https://github.com/capelabs/backend/pull/321"
            with contextlib.redirect_stdout(io.StringIO()):
                AGENT_TASK.command_context(arguments, store)
            self.assertEqual(
                AGENT_TASK.read_task_context(store, task_id)["pull_request_number"],
                321,
            )

            arguments.clear_jira = True
            arguments.pr = None
            with contextlib.redirect_stdout(io.StringIO()):
                AGENT_TASK.command_context(arguments, store)
            self.assertNotIn("jira_issue", AGENT_TASK.read_task_context(store, task_id))

            arguments.clear_jira = False
            arguments.clear_pr = True
            with contextlib.redirect_stdout(io.StringIO()):
                AGENT_TASK.command_context(arguments, store)
            self.assertNotIn("pull_request_number", AGENT_TASK.read_task_context(store, task_id))

    def test_display_context_selects_an_attached_task_from_the_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(Path(directory))
            parent_id = "20260826-204635-a5bc90"
            attachment_id = "20260826-204700-b5cd91"
            parent = self.task(parent_id, "environments")
            attachment = self.task(attachment_id, "backend")
            attachment["attachment_parent_task_id"] = parent_id
            store.save(parent)
            store.save(attachment)
            arguments = argparse.Namespace(
                task_id=None,
                jira=None,
                clear_jira=False,
                pr="456",
                clear_pr=False,
            )

            with (
                mock.patch.dict(os.environ, {"AI_TASK_ID": parent_id}, clear=False),
                mock.patch.object(AGENT_TASK.os, "getcwd", return_value=attachment["worktree_path"]),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                AGENT_TASK.command_context(arguments, store)

            self.assertNotIn("pull_request_number", AGENT_TASK.read_task_context(store, parent_id))
            self.assertEqual(
                AGENT_TASK.read_task_context(store, attachment_id)["pull_request_number"],
                456,
            )

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

    def test_jira_issue_is_detected_from_the_launch_description(self) -> None:
        task = {"description": "Implement CAPE-789 for PR #456 without changing the API"}

        self.assertEqual(AGENT_TASK.jira_issue_from_task_text(task), "CAPE-789")
        self.assertEqual(AGENT_TASK.pull_request_from_task_text(task), 456)
        self.assertEqual(
            AGENT_TASK.pull_request_from_task_text(
                {"description": "Review https://github.com/capelabs/backend/pull/789/files"}
            ),
            789,
        )
        with self.assertRaisesRegex(AGENT_TASK.AgentTaskError, "invalid Jira issue"):
            AGENT_TASK.jira_issue_key("not a ticket")
        with self.assertRaisesRegex(AGENT_TASK.AgentTaskError, "invalid pull request"):
            AGENT_TASK.pull_request_number("not a pull request")

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
        exclude.write_text(exclude.read_text() + "\n.ai-memory\n")
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

    def pending_codex_hook_context(
        self,
    ) -> tuple[object, dict[str, object], Path, str, Path, dict[str, object]]:
        store = self.store()
        arguments = argparse.Namespace(
            launch_cwd=self.repository,
            agent="codex",
            target="main",
            check=[],
            check_timeout=AGENT_TASK.DEFAULT_CHECK_TIMEOUT_SECONDS,
            no_integrate=False,
            quiet=True,
            task=None,
            description="interactive agent task",
        )
        task = AGENT_TASK.create_task(store, arguments, defer_worktree=True)
        path = Path(str(task["worktree_path"]))
        owner = AGENT_TASK.process_record(os.getpid(), role="lock-supervisor")
        assert owner is not None
        task["process"] = owner
        task["status"] = AGENT_TASK.RUNNING
        store.save(task)
        session_id = "session-one"
        session_path = store.sessions / "session-one.json"
        session = {
            "session_id": session_id,
            "task_id": task["task_id"],
            "process": owner,
            "working_directory": str(self.repository),
            "control_socket": str(store.controls / "session-one.sock"),
        }
        return store, task, path, session_id, session_path, session

    def test_read_only_codex_prompt_skips_the_worktree(self) -> None:
        store, task, path, session_id, session_path, session = self.pending_codex_hook_context()
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "thread-one",
            "cwd": str(self.repository),
            "prompt": "Inspect how login works",
        }

        with (
            mock.patch.dict(
                os.environ,
                {
                    "AI_TASK_HARNESS": "agent-task",
                    "AI_TASK_ID": str(task["task_id"]),
                },
                clear=False,
            ),
            mock.patch.object(AGENT_TASK, "Store", return_value=store),
            mock.patch.object(
                AGENT_TASK,
                "current_agent_session",
                return_value=(session_id, session_path, session),
            ),
            mock.patch.object(
                AGENT_TASK,
                "read_codex_provision_hook_payload",
                return_value=payload,
            ),
            mock.patch.object(
                AGENT_TASK,
                "generate_codex_task_intent",
                return_value=("inspect-login", False),
            ),
            mock.patch.object(AGENT_TASK, "update_session_metadata") as update_metadata,
            mock.patch.object(AGENT_TASK, "set_codex_thread_name") as set_thread_name,
            contextlib.redirect_stdout(io.StringIO()) as stdout,
        ):
            result = AGENT_TASK.command_provision_hook()

        updated = store.load(str(task["task_id"]))
        output = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertIsNone(updated["branch"])
        self.assertEqual(updated["title"], "inspect-login")
        self.assertEqual(updated["provisioning_slug"], "inspect-login")
        self.assertEqual(updated["worktree_state"], AGENT_TASK.WORKTREE_PENDING)
        self.assertEqual(list(path.iterdir()), [])
        self.assertIn("no task branch or Git worktree exists yet", output["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(
            update_metadata.call_args.args[2]["codex_task_checkout"],
            "read-only",
        )
        set_thread_name.assert_called_once_with(
            Path(str(session["control_socket"])),
            "thread-one",
            "inspect-login [read-only] -> main",
        )

        updated.pop("process", None)
        updated["status"] = AGENT_TASK.COMPLETED
        store.save(updated)
        self.assertTrue(AGENT_TASK.cleanup_task(store, updated))
        self.assertFalse(path.exists())

    def test_first_guarded_write_promotes_and_rejects_the_retry(self) -> None:
        store, task, path, session_id, session_path, session = self.pending_codex_hook_context()
        task["provisioning_slug"] = "inspect-login"
        store.save(task)
        safe_payload = {
            "hook_event_name": "PreToolUse",
            "session_id": "thread-one",
            "cwd": str(self.repository),
            "tool_name": "Bash",
            "tool_input": {"command": "rg -n login ."},
        }
        write_payload = {
            "hook_event_name": "PreToolUse",
            "session_id": "thread-one",
            "cwd": str(self.repository),
            "tool_name": "apply_patch",
            "tool_input": {"patch": "*** Begin Patch"},
        }

        environment = {
            "AI_TASK_HARNESS": "agent-task",
            "AI_TASK_ID": str(task["task_id"]),
        }
        with (
            mock.patch.dict(os.environ, environment, clear=False),
            mock.patch.object(AGENT_TASK, "Store", return_value=store),
            mock.patch.object(
                AGENT_TASK,
                "current_agent_session",
                return_value=(session_id, session_path, session),
            ),
            mock.patch.object(
                AGENT_TASK,
                "read_codex_provision_hook_payload",
                return_value=safe_payload,
            ),
            contextlib.redirect_stdout(io.StringIO()) as safe_stdout,
        ):
            self.assertEqual(AGENT_TASK.command_provision_hook(), 0)

        deferred = store.load(str(task["task_id"]))
        self.assertEqual(safe_stdout.getvalue(), "")
        self.assertIsNone(deferred["branch"])
        self.assertEqual(deferred["worktree_state"], AGENT_TASK.WORKTREE_PENDING)

        with (
            mock.patch.dict(os.environ, environment, clear=False),
            mock.patch.object(AGENT_TASK, "Store", return_value=store),
            mock.patch.object(
                AGENT_TASK,
                "current_agent_session",
                return_value=(session_id, session_path, session),
            ),
            mock.patch.object(
                AGENT_TASK,
                "read_codex_provision_hook_payload",
                return_value=write_payload,
            ),
            mock.patch.object(AGENT_TASK, "update_session_metadata"),
            mock.patch.object(AGENT_TASK, "set_codex_thread_name") as set_thread_name,
            contextlib.redirect_stdout(io.StringIO()) as write_stdout,
        ):
            self.assertEqual(AGENT_TASK.command_provision_hook(), 0)

        promoted = store.load(str(task["task_id"]))
        output = json.loads(write_stdout.getvalue())
        self.assertEqual(promoted["branch"], "inspect-login")
        self.assertEqual(promoted["worktree_state"], AGENT_TASK.WORKTREE_READY)
        self.assertEqual(self.git("branch", "--show-current", cwd=path).stdout.strip(), "inspect-login")
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("Retry it in AI_TASK_WORKDIR", output["hookSpecificOutput"]["permissionDecisionReason"])
        set_thread_name.assert_called_once_with(
            Path(str(session["control_socket"])),
            "thread-one",
            "inspect-login -> main",
        )

        promoted.pop("process", None)
        promoted["status"] = AGENT_TASK.COMPLETED
        store.save(promoted)
        self.assertTrue(AGENT_TASK.cleanup_task(store, promoted))

    def test_read_only_prompt_promotes_when_the_base_checkout_is_dirty(self) -> None:
        store, task, path, session_id, session_path, session = self.pending_codex_hook_context()
        (self.repository / "local.txt").write_text("local change\n")
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "thread-one",
            "cwd": str(self.repository),
            "prompt": "Inspect how login works",
        }

        with (
            mock.patch.dict(
                os.environ,
                {
                    "AI_TASK_HARNESS": "agent-task",
                    "AI_TASK_ID": str(task["task_id"]),
                },
                clear=False,
            ),
            mock.patch.object(AGENT_TASK, "Store", return_value=store),
            mock.patch.object(
                AGENT_TASK,
                "current_agent_session",
                return_value=(session_id, session_path, session),
            ),
            mock.patch.object(
                AGENT_TASK,
                "read_codex_provision_hook_payload",
                return_value=payload,
            ),
            mock.patch.object(
                AGENT_TASK,
                "generate_codex_task_intent",
                return_value=("inspect-login", False),
            ),
            mock.patch.object(AGENT_TASK, "update_session_metadata"),
            mock.patch.object(AGENT_TASK, "set_codex_thread_name"),
            contextlib.redirect_stdout(io.StringIO()) as stdout,
        ):
            self.assertEqual(AGENT_TASK.command_provision_hook(), 0)

        promoted = store.load(str(task["task_id"]))
        output = json.loads(stdout.getvalue())
        self.assertEqual(promoted["branch"], "inspect-login")
        self.assertEqual(promoted["worktree_state"], AGENT_TASK.WORKTREE_READY)
        self.assertIn("tracked or untracked changes", output["hookSpecificOutput"]["additionalContext"])

        promoted.pop("process", None)
        promoted["status"] = AGENT_TASK.COMPLETED
        store.save(promoted)
        self.assertTrue(AGENT_TASK.cleanup_task(store, promoted))

    def test_semantic_branch_suffix_is_added_only_on_collision(self) -> None:
        self.assertEqual(AGENT_TASK.available_task_branch(self.repository, "fix-login"), "fix-login")
        self.git("branch", "fix-login")
        self.assertEqual(AGENT_TASK.available_task_branch(self.repository, "fix-login"), "fix-login-2")
        self.git("branch", "fix-login-2")
        self.assertEqual(AGENT_TASK.available_task_branch(self.repository, "fix-login"), "fix-login-3")

    def test_first_codex_prompt_provisions_one_semantic_worktree(self) -> None:
        store = self.store()
        arguments = argparse.Namespace(
            launch_cwd=self.repository,
            agent="codex",
            target="main",
            check=[],
            check_timeout=AGENT_TASK.DEFAULT_CHECK_TIMEOUT_SECONDS,
            no_integrate=False,
            quiet=True,
            task=None,
            description="interactive agent task",
        )
        task = AGENT_TASK.create_task(store, arguments, defer_worktree=True)
        path = Path(str(task["worktree_path"]))
        owner = AGENT_TASK.process_record(os.getpid(), role="lock-supervisor")
        assert owner is not None
        task["process"] = owner
        task["status"] = AGENT_TASK.RUNNING
        store.save(task)
        session_id = "session-one"
        session_path = store.sessions / "session-one.json"
        session = {
            "session_id": session_id,
            "task_id": task["task_id"],
            "process": owner,
            "working_directory": str(self.repository),
            "control_socket": str(store.controls / "session-one.sock"),
        }
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "thread-one",
            "cwd": str(self.repository),
            "prompt": "Fix the login flow",
        }

        self.assertTrue(path.is_dir())
        self.assertEqual(list(path.iterdir()), [])
        self.assertIsNone(task["branch"])
        self.assertEqual(task["worktree_state"], AGENT_TASK.WORKTREE_PENDING)
        with (
            mock.patch.dict(
                os.environ,
                {
                    "AI_TASK_HARNESS": "agent-task",
                    "AI_TASK_ID": str(task["task_id"]),
                },
                clear=False,
            ),
            mock.patch.object(AGENT_TASK, "Store", return_value=store),
            mock.patch.object(
                AGENT_TASK,
                "current_agent_session",
                return_value=(session_id, session_path, session),
            ),
            mock.patch.object(
                AGENT_TASK,
                "read_codex_provision_hook_payload",
                return_value=payload,
            ),
            mock.patch.object(
                AGENT_TASK,
                "generate_codex_task_intent",
                return_value=("fix-login", True),
            ),
            mock.patch.object(AGENT_TASK, "update_session_metadata") as update_metadata,
            mock.patch.object(AGENT_TASK, "set_codex_thread_name") as set_thread_name,
            contextlib.redirect_stdout(io.StringIO()) as stdout,
        ):
            result = AGENT_TASK.command_provision_hook()

        updated = store.load(str(task["task_id"]))
        expected_branch = "fix-login"
        output = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(updated["branch"], expected_branch)
        self.assertEqual(updated["provisioning_slug"], "fix-login")
        self.assertEqual(updated["worktree_state"], AGENT_TASK.WORKTREE_READY)
        self.assertEqual(self.git("branch", "--show-current", cwd=path).stdout.strip(), expected_branch)
        self.assertIn(expected_branch, output["hookSpecificOutput"]["additionalContext"])
        update_metadata.assert_called_once()
        set_thread_name.assert_called_once_with(
            Path(str(session["control_socket"])),
            "thread-one",
            "fix-login -> main",
        )

        updated.pop("process", None)
        updated["status"] = AGENT_TASK.COMPLETED
        store.save(updated)
        self.assertTrue(AGENT_TASK.cleanup_task(store, updated))
        self.assertFalse(path.exists())
        self.assertNotEqual(
            self.git(
                "show-ref",
                "--verify",
                "--quiet",
                f"refs/heads/{expected_branch}",
                check=False,
            ).returncode,
            0,
        )

    def test_secondary_attachment_reuses_the_parent_semantic_slug(self) -> None:
        secondary = Path(self.temporary.name) / "secondary-semantic"
        self.git("init", "-b", "main", str(secondary), cwd=Path(self.temporary.name))
        self.git("config", "user.name", "Test Agent", cwd=secondary)
        self.git("config", "user.email", "agent@example.com", cwd=secondary)
        self.git("config", "commit.gpgsign", "false", cwd=secondary)
        exclude = secondary / ".git/info/exclude"
        exclude.write_text(exclude.read_text() + "\n.ai-memory\n")
        (secondary / "base.txt").write_text("base\n")
        self.git("add", ".", cwd=secondary)
        self.git("commit", "-m", "base", cwd=secondary)

        store = self.store()
        arguments = argparse.Namespace(
            launch_cwd=self.repository,
            agent="codex",
            target="main",
            check=[],
            check_timeout=AGENT_TASK.DEFAULT_CHECK_TIMEOUT_SECONDS,
            no_integrate=False,
            quiet=True,
            task=None,
            description="interactive agent task",
        )
        parent = AGENT_TASK.create_task(store, arguments)
        parent["provisioning_slug"] = "fix-login"
        owner = AGENT_TASK.process_record(os.getpid(), role="lock-supervisor")
        assert owner is not None
        parent["process"] = owner
        parent["status"] = AGENT_TASK.RUNNING
        store.save(parent)
        session = {
            "session_id": "session-one",
            "task_id": parent["task_id"],
            "process": owner,
            "agent": "codex",
        }

        with (
            mock.patch.object(
                AGENT_TASK,
                "current_agent_session",
                return_value=("session-one", store.sessions / "session-one.json", session),
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = AGENT_TASK.command_attach(argparse.Namespace(path=str(secondary)), store)

        attachment = next(
            value
            for value in store.all()
            if value.get("attachment_parent_task_id") == parent["task_id"]
        )
        self.assertEqual(result, 0)
        self.assertEqual(attachment["branch"], "fix-login")
        self.assertEqual(
            self.git(
                "branch",
                "--show-current",
                cwd=Path(str(attachment["worktree_path"])),
            ).stdout.strip(),
            attachment["branch"],
        )

        for value in (attachment, parent):
            value.pop("process", None)
            value["status"] = AGENT_TASK.COMPLETED
            store.save(value)
            self.assertTrue(AGENT_TASK.cleanup_task(store, value))

    def test_open_isolates_and_integrates_the_first_task(self) -> None:
        result = self.cli(
            "open",
            "isolated by default",
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
        self.assertEqual(task["base_source"], "integration_target")
        self.assertEqual(task["worktree_number"], 1)
        self.assertEqual(task["origin_working_directory"], str(self.repository))
        self.assertEqual((self.repository / "policy-result.txt").read_text(), "isolated\n")

    def test_open_records_main_as_the_default_target(self) -> None:
        self.git("branch", "develop")

        self.cli("open", "--agent", "custom", "--", "true", check=True)
        memory = json.loads((self.repository / ".ai-memory").read_text())

        self.assertEqual(memory["settings"]["integration_target"], "main")


    def test_managed_session_attaches_and_integrates_a_secondary_repository(self) -> None:
        secondary = Path(self.temporary.name) / "secondary"
        self.git("init", "-b", "main", str(secondary), cwd=Path(self.temporary.name))
        self.git("config", "user.name", "Test Agent", cwd=secondary)
        self.git("config", "user.email", "agent@example.com", cwd=secondary)
        self.git("config", "commit.gpgsign", "false", cwd=secondary)
        exclude = secondary / ".git/info/exclude"
        exclude.write_text(exclude.read_text() + "\n.ai-memory\n")
        (secondary / "base.txt").write_text("base\n")
        self.git("add", ".", cwd=secondary)
        self.git("commit", "-m", "base", cwd=secondary)

        agent_code = (
            "import subprocess,sys; from pathlib import Path; "
            f"script={str(SCRIPT)!r}; secondary={str(secondary)!r}; "
            "attached=subprocess.run([sys.executable,script,'attach',secondary],"
            "check=True,text=True,stdout=subprocess.PIPE); "
            "task_id=next(line.removeprefix('task: ') for line in "
            "attached.stdout.splitlines() if line.startswith('task: ')); "
            "worktree=Path(next(line.removeprefix('worktree: ') for line in "
            "attached.stdout.splitlines() if line.startswith('worktree: '))); "
            "worktree.joinpath('secondary.txt').write_text('attached\\n'); "
            "subprocess.run(['git','add','secondary.txt'],cwd=worktree,check=True); "
            "subprocess.run(['git','commit','-m','feat: add attached result'],cwd=worktree,check=True); "
            "subprocess.run([sys.executable,script,'publish',task_id],check=True); "
            "published=subprocess.run(['git','show','main:secondary.txt'],cwd=secondary,"
            "check=True,text=True,stdout=subprocess.PIPE).stdout; "
            "assert published == 'attached\\n'; "
            "worktree.joinpath('secondary-later.txt').write_text('later\\n'); "
            "subprocess.run(['git','add','secondary-later.txt'],cwd=worktree,check=True); "
            "subprocess.run(['git','commit','-m','feat: continue attached work'],cwd=worktree,check=True)"
        )
        result = self.cli(
            "open",
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
        self.assertEqual((secondary / "secondary-later.txt").read_text(), "later\n")
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
        exclude.write_text(exclude.read_text() + "\n.ai-memory\n")
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
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            "exit 75",
        )

        self.assertEqual(result.returncode, 75)

    def test_open_isolates_busy_dirty_work_and_queues_integration(self) -> None:
        local_only = self.repository / "local-only.txt"
        local_only.write_text("owned by the in-place session\n")
        with AGENT_TASK.checkout_session_lock(self.store(), self.repository) as acquired:
            self.assertTrue(acquired)
            result = self.cli(
                "open",
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

    def test_git_clean_cannot_bypass_the_stable_lock(self) -> None:
        store = self.store()

        with AGENT_TASK.checkout_session_lock(store, self.repository) as first:
            self.assertTrue(first)
            self.git("clean", "-fdx")
            with AGENT_TASK.checkout_session_lock(store, self.repository) as second:
                self.assertFalse(second)

        with AGENT_TASK.checkout_session_lock(store, self.repository) as released:
            self.assertTrue(released)

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

    def test_detached_onepassword_daemon_releases_the_checkout(self) -> None:
        store = self.store()
        daemon_pid_path = self.repository.parent / "op-daemon-pid.txt"
        daemon_code = (
            "import ctypes,os,time; from pathlib import Path; "
            "child=os.fork(); "
            "os._exit(0) if child else None; "
            "os.setsid(); ctypes.CDLL(None).prctl(15,b'op',0,0,0); "
            f"Path({str(daemon_pid_path)!r}).write_text(str(os.getpid())); "
            "time.sleep(10)"
        )
        daemon_pid: int | None = None
        supervisor: subprocess.Popen[bytes] | None = None
        with AGENT_TASK.checkout_session_lock(store, self.repository) as reservation:
            self.assertTrue(reservation)
            command, environment = AGENT_TASK.guarded_agent_invocation(
                [sys.executable, "-c", daemon_code],
                os.environ.copy(),
                tuple(reservation),
            )
            supervisor = subprocess.Popen(
                command,
                env=environment,
                pass_fds=tuple(reservation),
            )

        try:
            supervisor.wait(timeout=3)
            for _ in range(100):
                if daemon_pid_path.exists():
                    break
                time.sleep(0.01)
            self.assertTrue(daemon_pid_path.exists())
            daemon_pid = int(daemon_pid_path.read_text())
            os.kill(daemon_pid, 0)
            with AGENT_TASK.checkout_session_lock(store, self.repository) as after_supervisor:
                self.assertTrue(after_supervisor)
        finally:
            if daemon_pid is not None:
                try:
                    os.kill(daemon_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            if supervisor is not None and supervisor.poll() is None:
                supervisor.kill()
                supervisor.wait(timeout=5)

    def test_open_uses_the_target_while_a_native_supervisor_is_alive(self) -> None:
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
            target_head = self.git("rev-parse", "main").stdout.strip()
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
                "--agent",
                "custom",
                "--task",
                "parallel after launcher exit",
                "--",
                "sh",
                "-lc",
                (
                    "test -e active-after-session-start.txt && "
                    "printf 'K only\\n' > isolated-after-launcher.txt && "
                    "git add isolated-after-launcher.txt && "
                    "git commit -m 'feat: add isolated result after launcher exit'"
                ),
            )
            task = self.task_from(result)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(task["base_sha"], target_head)
            self.assertEqual(task["base_source"], "integration_target")
        finally:
            if supervisor is not None:
                supervisor.wait(timeout=5)

        self.cli("reconcile", check=True)
        self.assertEqual((self.repository / "isolated-after-launcher.txt").read_text(), "K only\n")

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

    def test_active_task_can_publish_and_keep_working(self) -> None:
        base = self.git("rev-parse", "main").stdout.strip()
        python = shlex.quote(sys.executable)
        script = shlex.quote(str(SCRIPT))
        repository = shlex.quote(str(self.repository))
        result = self.cli(
            "start",
            "publish before deployment",
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            (
                "printf 'published\\n' > published.txt && "
                "git add published.txt && git commit -m 'feat: publish checkpoint' && "
                f"{python} {script} publish && "
                f"test \"$(git -C {repository} show main:published.txt)\" = published && "
                "printf 'continued\\n' > continued.txt && "
                "git add continued.txt && git commit -m 'feat: continue after publish'"
            ),
            check=True,
        )
        task = self.task_from(result)

        self.assertIn("fast-forward publish", result.stdout)
        self.assertEqual(task["status"], AGENT_TASK.INTEGRATED)
        self.assertEqual((self.repository / "published.txt").read_text(), "published\n")
        self.assertEqual((self.repository / "continued.txt").read_text(), "continued\n")
        self.assertEqual(
            self.git("rev-list", "--merges", f"{base}..main").stdout.strip(),
            "",
        )

    def test_active_task_can_publish_while_another_task_runs(self) -> None:
        ready = self.state / "parallel-publish-ready"
        release = self.state / "parallel-publish-release"
        holder = subprocess.Popen(
            [
                sys.executable,
                str(SCRIPT),
                "start",
                "hold an independent worktree",
                "--agent",
                "custom",
                "--",
                "sh",
                "-lc",
                (
                    f"touch {shlex.quote(str(ready))}; "
                    f"while [ ! -e {shlex.quote(str(release))} ]; do sleep 0.02; done"
                ),
            ],
            cwd=self.repository,
            env=self.cli_environment(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            deadline = time.monotonic() + 10
            while not ready.exists() and holder.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(ready.exists(), "parallel task did not become ready")

            python = shlex.quote(sys.executable)
            script = shlex.quote(str(SCRIPT))
            repository = shlex.quote(str(self.repository))
            published = self.cli(
                "start",
                "publish alongside another task",
                "--agent",
                "custom",
                "--",
                "sh",
                "-lc",
                (
                    "printf 'parallel publish\\n' > parallel-publish.txt && "
                    "git add parallel-publish.txt && "
                    "git commit -m 'feat: publish alongside another task' && "
                    f"{python} {script} publish && "
                    f"test \"$(git -C {repository} show main:parallel-publish.txt)\" = 'parallel publish'"
                ),
            )
            task = self.task_from(published)
            self.assertEqual(published.returncode, 0, published.stderr)
            self.assertIn("fast-forward publish", published.stdout)
            self.assertEqual(task["status"], AGENT_TASK.INTEGRATED)
            self.assertEqual(task["integration_strategy"], "already-present")
            self.assertEqual((self.repository / "parallel-publish.txt").read_text(), "parallel publish\n")

            release.write_text("release\n")
            holder_stdout, holder_stderr = holder.communicate(timeout=20)
        finally:
            if holder.poll() is None:
                holder.terminate()
                holder.wait(timeout=5)

        self.assertEqual(holder.returncode, 0, f"stdout:\n{holder_stdout}\nstderr:\n{holder_stderr}")
        updated = json.loads((self.state / "tasks" / f"{task['task_id']}.json").read_text())
        self.assertEqual(updated["status"], AGENT_TASK.INTEGRATED)

    def test_obsolete_handoff_keeps_the_receiver_open(self) -> None:
        result = self.cli(
            "start",
            "prepare an already published result",
            "--agent",
            "custom",
            "--no-integrate",
            "--",
            "sh",
            "-lc",
            "printf 'published\\n' > obsolete-handoff.txt && git add obsolete-handoff.txt && "
            "git commit -m 'feat: prepare published result'",
            check=True,
        )
        task = self.task_from(result)
        store = self.store()
        task["auto_integrate"] = True
        store.save(task)
        self.git("merge", "--ff-only", str(task["result_commit"]))

        session_id = "active-receiver"
        session_path = store.sessions / "active-receiver.json"
        session = {
            "session_id": session_id,
            "notification_protocol": AGENT_TASK.NOTIFICATION_PROTOCOL,
            "notification_state": "ready",
            "process": AGENT_TASK.process_record(os.getpid(), role="lock-supervisor"),
        }
        AGENT_TASK.atomic_write_private(session_path, (json.dumps(session) + "\n").encode())
        event_id = AGENT_TASK.enqueue_integration_notice(store, session, task)
        environment = {
            "AGENT_TASK_STATE_DIR": str(self.state),
            AGENT_TASK.AGENT_SESSION_ID_ENV: session_id,
            AGENT_TASK.AGENT_SESSION_PATH_ENV: str(session_path),
        }
        stdout = io.StringIO()
        with (
            mock.patch.dict(os.environ, environment, clear=False),
            mock.patch.object(AGENT_TASK.os, "kill") as kill,
            contextlib.redirect_stdout(stdout),
        ):
            with AGENT_TASK.repository_activity_lock(
                store,
                self.repository,
                exclusive=False,
                blocking=True,
            ) as available:
                self.assertTrue(available)
                exit_code = AGENT_TASK.command_handoff(
                    AGENT_TASK.argparse.Namespace(event_id=event_id),
                    store,
                )

        updated = store.load(str(task["task_id"]))
        inbox = AGENT_TASK.read_session_inbox(store, session_id)
        self.assertEqual(exit_code, 0)
        self.assertEqual(updated["status"], AGENT_TASK.INTEGRATED)
        self.assertEqual(updated["integration_strategy"], "already-present")
        self.assertEqual(inbox["messages"][0]["status"], "resolved")
        self.assertIn("this session remains open", stdout.getvalue())
        kill.assert_not_called()

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
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            "git add resumed.txt && git commit -m 'feat: resume task'",
            check=True,
        )
        updated = json.loads((self.state / "tasks" / f"{task['task_id']}.json").read_text())

        self.assertIn("Resuming: resume this task", resumed.stdout)
        self.assertIn(f"...{str(task['task_id']).rpartition('-')[2]}", resumed.stdout)
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

        opened = self.cli("open", "another instruction", "--agent", "custom", "--", "true")

        self.assertEqual(opened.returncode, 2)
        self.assertIn("multiple interrupted tasks require a terminal selection", opened.stderr)
        self.assertIn("first interrupted task", opened.stdout)
        self.assertIn("second interrupted task", opened.stdout)
        self.assertNotIn("interactive agent task", opened.stdout)
        self.assertEqual(len(list((self.state / "tasks").glob("*.json"))), 2)

    def test_recovery_picker_defaults_to_all_and_shows_titles(self) -> None:
        older = {
            "task_id": "20260828-174720-ea947f",
            "title": "fix-login-timeout",
            "description": "interactive agent task",
            "branch": "fix-login-timeout",
            "target_branch": "develop",
            "worktree_path": "/missing/one",
            "updated_at": "2026-08-28T17:47:20+09:00",
        }
        newer = {
            "task_id": "20260828-205537-7e3533",
            "provisioning_slug": "skip-read-worktree",
            "description": "interactive agent task",
            "branch": "skip-read-worktree",
            "target_branch": "develop",
            "worktree_path": "/missing/two",
            "updated_at": "2026-08-28T20:55:37+09:00",
        }

        with (
            mock.patch.object(sys.stdin, "isatty", return_value=True),
            mock.patch("builtins.input", return_value=""),
            contextlib.redirect_stdout(io.StringIO()) as stdout,
        ):
            selected = AGENT_TASK.choose_recovery_tasks([older, newer])

        output = stdout.getvalue()
        self.assertEqual(selected, [newer, older])
        self.assertIn("skip-read-worktree", output)
        self.assertIn("fix-login-timeout", output)
        self.assertIn("skip-read-worktree -> develop", output)
        self.assertIn("id ...7e3533", output)
        self.assertNotIn("interactive agent task", output)

    def test_recovery_title_ignores_legacy_id_only_branch(self) -> None:
        task = {
            "task_id": "20260828-174720-ea947f",
            "agent": "codex",
            "description": "interactive agent task",
            "branch": "ai/codex/20260828-174720-ea947f",
            "worktree_path": "/missing/worktree",
        }

        self.assertEqual(AGENT_TASK.recovery_task_title(task), "untitled recovery")

    def test_recovery_queue_runs_every_selected_task(self) -> None:
        tasks = [
            {"task_id": "20260828-174720-ea947f", "title": "first-fix"},
            {"task_id": "20260828-205537-7e3533", "title": "second-fix"},
        ]
        arguments = argparse.Namespace(
            agent="codex",
            no_integrate=False,
            quiet=True,
        )

        with (
            mock.patch.object(AGENT_TASK, "command_recover", side_effect=(0, 0)) as recover,
            contextlib.redirect_stdout(io.StringIO()) as stdout,
        ):
            result = AGENT_TASK.recover_selected_tasks(
                arguments,
                mock.Mock(),
                tasks,
                new_session=False,
                prompt=None,
                command=[],
            )

        self.assertEqual(result, 0)
        self.assertEqual(recover.call_count, 2)
        self.assertIn("Resuming 1/2: first-fix", stdout.getvalue())
        self.assertIn("Resuming 2/2: second-fix", stdout.getvalue())

    def test_empty_interrupted_tasks_are_cleaned_without_a_picker(self) -> None:
        store = self.store()
        arguments = argparse.Namespace(
            launch_cwd=self.repository,
            agent="codex",
            target="main",
            check=[],
            check_timeout=AGENT_TASK.DEFAULT_CHECK_TIMEOUT_SECONDS,
            no_integrate=False,
            quiet=True,
            task=None,
            description=None,
        )
        ready = AGENT_TASK.create_task(store, arguments)
        pending = AGENT_TASK.create_task(store, arguments, defer_worktree=True)
        for task in (ready, pending):
            task["status"] = AGENT_TASK.RECOVERY
            task["interrupted_at"] = AGENT_TASK.now()
            task["process"] = {"pid": 99999999, "start": "gone", "role": "lock-supervisor"}
            store.save(task)

        refreshed = AGENT_TASK.refresh_interrupted_tasks(store, self.repository)
        updated = {task["task_id"]: task for task in refreshed}

        for task in (ready, pending):
            resolved = updated[task["task_id"]]
            self.assertEqual(resolved["status"], AGENT_TASK.COMPLETED)
            self.assertIn("cleaned automatically", resolved["status_reason"])
            self.assertFalse(Path(str(task["worktree_path"])).exists())
        self.assertEqual(
            [task for task in refreshed if task.get("status") == AGENT_TASK.RECOVERY],
            [],
        )

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

    def test_unowned_transient_state_requires_explicit_integration(self) -> None:
        result = self.cli(
            "start",
            "preserve unowned transient state",
            "--agent",
            "custom",
            "--no-integrate",
            "--",
            "sh",
            "-lc",
            "printf 'unowned\n' > unowned-result.txt && git add unowned-result.txt && git commit -m 'feat: add unowned result'",
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
        self.assertTrue(preserved["unowned_integration_interrupted"])
        self.assertFalse((self.repository / "unowned-result.txt").exists())

        self.cli("integrate", str(task["task_id"]), check=True)
        self.assertEqual((self.repository / "unowned-result.txt").read_text(), "unowned\n")

    def test_reconcile_closes_an_unowned_record_whose_result_is_already_on_target(self) -> None:
        result = self.cli(
            "start",
            "recognize an already applied unowned result",
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
        task["unowned_integration_interrupted"] = True
        task["status_reason"] = "interrupted integration has no owner metadata"
        task_path.write_text(json.dumps(task, indent=2, sort_keys=True) + "\n")

        self.cli("reconcile", "--quiet", check=True)
        updated = json.loads(task_path.read_text())

        self.assertEqual(updated["status"], AGENT_TASK.INTEGRATED)
        self.assertNotIn("unowned_integration_interrupted", updated)
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

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


SCRIPT = Path(__file__).with_name("agent_task.py")
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

    def test_codex_launcher_uses_a_worktree_only_when_busy(self) -> None:
        configuration = SCRIPT.parent.parent.joinpath("agent-task.tf").read_text()

        self.assertIn('if [[ "$${1-}" == "--local" ]]', configuration)
        self.assertIn('if [[ "$${1-}" == "resume" ]]', configuration)
        self.assertIn('if [[ "$${1-}" == "--new" ]]', configuration)
        self.assertIn('if [[ "$${1-}" == "--task" ]]', configuration)
        self.assertIn("agent-task open --auto --agent codex", configuration)
        self.assertIn("agent-task open --managed --new --agent codex", configuration)
        self.assertIn("agent-task resume --agent codex", configuration)
        self.assertIn("agent-task open --managed --agent codex", configuration)
        self.assertIn('command codex --dangerously-bypass-approvals-and-sandbox "$@"', configuration)
        self.assertIn('command env IS_DEMO=1 claude', configuration)
        self.assertNotIn('resource "host_package_pacman" "bubblewrap"', configuration)

    def test_checkout_lock_detects_contention_and_releases_automatically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            with AGENT_TASK.checkout_session_lock(checkout) as first:
                with AGENT_TASK.checkout_session_lock(checkout) as second:
                    self.assertTrue(first)
                    self.assertFalse(second)
            with AGENT_TASK.checkout_session_lock(checkout) as after_release:
                self.assertTrue(after_release)
            self.assertTrue((checkout / ".ai-lock").exists())

    def test_auto_open_uses_the_current_checkout_when_available(self) -> None:
        arguments = AGENT_TASK.build_parser().parse_args(["open", "work here", "--auto"])
        arguments.command = []
        completed = mock.Mock(returncode=0)

        with (
            mock.patch.object(AGENT_TASK, "repo_root", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "primary_worktree", return_value=Path("/repo")),
            mock.patch.object(
                AGENT_TASK,
                "checkout_session_lock",
                return_value=contextlib.nullcontext(True),
            ),
            mock.patch.object(AGENT_TASK.subprocess, "run", return_value=completed) as run,
        ):
            exit_code = AGENT_TASK.command_open(arguments, mock.Mock())

        self.assertEqual(exit_code, 0)
        self.assertEqual(run.call_args.args[0][-1], "work here")

    def test_auto_open_falls_back_to_a_worktree_when_busy(self) -> None:
        arguments = AGENT_TASK.build_parser().parse_args(["open", "parallel work", "--auto"])
        arguments.command = []

        with (
            mock.patch.object(AGENT_TASK, "repo_root", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "primary_worktree", return_value=Path("/repo")),
            mock.patch.object(
                AGENT_TASK,
                "checkout_session_lock",
                return_value=contextlib.nullcontext(False),
            ),
            mock.patch.object(AGENT_TASK, "refresh_interrupted_tasks", return_value=[]),
            mock.patch.object(AGENT_TASK, "command_start", return_value=0) as start,
        ):
            exit_code = AGENT_TASK.command_open(arguments, mock.Mock())

        self.assertEqual(exit_code, 0)
        self.assertTrue(start.call_args.args[0].allow_dirty_source)
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

    def test_resume_without_preserved_work_uses_the_available_checkout(self) -> None:
        arguments = AGENT_TASK.build_parser().parse_args(["resume"])
        completed = mock.Mock(returncode=0)

        with (
            mock.patch.object(AGENT_TASK, "repo_root", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "primary_worktree", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "refresh_interrupted_tasks", return_value=[]),
            mock.patch.object(
                AGENT_TASK,
                "checkout_session_lock",
                return_value=contextlib.nullcontext(True),
            ),
            mock.patch.object(AGENT_TASK.subprocess, "run", return_value=completed) as run,
        ):
            exit_code = AGENT_TASK.command_resume(arguments, mock.Mock())

        self.assertEqual(exit_code, 0)
        command = run.call_args.args[0]
        self.assertEqual(command[:2], ["codex", "resume"])
        self.assertIn("--all", command)
        self.assertIn('tui.resume_cwd="current"', command)

    def test_resume_uses_a_fresh_worktree_when_the_checkout_is_busy(self) -> None:
        arguments = AGENT_TASK.build_parser().parse_args(["resume"])

        with (
            mock.patch.object(AGENT_TASK, "repo_root", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "primary_worktree", return_value=Path("/repo")),
            mock.patch.object(AGENT_TASK, "refresh_interrupted_tasks", return_value=[]),
            mock.patch.object(
                AGENT_TASK,
                "checkout_session_lock",
                return_value=contextlib.nullcontext(False),
            ),
            mock.patch.object(AGENT_TASK, "command_start", return_value=0) as start,
        ):
            exit_code = AGENT_TASK.command_resume(arguments, mock.Mock())

        self.assertEqual(exit_code, 0)
        self.assertTrue(start.call_args.args[0].allow_dirty_source)
        command = start.call_args.args[0].command
        self.assertEqual(command[:2], ["codex", "resume"])

    def test_bubblewrap_is_forgotten_without_removing_the_package(self) -> None:
        configuration = SCRIPT.parent.parent.joinpath("agent-task.tf").read_text()

        self.assertIn("from = host_package_pacman.bubblewrap", configuration)
        self.assertIn("destroy = false", configuration)

    def test_agent_lock_is_globally_ignored(self) -> None:
        configuration = SCRIPT.parent.parent.joinpath("git.tf").read_text()

        self.assertIn(".ai-memory", configuration)
        self.assertIn(".ai-lock", configuration)

    def test_legacy_open_invocation_launches_the_native_agent(self) -> None:
        arguments = AGENT_TASK.build_parser().parse_args(["open", "continue here", "--agent", "codex"])
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

    def cli(self, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["AGENT_TASK_STATE_DIR"] = str(self.state)
        environment["GIT_CONFIG_GLOBAL"] = os.devnull
        environment["XDG_CONFIG_HOME"] = str(self.state / "xdg")
        environment.pop("SSH_AUTH_SOCK", None)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=self.repository,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if check and result.returncode:
            self.fail(f"command failed ({result.returncode})\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        return result

    def task_from(self, result: subprocess.CompletedProcess[str]) -> dict[str, object]:
        task_id = next(line.removeprefix("task: ") for line in result.stdout.splitlines() if line.startswith("task: "))
        return json.loads((self.state / "tasks" / f"{task_id}.json").read_text())

    def test_auto_open_runs_natively_when_the_checkout_is_free(self) -> None:
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

    def test_auto_open_isolates_busy_dirty_work_and_queues_integration(self) -> None:
        local_only = self.repository / "local-only.txt"
        local_only.write_text("owned by the in-place session\n")
        with AGENT_TASK.checkout_session_lock(self.repository) as acquired:
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
        self.assertTrue(local_only.exists())
        self.assertFalse((self.repository / "parallel.txt").exists())

        local_only.unlink()
        self.cli("reconcile", check=True)
        task = json.loads((self.state / "tasks" / f"{task['task_id']}.json").read_text())
        self.assertEqual(task["status"], AGENT_TASK.INTEGRATED)
        self.assertEqual((self.repository / "parallel.txt").read_text(), "parallel\n")

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
            check=True,
        )
        first_stdout, first_stderr = first.communicate(timeout=10)
        if first.returncode:
            self.fail(f"first task failed ({first.returncode})\nstdout:\n{first_stdout}\nstderr:\n{first_stderr}")

        tasks = {
            task["description"]: task
            for task in (json.loads(path.read_text()) for path in (self.state / "tasks").glob("*.json"))
        }
        first_task = tasks["first memory writer"]
        second_task = self.task_from(second)
        memory = json.loads((self.repository / ".ai-memory").read_text())

        self.assertEqual(first_task["status"], "INTEGRATED")
        self.assertEqual(first_task["memory_overwrites"]["fields"], ["memories.workflow.review"])
        self.assertEqual(second_task["status"], "INTEGRATED")
        self.assertEqual(memory["memories"]["workflow.review"]["summary"], "Use the first review workflow.")
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
        self.assertIn("{invalid", task["memory_proposal"]["proposal"])
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

    def test_ignored_artifact_is_discarded_after_clean_commit(self) -> None:
        result = self.cli(
            "start",
            "create an ignored build artifact",
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            "printf 'done\\n' > result.txt && git add result.txt && git commit -m 'feat: add result' && mkdir .agent-cache && touch .agent-cache/output",
            check=True,
        )
        task = self.task_from(result)
        worktree = Path(str(task["worktree_path"]))

        self.assertTrue(task.get("integrated_commit"))
        self.assertEqual(task["status"], "INTEGRATED")
        self.assertEqual(task["discarded_ignored_artifacts"]["count"], 1)
        self.assertFalse(worktree.exists())

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
        self.assertIn("tracks forbidden .ai-memory", task["status_reason"])
        self.assertFalse(Path(str(task["worktree_path"])).exists())
        self.assertNotEqual(self.git("cat-file", "-e", "main:.ai-memory", check=False).returncode, 0)
        self.assertEqual(
            self.git("show-ref", "--verify", "--quiet", f"refs/heads/{task['branch']}", check=False).returncode,
            0,
        )

    def test_reconcile_finishes_a_ready_task(self) -> None:
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
        self.assertEqual(updated["status"], "INTEGRATED")
        self.assertEqual((self.repository / "queued.txt").read_text(), "queued\n")
        self.assertFalse(Path(str(updated["worktree_path"])).exists())

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

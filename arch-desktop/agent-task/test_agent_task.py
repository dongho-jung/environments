from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("agent_task.py")


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
        self.assertNotEqual(self.git("show-ref", "--verify", "--quiet", f"refs/heads/{task['branch']}", check=False).returncode, 0)

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

    def test_conflict_preserves_committed_task(self) -> None:
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
        self.assertTrue(Path(str(updated["worktree_path"])).exists())
        self.assertEqual((self.repository / "shared.txt").read_text(), "target\n")

    def test_ignored_artifact_requires_explicit_discard(self) -> None:
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
        self.assertEqual(task["status"], "RECOVERY_REQUIRED")
        self.assertTrue((worktree / ".agent-cache/output").exists())
        self.assertEqual(self.cli("cleanup", str(task["task_id"])).returncode, 2)
        self.cli("cleanup", str(task["task_id"]), "--discard-ignored", check=True)
        updated = json.loads((self.state / "tasks" / f"{task['task_id']}.json").read_text())
        self.assertEqual(updated["status"], "INTEGRATED")
        self.assertFalse(worktree.exists())

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

        self.cli("reconcile", check=True)
        updated = json.loads((self.state / "tasks" / f"{task['task_id']}.json").read_text())
        self.assertEqual(updated["status"], "INTEGRATED")
        self.assertEqual((self.repository / "queued.txt").read_text(), "queued\n")
        self.assertFalse(Path(str(updated["worktree_path"])).exists())

    def test_policy_blocks_git_lifecycle_and_terraform_apply(self) -> None:
        switched = self.cli(
            "start",
            "attempt branch switch",
            "--agent",
            "custom",
            "--",
            "git",
            "switch",
            "main",
        )
        self.assertEqual(switched.returncode, 126)
        self.assertIn("denied: git switch", switched.stderr)

        if shutil.which("terraform"):
            applied = self.cli(
                "start",
                "attempt terraform apply",
                "--agent",
                "custom",
                "--",
                "terraform",
                "apply",
                "-auto-approve",
            )
            self.assertEqual(applied.returncode, 126)
            self.assertIn("denied: terraform apply", applied.stderr)


if __name__ == "__main__":
    unittest.main()

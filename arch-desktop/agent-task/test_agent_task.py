from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
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
        exclude.write_text(exclude.read_text() + "\n.ai-metadata\n")
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
        self.assertFalse((self.state / "scratch" / str(task["task_id"])).exists())
        self.assertNotEqual(self.git("show-ref", "--verify", "--quiet", f"refs/heads/{task['branch']}", check=False).returncode, 0)

    def test_metadata_selects_target_and_persists_agent_updates(self) -> None:
        self.git("branch", "develop")
        metadata = {
            "schema_version": 1,
            "branching": {"target_branch": "develop", "strategy": "git-flow"},
            "deployment": {"strategy": None, "environments": {}, "required_mcp_tools": [], "notes": []},
            "repository_notes": [],
        }
        (self.repository / ".ai-metadata").write_text(json.dumps(metadata, indent=2) + "\n")
        result = self.cli(
            "start",
            "record deployment knowledge",
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            "python -c \"import json; from pathlib import Path; p=Path('.ai-metadata'); d=json.loads(p.read_text()); d['deployment']['strategy']='release MCP'; d['deployment']['required_mcp_tools']=['mcp__release__deploy']; p.write_text(json.dumps(d, indent=2, sort_keys=True) + '\\\\n')\" && printf 'done\\n' > metadata.txt && git add metadata.txt && git commit -m 'feat: add metadata test'",
            check=True,
        )
        task = self.task_from(result)
        updated = json.loads((self.repository / ".ai-metadata").read_text())

        self.assertEqual(task["target_branch"], "develop")
        self.assertEqual(task["status"], "INTEGRATED")
        self.assertEqual(updated["deployment"]["strategy"], "release MCP")
        self.assertEqual(updated["deployment"]["required_mcp_tools"], ["mcp__release__deploy"])
        self.assertEqual(self.git("show", "develop:metadata.txt").stdout, "done\n")
        self.assertNotEqual(self.git("show", "develop:.ai-metadata", check=False).returncode, 0)

    def test_metadata_three_way_merge_preserves_parallel_fields(self) -> None:
        base = AGENT_TASK.metadata_template("main")
        current = json.loads(json.dumps(base))
        proposed = json.loads(json.dumps(base))
        current["branching"]["strategy"] = "git-flow"
        proposed["deployment"]["required_mcp_tools"] = ["mcp__release__deploy"]
        overwrites: list[str] = []

        merged = AGENT_TASK.merge_metadata(base, current, proposed, "", overwrites)
        self.assertEqual(overwrites, [])
        self.assertEqual(merged["branching"]["strategy"], "git-flow")
        self.assertEqual(merged["deployment"]["required_mcp_tools"], ["mcp__release__deploy"])

        proposed["branching"]["strategy"] = "trunk"
        overwrites = []
        merged = AGENT_TASK.merge_metadata(base, current, proposed, "", overwrites)
        self.assertEqual(overwrites, ["branching.strategy"])
        self.assertEqual(merged["branching"]["strategy"], "trunk")

    def test_metadata_race_does_not_retain_worktrees(self) -> None:
        environment = os.environ.copy()
        environment["AGENT_TASK_STATE_DIR"] = str(self.state)
        environment.pop("SSH_AUTH_SOCK", None)
        first = subprocess.Popen(
            [
                sys.executable,
                str(SCRIPT),
                "start",
                "first metadata writer",
                "--agent",
                "custom",
                "--",
                "sh",
                "-lc",
                "python -c \"import json; from pathlib import Path; p=Path('.ai-metadata'); d=json.loads(p.read_text()); d['branching']['strategy']='first'; p.write_text(json.dumps(d, indent=2, sort_keys=True) + '\\\\n')\" && printf 'first\\n' > first.txt && git add first.txt && git commit -m 'feat: add first' && sleep 1",
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
            "second metadata writer",
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            "python -c \"import json; from pathlib import Path; p=Path('.ai-metadata'); d=json.loads(p.read_text()); d['branching']['strategy']='second'; p.write_text(json.dumps(d, indent=2, sort_keys=True) + '\\\\n')\" && printf 'second\\n' > second.txt && git add second.txt && git commit -m 'feat: add second'",
            check=True,
        )
        first_stdout, first_stderr = first.communicate(timeout=10)
        if first.returncode:
            self.fail(f"first task failed ({first.returncode})\nstdout:\n{first_stdout}\nstderr:\n{first_stderr}")

        tasks = {
            task["description"]: task
            for task in (json.loads(path.read_text()) for path in (self.state / "tasks").glob("*.json"))
        }
        first_task = tasks["first metadata writer"]
        second_task = self.task_from(second)
        metadata = json.loads((self.repository / ".ai-metadata").read_text())

        self.assertEqual(first_task["status"], "INTEGRATED")
        self.assertEqual(first_task["metadata_overwrites"]["fields"], ["branching.strategy"])
        self.assertEqual(second_task["status"], "INTEGRATED")
        self.assertEqual(metadata["branching"]["strategy"], "first")
        self.assertFalse(Path(first_task["worktree_path"]).exists())
        self.assertFalse(Path(str(second_task["worktree_path"])).exists())

    def test_invalid_metadata_is_recorded_without_blocking_code(self) -> None:
        result = self.cli(
            "start",
            "write invalid metadata",
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            "printf '{invalid' > .ai-metadata && printf 'done\\n' > valid.txt && git add valid.txt && git commit -m 'feat: add valid result'",
            check=True,
        )
        task = self.task_from(result)
        canonical = json.loads((self.repository / ".ai-metadata").read_text())

        self.assertEqual(task["status"], "INTEGRATED")
        self.assertIn("metadata_warning", task)
        self.assertIn("{invalid", task["metadata_proposal"]["proposal"])
        self.assertEqual(canonical["schema_version"], 1)
        self.assertFalse(Path(str(task["worktree_path"])).exists())

    def test_unignored_metadata_is_refused_and_removed(self) -> None:
        (self.repository / ".git/info/exclude").write_text("")
        result = self.cli(
            "start",
            "unsafe metadata setup",
            "--agent",
            "custom",
            "--",
            "true",
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("is not ignored", result.stderr)
        self.assertFalse((self.repository / ".ai-metadata").exists())

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

    def test_tracked_metadata_never_reaches_target(self) -> None:
        result = self.cli(
            "start",
            "try to commit repository memory",
            "--agent",
            "custom",
            "--",
            "sh",
            "-lc",
            "git add -f .ai-metadata && git commit -m 'chore: track metadata'",
        )
        task = self.task_from(result)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(task["status"], "RECOVERY_REQUIRED")
        self.assertIn("tracks forbidden .ai-metadata", task["status_reason"])
        self.assertFalse(Path(str(task["worktree_path"])).exists())
        self.assertNotEqual(self.git("cat-file", "-e", "main:.ai-metadata", check=False).returncode, 0)
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

        self.git("config", "alias.co", "checkout")
        aliased = self.cli(
            "start",
            "attempt aliased branch switch",
            "--agent",
            "custom",
            "--",
            "git",
            "co",
            "main",
        )
        self.assertEqual(aliased.returncode, 126)
        self.assertIn("Git aliases are unavailable", aliased.stderr)

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

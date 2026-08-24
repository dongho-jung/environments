#!/usr/bin/env python3
"""Lifecycle harness for disposable coding-agent Git worktrees."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from typing import Any, Iterator, Sequence


CREATED = "CREATED"
RUNNING = "RUNNING"
READY = "READY_TO_INTEGRATE"
INTEGRATING = "INTEGRATING"
VALIDATING = "VALIDATING"
INTEGRATED = "INTEGRATED"
FAILED = "FAILED"
RECOVERY = "RECOVERY_REQUIRED"
MEMORY_NAME = ".ai-memory"
MISSING = object()


class AgentTaskError(RuntimeError):
    pass


class LockBusy(AgentTaskError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def run(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(argv),
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=False,
    )
    if check and result.returncode:
        detail = ((result.stderr or "") + (result.stdout or "")).strip()
        raise AgentTaskError(f"command failed ({result.returncode}): {shlex.join(argv)}\n{detail}")
    return result


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(["git", *args], cwd=cwd, check=check)


def repo_root(cwd: Path) -> Path:
    return Path(git(cwd, "rev-parse", "--show-toplevel").stdout.strip()).resolve()


def common_dir(cwd: Path) -> Path:
    value = git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
    return Path(value).resolve()


def ref(cwd: Path, name: str) -> str:
    return git(cwd, "rev-parse", "--verify", name).stdout.strip()


def branch_exists(repository: Path, branch: str) -> bool:
    return git(repository, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0


def is_ancestor(repository: Path, older: str, newer: str) -> bool:
    return git(repository, "merge-base", "--is-ancestor", older, newer, check=False).returncode == 0


def repo_key(repository: Path) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", repository.name.lower()).strip("-") or "repository"
    digest = hashlib.sha256(str(common_dir(repository)).encode()).hexdigest()[:8]
    return f"{slug}-{digest}"


def process_start(pid: int) -> str | None:
    try:
        value = Path(f"/proc/{pid}/stat").read_text()
        return value[value.rfind(")") + 2 :].split()[19]
    except (OSError, IndexError):
        return None


def process_alive(process: dict[str, Any] | None) -> bool:
    if not process:
        return False
    pid = int(process.get("pid", 0))
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    expected = process.get("start")
    return expected is None or process_start(pid) == expected


class Store:
    def __init__(self) -> None:
        configured = os.environ.get("AGENT_TASK_STATE_DIR")
        self.root = Path(configured).expanduser() if configured else Path.home() / ".local/state/agent-task"
        self.root = self.root.resolve()
        self.tasks = self.root / "tasks"
        self.worktrees = self.root / "worktrees"
        self.integrations = self.root / "integrations"
        self.scratch = self.root / "scratch"
        self.locks = self.root / "locks"
        for path in (self.tasks, self.worktrees, self.integrations, self.scratch, self.locks):
            path.mkdir(parents=True, exist_ok=True)

    def task_path(self, task_id: str) -> Path:
        if not task_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for char in task_id):
            raise AgentTaskError(f"invalid task id: {task_id!r}")
        return self.tasks / f"{task_id}.json"

    def save(self, task: dict[str, Any]) -> None:
        task["updated_at"] = now()
        path = self.task_path(task["task_id"])
        temporary = path.with_name(f".{path.name}.{os.getpid()}")
        temporary.write_text(json.dumps(task, indent=2, sort_keys=True) + "\n")
        temporary.chmod(0o600)
        os.replace(temporary, path)

    def load(self, task_id: str) -> dict[str, Any]:
        path = self.task_path(task_id)
        if not path.exists():
            raise AgentTaskError(f"unknown task: {task_id}")
        return json.loads(path.read_text())

    def all(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for path in self.tasks.glob("*.json"):
            try:
                result.append(json.loads(path.read_text()))
            except (OSError, json.JSONDecodeError):
                print(f"agent-task: unreadable registry entry preserved: {path}", file=sys.stderr)
        return result

    @contextlib.contextmanager
    def lock(self, name: str, *, blocking: bool = True) -> Iterator[None]:
        key = hashlib.sha256(name.encode()).hexdigest()
        descriptor = os.open(self.locks / f"{key}.lock", os.O_CREAT | os.O_RDWR, 0o600)
        operation = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            try:
                fcntl.flock(descriptor, operation)
            except BlockingIOError as error:
                raise LockBusy(f"operation already running: {name}") from error
            yield
        finally:
            os.close(descriptor)


def validate_memory(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AgentTaskError(f"{MEMORY_NAME} must contain a JSON object")
    if value.get("schema_version") != 1:
        raise AgentTaskError(f"{MEMORY_NAME} schema_version must be 1")
    settings = value.get("settings")
    memories = value.get("memories")
    if not isinstance(settings, dict) or not isinstance(memories, dict):
        raise AgentTaskError(f"{MEMORY_NAME} settings and memories must be JSON objects")
    target = settings.get("integration_target")
    if target is not None and not isinstance(target, str):
        raise AgentTaskError(f"{MEMORY_NAME} settings.integration_target must be a string or null")
    for key, memory in memories.items():
        if not isinstance(key, str) or not key or not isinstance(memory, dict):
            raise AgentTaskError(f"{MEMORY_NAME} memories must map non-empty keys to JSON objects")
        if not isinstance(memory.get("summary"), str) or not memory["summary"].strip():
            raise AgentTaskError(f"{MEMORY_NAME} memory {key!r} must have a non-empty summary")
    return value


def read_memory(path: Path) -> dict[str, Any]:
    try:
        return validate_memory(json.loads(path.read_text()))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AgentTaskError(f"cannot read {path}: {error}") from error


def memory_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def write_memory(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}")
    temporary.write_bytes(memory_bytes(value))
    os.replace(temporary, path)


def memory_template(target: str | None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "settings": {"integration_target": target},
        "memories": {},
    }


def primary_worktree(repository: Path) -> Path:
    records = listed_worktrees(repository)
    if records and records[0].get("worktree"):
        return Path(records[0]["worktree"]).resolve()
    return repository.resolve()


def infer_target(repository: Path, current_branch: str) -> str | None:
    if current_branch in ("develop", "main", "master"):
        return current_branch
    remote = git(repository, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", check=False)
    if remote.returncode == 0:
        candidate = remote.stdout.strip().removeprefix("origin/")
        if candidate and branch_exists(repository, candidate):
            return candidate
    candidates = [name for name in ("develop", "main", "master") if branch_exists(repository, name)]
    return candidates[0] if len(candidates) == 1 else None


def ensure_memory(store: Store, repository: Path, current_branch: str) -> tuple[Path, dict[str, Any]]:
    root = primary_worktree(repository)
    path = root / MEMORY_NAME
    with store.lock(f"memory:{common_dir(repository)}"):
        if git(root, "ls-files", "--error-unmatch", MEMORY_NAME, check=False).returncode == 0:
            raise AgentTaskError(f"{path} is tracked; repository memory must remain local")
        created = False
        if not path.exists():
            write_memory(path, memory_template(infer_target(repository, current_branch)))
            created = True
        if git(root, "check-ignore", "--quiet", MEMORY_NAME, check=False).returncode != 0:
            if created:
                path.unlink()
            raise AgentTaskError(f"{path} is not ignored; install the global {MEMORY_NAME} ignore first")
        value = read_memory(path)
    return path, value


def merge_memory(
    base: Any,
    current: Any,
    proposed: Any,
    path: str,
    overwrites: list[str],
) -> Any:
    if proposed == base:
        return current
    if current == base or current == proposed:
        return proposed
    if isinstance(base, dict) and isinstance(current, dict) and isinstance(proposed, dict):
        result: dict[str, Any] = {}
        for key in sorted(base.keys() | current.keys() | proposed.keys()):
            merged = merge_memory(
                base.get(key, MISSING),
                current.get(key, MISSING),
                proposed.get(key, MISSING),
                f"{path}.{key}" if path else key,
                overwrites,
            )
            if merged is not MISSING:
                result[key] = merged
        return result
    overwrites.append(path or "<root>")
    return proposed


def stage_memory(task: dict[str, Any], value: dict[str, Any]) -> None:
    path = Path(task["worktree_path"]) / MEMORY_NAME
    write_memory(path, value)
    task["memory_base"] = value
    task["memory_pending"] = True


def archive_memory_proposal(
    store: Store,
    task: dict[str, Any],
    reason: str,
    *,
    raw: bytes | None = None,
) -> None:
    task["memory_proposal"] = {
        "reason": reason,
        "proposal": raw.decode(errors="replace") if raw is not None else None,
        "recorded_at": now(),
    }
    task["memory_pending"] = False
    task["memory_warning"] = reason
    store.save(task)


def clear_memory_warning(task: dict[str, Any]) -> None:
    task.pop("memory_proposal", None)
    task.pop("memory_warning", None)


def sync_memory(store: Store, task: dict[str, Any]) -> None:
    if not task.get("memory_pending"):
        return
    proposed_path = Path(task["worktree_path"]) / MEMORY_NAME
    if not proposed_path.exists():
        archive_memory_proposal(store, task, f"managed {MEMORY_NAME} copy is missing")
        return
    try:
        raw = proposed_path.read_bytes()
    except OSError as error:
        archive_memory_proposal(store, task, f"cannot read {proposed_path}: {error}")
        return
    try:
        proposed = validate_memory(json.loads(raw))
        base = validate_memory(task["memory_base"])
    except (AgentTaskError, KeyError, UnicodeError, json.JSONDecodeError) as error:
        archive_memory_proposal(store, task, str(error), raw=raw)
        return
    if proposed == base:
        task["memory_pending"] = False
        store.save(task)
        return

    canonical_path = Path(task["memory_path"])
    with store.lock(f"memory:{task['git_common_dir']}"):
        try:
            current = read_memory(canonical_path)
        except AgentTaskError as error:
            archive_memory_proposal(store, task, str(error), raw=raw)
            return
        overwrites: list[str] = []
        merged = validate_memory(merge_memory(base, current, proposed, "", overwrites))
        if overwrites:
            task["memory_overwrites"] = {"fields": overwrites, "recorded_at": now()}
        else:
            task.pop("memory_overwrites", None)
        write_memory(canonical_path, merged)

    task["memory_base"] = merged
    task["memory_pending"] = False
    task["memory_updated"] = True
    clear_memory_warning(task)
    store.save(task)


# The wrapper is an accidental-misuse guard, not a hostile-code sandbox. The
# real binaries remain available to the wrapper inside the mount namespace.
GIT_DENIED = {
    "am",
    "bisect",
    "branch",
    "checkout",
    "cherry-pick",
    "clean",
    "clone",
    "config",
    "fetch",
    "gc",
    "init",
    "maintenance",
    "merge",
    "notes",
    "pull",
    "push",
    "rebase",
    "reflog",
    "remote",
    "replace",
    "reset",
    "restore",
    "revert",
    "sparse-checkout",
    "stash",
    "submodule",
    "switch",
    "symbolic-ref",
    "tag",
    "update-ref",
    "worktree",
}


def deny(message: str) -> int:
    print(f"agent-task policy: denied: {message}", file=sys.stderr)
    return 126


def git_command(args: Sequence[str], worktree: Path) -> tuple[str | None, list[str]]:
    index = 0
    while index < len(args):
        value = args[index]
        if value == "-C":
            if index + 1 >= len(args):
                return None, []
            target = (Path.cwd() / args[index + 1]).resolve()
            if not target.is_relative_to(worktree):
                return "__outside__", []
            index += 2
        elif value.startswith("-C") and len(value) > 2:
            target = (Path.cwd() / value[2:]).resolve()
            if not target.is_relative_to(worktree):
                return "__outside__", []
            index += 1
        elif value in ("-c", "--config-env", "--git-dir", "--work-tree"):
            return "__config__", []
        elif value.startswith(("-c", "--config-env=", "--git-dir=", "--work-tree=", "--exec-path")):
            return "__config__", []
        elif value.startswith("-"):
            index += 1
        else:
            return value, list(args[index + 1 :])
    return None, []


def policy_main(tool: str) -> int:
    policy_path = os.environ.get("AGENT_TASK_POLICY")
    if not policy_path:
        return deny("managed command used without task policy")
    policy = json.loads(Path(policy_path).read_text())
    real = policy.get("real", {}).get(tool)
    if not real:
        return deny(f"{tool} is unavailable")
    args = sys.argv[1:]

    if tool == "git":
        command, tail = git_command(args, Path(policy["worktree"]))
        if command == "__outside__":
            return deny("git -C outside the assigned worktree")
        if command == "__config__":
            return deny("Git directory/config overrides")
        alias = None
        if command:
            configured = subprocess.run(
                [real, "config", "--get", f"alias.{command}"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            alias = configured.stdout.strip() if configured.returncode == 0 else None
        if alias:
            return deny(f"Git aliases are unavailable in managed tasks: {command}")
        if command == "branch" and tail in ([], ["--show-current"]):
            pass
        elif command == "maintenance" and tail and tail[0] == "run" and "--auto" in tail:
            pass
        elif command in GIT_DENIED:
            return deny(f"git {command}")
        if command == "commit" and any(value in ("--amend", "--no-verify") for value in tail):
            return deny("commit --amend/--no-verify")

    if tool in ("terraform", "tofu"):
        if any(value == "-chdir" or value.startswith("-chdir=") for value in args):
            return deny(f"{tool} -chdir")
        command = next((value for value in args if not value.startswith("-")), "version")
        allowed = {"fmt", "validate", "version", "providers", "show", "output", "graph", "init", "plan"}
        if command not in allowed:
            return deny(f"{tool} {command}")
        args = list(args)
        if command == "init":
            if not any(value.startswith("-backend") for value in args):
                args.append("-backend=false")
            if not any(value.startswith("-input") for value in args):
                args.append("-input=false")
        if command == "plan":
            if not any(value.startswith("-lock") for value in args):
                args.append("-lock=false")
            if not any(value.startswith("-input") for value in args):
                args.append("-input=false")

    return subprocess.run([real, *args], check=False).returncode


def agent_state_paths(agent: str) -> list[Path]:
    if agent == "codex":
        candidates = [Path.home() / ".codex"]
    elif agent == "claude":
        candidates = [Path.home() / ".claude", Path.home() / ".claude.json"]
    else:
        candidates = []
    return [path.resolve() for path in candidates if path.exists()]


def sandbox_command(store: Store, task: dict[str, Any], command: Sequence[str], *, agent_state: bool) -> list[str]:
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise AgentTaskError("bubblewrap is required")
    worktree = Path(task["worktree_path"]).resolve()
    common = Path(task["git_common_dir"]).resolve()
    relative = Path(task.get("workdir_relative") or ".")
    working_directory = (worktree / relative).resolve()
    if not working_directory.is_relative_to(worktree) or not working_directory.is_dir():
        working_directory = worktree

    scratch = store.scratch / task["task_id"]
    scratch.mkdir(parents=True, exist_ok=True)
    wrapper = Path(__file__).resolve()
    real: dict[str, str] = {}
    mounts: list[str] = []
    for tool in ("git", "terraform", "tofu"):
        visible_value = shutil.which(tool)
        if not visible_value:
            continue
        visible = Path(visible_value)
        private_source = scratch / f"real-{tool}"
        private_source.touch(exist_ok=True)
        private = Path("/run/agent-task") / f"real-{tool}"
        mounts.extend(("--ro-bind", str(visible.resolve()), str(private)))
        mounts.extend(("--ro-bind", str(wrapper), str(visible)))
        real[tool] = str(private)

    policy = scratch / "policy.json"
    policy.write_text(json.dumps({"worktree": str(worktree), "real": real}))
    argv = [
        bwrap,
        "--die-with-parent",
        "--unshare-pid",
        "--ro-bind",
        "/",
        "/",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        "/tmp",
        "--tmpfs",
        "/run",
        "--dir",
        "/run/agent-task",
        "--ro-bind",
        str(scratch),
        "/run/agent-task",
        "--dir",
        "/tmp/runtime",
        "--bind",
        str(worktree),
        str(worktree),
        "--bind",
        str(common),
        str(common),
        *mounts,
    ]
    if agent_state:
        for path in agent_state_paths(task.get("agent", "custom")):
            argv.extend(("--bind", str(path), str(path)))

    ssh_socket = os.environ.get("SSH_AUTH_SOCK")
    if ssh_socket and Path(ssh_socket).exists() and Path(ssh_socket).is_relative_to(Path("/run")):
        socket_parent = Path(ssh_socket).parent
        parents = [path for path in socket_parent.parents if path != Path("/") and path.is_relative_to(Path("/run"))]
        for path in reversed(parents):
            if path != Path("/run"):
                argv.extend(("--dir", str(path)))
        argv.extend(("--dir", str(socket_parent), "--ro-bind", str(socket_parent), str(socket_parent)))

    argv.extend(
        (
            "--setenv",
            "AGENT_TASK_POLICY",
            "/run/agent-task/policy.json",
            "--setenv",
            "TMPDIR",
            "/tmp",
            "--setenv",
            "XDG_RUNTIME_DIR",
            "/tmp/runtime",
            "--chdir",
            str(working_directory),
            "--",
            *command,
        )
    )
    return argv


def default_agent_command(agent: str, prompt: str | None) -> list[str]:
    if agent == "codex":
        result = ["codex", "--dangerously-bypass-approvals-and-sandbox"]
    elif agent == "claude":
        result = [
            "env",
            "IS_DEMO=1",
            "claude",
            "--ide",
            "--chrome",
            "--allow-dangerously-skip-permissions",
            "--effort",
            "max",
            "--permission-mode",
            "bypassPermissions",
        ]
    else:
        raise AgentTaskError("custom agents require a command after --")
    if prompt:
        result.append(prompt)
    return result


def default_recovery_command(agent: str, prompt: str) -> list[str]:
    if agent == "codex":
        return [
            "codex",
            "resume",
            "--last",
            "--dangerously-bypass-approvals-and-sandbox",
            prompt,
        ]
    if agent == "claude":
        return [
            "env",
            "IS_DEMO=1",
            "claude",
            "--continue",
            "--ide",
            "--chrome",
            "--allow-dangerously-skip-permissions",
            "--effort",
            "max",
            "--permission-mode",
            "bypassPermissions",
            prompt,
        ]
    raise AgentTaskError("custom agents require a recovery command after --")


def resume_hint(agent: str) -> str | None:
    if agent == "codex":
        return "codex resume --last"
    if agent == "claude":
        return "claude --continue"
    return None


def task_environment(task: dict[str, Any]) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "AI_TASK_HARNESS": "agent-task",
            "AI_TASK_ID": task["task_id"],
            "AI_TASK_WORKTREE": task["worktree_path"],
            "AI_TASK_BRANCH": task["branch"],
            "AI_TASK_TARGET_BRANCH": task.get("target_branch") or "",
            "AI_REPO_MEMORY": MEMORY_NAME,
            "AI_REPO_MEMORY_SOURCE": task.get("memory_path") or "",
        }
    )
    return environment


def set_status(store: Store, task: dict[str, Any], status: str, reason: str | None = None) -> None:
    task["status"] = status
    if reason:
        task["status_reason"] = reason
    else:
        task.pop("status_reason", None)
    store.save(task)


def worktree_changes(path: Path) -> tuple[list[str], list[str]]:
    if not path.exists():
        return [], []
    output = git(path, "status", "--porcelain=v1", "--untracked-files=all", "--ignored=matching").stdout
    lines = [
        line
        for line in output.splitlines()
        if line and not (line[:2] in ("??", "!!") and line[3:] == MEMORY_NAME)
    ]
    return [line for line in lines if not line.startswith("!!")], [line for line in lines if line.startswith("!!")]


def current_head(task: dict[str, Any]) -> str | None:
    path = Path(task["worktree_path"])
    if path.exists():
        result = git(path, "rev-parse", "HEAD", check=False)
        if result.returncode == 0:
            return result.stdout.strip()
    repository = Path(task["repository"])
    branch = task.get("branch")
    if branch and branch_exists(repository, branch):
        return ref(repository, f"refs/heads/{branch}")
    return task.get("result_commit")


def commit_tracks_memory(repository: Path, commit: str) -> bool:
    return git(repository, "cat-file", "-e", f"{commit}:{MEMORY_NAME}", check=False).returncode == 0


def unlock_worktree(repository: Path, path: Path) -> None:
    git(repository, "worktree", "unlock", str(path), check=False)


def cleanup_task(store: Store, task: dict[str, Any]) -> bool:
    path = Path(task["worktree_path"])
    changed = False
    if path.exists():
        normal, _ignored = worktree_changes(path)
        if normal:
            set_status(store, task, RECOVERY, f"cleanup preserved uncommitted changes in {path}")
            return False
        sync_memory(store, task)
        normal, ignored = worktree_changes(path)
        if normal:
            set_status(store, task, RECOVERY, f"cleanup preserved uncommitted changes in {path}")
            return False
        if ignored:
            task["discarded_ignored_artifacts"] = {
                "count": len(ignored),
                "sample": [line[3:] for line in ignored[:20]],
            }
            cleaned = git(path, "clean", "-ff", "-d", "-X", check=False)
            if cleaned.returncode:
                set_status(store, task, RECOVERY, f"ignored artifact cleanup failed: {cleaned.stderr.strip()}")
                return False
            normal, ignored = worktree_changes(path)
            if normal or ignored:
                set_status(store, task, RECOVERY, f"cleanup found new changes in {path}")
                return False
        unlock_worktree(Path(task["repository"]), path)
        result = git(Path(task["repository"]), "worktree", "remove", str(path), check=False)
        if result.returncode:
            git(Path(task["repository"]), "worktree", "lock", "--reason", f"agent-task:{task['task_id']}", str(path), check=False)
            set_status(store, task, RECOVERY, f"worktree removal failed: {result.stderr.strip()}")
            return False
        task.setdefault("worktree_cleaned_at", now())
        changed = True

    scratch = store.scratch / task["task_id"]
    shutil.rmtree(scratch, ignore_errors=True)

    branch = task.get("branch")
    repository = Path(task["repository"])
    if branch and branch_exists(repository, branch):
        head = ref(repository, f"refs/heads/{branch}")
        safe_to_delete = (
            (task.get("status") == FAILED and head == task.get("base_sha"))
            or (task.get("integrated_commit") and is_ancestor(repository, head, task["integrated_commit"]))
        )
        if safe_to_delete:
            git(repository, "branch", "-D", branch)
            task.setdefault("branch_deleted_at", now())
            changed = True

    task.pop("cleanup_pending_status", None)
    if (
        task.get("integrated_commit")
        and not branch_exists(repository, branch)
        and (task.get("status") != INTEGRATED or task.get("status_reason"))
    ):
        task["status"] = INTEGRATED
        task.pop("status_reason", None)
        changed = True
    if changed:
        store.save(task)
    return True


def launch_agent(store: Store, task: dict[str, Any], command: Sequence[str]) -> int:
    sandboxed = sandbox_command(store, task, command, agent_state=True)
    process = subprocess.Popen(sandboxed, env=task_environment(task))
    task["process"] = {"pid": process.pid, "start": process_start(process.pid)}
    set_status(store, task, RUNNING)
    try:
        exit_code = process.wait()
    finally:
        task.pop("process", None)
    task["agent_exit_code"] = exit_code
    store.save(task)
    return exit_code


def inspect_result(store: Store, task: dict[str, Any], *, trust_clean_commit: bool = False) -> None:
    path = Path(task["worktree_path"])
    if path.exists():
        normal, _ignored = worktree_changes(path)
        if normal:
            set_status(store, task, RECOVERY, f"uncommitted work preserved in {path}")
            return
        branch = git(path, "branch", "--show-current").stdout.strip()
        if branch != task.get("branch"):
            set_status(store, task, RECOVERY, f"unexpected branch {branch or '(detached)'} preserved")
            return
    head = current_head(task)
    if not head or head == task.get("base_sha"):
        if path.exists():
            sync_memory(store, task)
        if task.get("agent_exit_code", 0):
            set_status(store, task, RECOVERY, f"agent exited with {task['agent_exit_code']}; session preserved")
            return
        set_status(store, task, FAILED, "agent produced no commit")
        cleanup_task(store, task)
        return
    if not is_ancestor(Path(task["repository"]), task["base_sha"], head):
        set_status(store, task, RECOVERY, "result does not descend from the recorded base")
        return
    task["result_commit"] = head
    if commit_tracks_memory(Path(task["repository"]), head):
        raw = (path / MEMORY_NAME).read_bytes() if path.exists() and (path / MEMORY_NAME).exists() else None
        archive_memory_proposal(
            store,
            task,
            f"result commit tracks forbidden {MEMORY_NAME}; remove it from the branch before integration",
            raw=raw,
        )
        set_status(store, task, RECOVERY, f"result commit tracks forbidden {MEMORY_NAME}")
        cleanup_task(store, task)
        return
    if path.exists():
        sync_memory(store, task)
    if task.get("agent_exit_code", 0) and not trust_clean_commit:
        set_status(store, task, RECOVERY, f"agent exited with {task['agent_exit_code']}; clean commit preserved")
        cleanup_task(store, task)
        return
    set_status(store, task, READY)


def preserve_interrupted_task(store: Store, task: dict[str, Any]) -> None:
    task.pop("process", None)
    head = current_head(task)
    if head and head != task.get("base_sha") and is_ancestor(Path(task["repository"]), task["base_sha"], head):
        task["result_commit"] = head
    task["interrupted_at"] = now()
    set_status(store, task, RECOVERY, "agent process ended before lifecycle completion; resume required")


def listed_worktrees(repository: Path) -> list[dict[str, str]]:
    output = git(repository, "worktree", "list", "--porcelain").stdout
    records: list[dict[str, str]] = []
    record: dict[str, str] = {}
    for line in [*output.splitlines(), ""]:
        if not line:
            if record:
                records.append(record)
                record = {}
            continue
        key, _, value = line.partition(" ")
        record[key] = value
    return records


def target_checkout(repository: Path, branch: str) -> Path | None:
    expected = f"refs/heads/{branch}"
    for record in listed_worktrees(repository):
        if record.get("branch") == expected:
            return Path(record["worktree"])
    return None


def remove_integration_worktree(repository: Path, path: Path) -> None:
    if path.exists():
        git(repository, "worktree", "remove", "--force", str(path), check=False)


def validation_commands(task: dict[str, Any], candidate: Path, target_sha: str) -> list[list[str]]:
    commands = [["sh", "-lc", value] for value in task.get("checks", [])]
    changed = git(candidate, "diff", "--name-only", f"{target_sha}..HEAD").stdout.splitlines()
    if any(path.endswith(".tf") for path in changed) and shutil.which("terraform"):
        commands.append(["terraform", "fmt", "-check", "-recursive", "."])
    return commands


def validate_candidate(store: Store, task: dict[str, Any], candidate: Path, target_sha: str) -> bool:
    candidate_task = dict(task)
    candidate_task["worktree_path"] = str(candidate)
    candidate_task["workdir_relative"] = "."
    for command in validation_commands(task, candidate, target_sha):
        print(f"validate: {shlex.join(command)}")
        result = subprocess.run(sandbox_command(store, candidate_task, command, agent_state=False), check=False)
        if result.returncode:
            task["validation_failure"] = {"command": command, "exit_code": result.returncode}
            return False
    task.pop("validation_failure", None)
    return True


def defer_integration(store: Store, task: dict[str, Any], status: str, reason: str) -> bool:
    set_status(store, task, status, reason)
    cleanup_task(store, task)
    return False


def integrate_task(store: Store, task: dict[str, Any]) -> bool:
    repository = Path(task["repository"])
    target = task.get("target_branch")
    result_commit = task.get("result_commit")
    if not target or not result_commit:
        return defer_integration(store, task, RECOVERY, "integration metadata is incomplete")
    if commit_tracks_memory(repository, result_commit):
        return defer_integration(store, task, RECOVERY, f"result commit tracks forbidden {MEMORY_NAME}")

    with store.lock(f"integrate:{common_dir(repository)}:{target}"):
        target_ref = f"refs/heads/{target}"
        if not branch_exists(repository, target):
            return defer_integration(store, task, RECOVERY, f"target branch no longer exists: {target}")
        target_sha = ref(repository, target_ref)
        if is_ancestor(repository, result_commit, target_sha):
            task["integrated_commit"] = target_sha
            set_status(store, task, INTEGRATED, "result was already present on target")
            cleanup_task(store, task)
            return True

        checkout = target_checkout(repository, target)
        if checkout and worktree_changes(checkout)[0]:
            return defer_integration(store, task, READY, f"target checkout is dirty; integration queued: {checkout}")

        candidate = store.integrations / repo_key(repository) / task["task_id"]
        candidate.parent.mkdir(parents=True, exist_ok=True)
        remove_integration_worktree(repository, candidate)
        set_status(store, task, INTEGRATING)
        git(repository, "worktree", "add", "--detach", str(candidate), target_sha)
        try:
            merge = git(
                candidate,
                "-c",
                "commit.gpgsign=false",
                "-c",
                "core.hooksPath=/dev/null",
                "merge",
                "--no-ff",
                "--no-edit",
                result_commit,
                check=False,
            )
            if merge.returncode:
                return defer_integration(store, task, RECOVERY, "integration conflict; committed result preserved")
            candidate_head = ref(candidate, "HEAD")
            set_status(store, task, VALIDATING)
            if not validate_candidate(store, task, candidate, target_sha):
                return defer_integration(store, task, RECOVERY, "merged candidate failed validation")

            if ref(repository, target_ref) != target_sha:
                return defer_integration(store, task, READY, "target advanced during validation; integration queued")
            if checkout:
                if worktree_changes(checkout)[0]:
                    return defer_integration(
                        store, task, READY, f"target checkout became dirty; integration queued: {checkout}"
                    )
                advanced = git(checkout, "-c", "core.hooksPath=/dev/null", "merge", "--ff-only", candidate_head, check=False)
                if advanced.returncode:
                    return defer_integration(store, task, READY, "target could not fast-forward; integration queued")
            else:
                updated = git(repository, "update-ref", target_ref, candidate_head, target_sha, check=False)
                if updated.returncode:
                    return defer_integration(store, task, READY, "target advanced; integration queued")

            task["integrated_commit"] = candidate_head
            set_status(store, task, INTEGRATED)
        finally:
            remove_integration_worktree(repository, candidate)

    cleanup_task(store, task)
    return bool(task.get("integrated_commit"))


def finalize_task(store: Store, task: dict[str, Any], *, integrate: bool, trust_clean_commit: bool = False) -> None:
    inspect_result(store, task, trust_clean_commit=trust_clean_commit)
    if task.get("status") != READY:
        return
    if not cleanup_task(store, task):
        return
    if integrate:
        integrate_task(store, task)


def create_task(store: Store, args: argparse.Namespace) -> dict[str, Any]:
    cwd = Path.cwd().resolve()
    checkout = repo_root(cwd)
    current_branch = git(checkout, "branch", "--show-current").stdout.strip()
    repository = primary_worktree(checkout)
    dirty, _ignored = worktree_changes(checkout)
    if dirty:
        raise AgentTaskError(
            f"current checkout has uncommitted work that a new worktree would not inherit: {checkout}\n"
            "Commit or finish that work first; the harness will not silently omit it."
        )
    memory_path, memory = ensure_memory(store, repository, current_branch)
    configured_target = memory.get("settings", {}).get("integration_target")
    target = args.target or configured_target
    if not target:
        raise AgentTaskError(f"no target branch; set --target or settings.integration_target in {memory_path}")
    if not branch_exists(repository, target):
        raise AgentTaskError(f"target branch from {memory_path} does not exist locally: {target}")
    if git(repository, "cat-file", "-e", f"refs/heads/{target}:{MEMORY_NAME}", check=False).returncode == 0:
        raise AgentTaskError(f"{MEMORY_NAME} is tracked on target branch {target}; repository memory must remain local")
    base = ref(checkout, "HEAD")
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    random = os.urandom(3).hex()
    task_id = f"{stamp}-{random}"
    branch = f"ai/{args.agent}/{task_id}"
    worktree = store.worktrees / repo_key(repository) / task_id
    relative = cwd.relative_to(checkout)
    task: dict[str, Any] = {
        "task_id": task_id,
        "repository": str(repository),
        "git_common_dir": str(common_dir(repository)),
        "base_sha": base,
        "source_branch": current_branch or None,
        "target_branch": target,
        "branch": branch,
        "worktree_path": str(worktree),
        "workdir_relative": str(relative),
        "memory_path": str(memory_path),
        "memory_base": memory,
        "memory_pending": False,
        "agent": args.agent,
        "resume_hint": resume_hint(args.agent),
        "description": args.task or args.description or "interactive agent task",
        "checks": args.check,
        "status": CREATED,
        "created_at": now(),
        "process": {"pid": os.getpid(), "start": process_start(os.getpid()), "role": "launcher"},
    }
    store.save(task)
    worktree.parent.mkdir(parents=True, exist_ok=True)
    try:
        git(repository, "worktree", "add", "-b", branch, str(worktree), base)
        git(repository, "worktree", "lock", "--reason", f"agent-task:{task_id}", str(worktree))
        stage_memory(task, memory)
        store.save(task)
    except Exception as error:
        set_status(store, task, FAILED, str(error))
        raise
    return task


def recreate_worktree(store: Store, task: dict[str, Any]) -> None:
    path = Path(task["worktree_path"])
    if path.exists():
        return
    repository = Path(task["repository"])
    branch = task["branch"]
    if not branch_exists(repository, branch):
        start = task.get("result_commit") or task["base_sha"]
        git(repository, "branch", branch, start)
    path.parent.mkdir(parents=True, exist_ok=True)
    git(repository, "worktree", "add", str(path), branch)
    git(repository, "worktree", "lock", "--reason", f"agent-task:{task['task_id']}", str(path))
    if task.get("memory_path"):
        stage_memory(task, read_memory(Path(task["memory_path"])))
        store.save(task)


def prepare_recovery(task: dict[str, Any]) -> str:
    path = Path(task["worktree_path"])
    notes: list[str] = []
    if task.get("memory_warning"):
        notes.append(
            f"A non-blocking {MEMORY_NAME} proposal is recorded in the task status: "
            f"{task['memory_warning']}."
        )
    if commit_tracks_memory(Path(task["repository"]), ref(path, "HEAD")):
        notes.append(f"Remove {MEMORY_NAME} from the branch with git rm --cached, then commit the deletion.")
    if task.get("interrupted_at"):
        notes.append("Resume the interrupted session and continue from its preserved files and commits.")
        return " ".join(notes)
    normal, _ignored = worktree_changes(path)
    if normal or not task.get("target_branch"):
        notes.append("Resume the preserved files and commit the completed result.")
        return " ".join(notes)
    repository = Path(task["repository"])
    if not branch_exists(repository, task["target_branch"]):
        notes.append(f"The target branch {task['target_branch']} no longer exists; repair the task metadata first.")
        return " ".join(notes)
    if git(path, "rev-parse", "--verify", "MERGE_HEAD", check=False).returncode == 0:
        notes.append("A target merge is already in progress. Resolve only those conflicts and commit.")
        return " ".join(notes)
    target_sha = ref(repository, f"refs/heads/{task['target_branch']}")
    head = ref(path, "HEAD")
    if is_ancestor(repository, target_sha, head):
        notes.append("The task already contains the current target; finish and commit the result.")
        return " ".join(notes)
    merge = git(path, "-c", "commit.gpgsign=false", "merge", "--no-ff", "--no-commit", target_sha, check=False)
    if merge.returncode:
        notes.append("The harness prepared merge conflicts with the current target. Resolve only those conflicts and commit.")
    else:
        notes.append("The harness staged the current target merge. Validate, make any needed fix, and commit it.")
    return " ".join(notes)


def launch_for_task(
    store: Store,
    task: dict[str, Any],
    command: Sequence[str],
    *,
    integrate: bool,
    task_locked: bool = False,
) -> int:
    manager = contextlib.nullcontext() if task_locked else store.lock(f"task:{task['task_id']}")
    with manager:
        current = store.load(task["task_id"])
        task.clear()
        task.update(current)
        try:
            exit_code = launch_agent(store, task, command)
        except Exception as error:
            task.pop("process", None)
            set_status(store, task, FAILED, f"agent launch failed: {error}")
            cleanup_task(store, task)
            raise
        finalize_task(store, task, integrate=integrate)
        return exit_code


def command_start(args: argparse.Namespace, store: Store) -> int:
    explicit = list(args.command)
    if args.agent == "custom" and not explicit:
        raise AgentTaskError("custom agents require a command after --")
    task = create_task(store, args)
    prompt = args.description
    command = explicit or default_agent_command(args.agent, prompt)
    print(f"task: {task['task_id']}\nworktree: {task['worktree_path']}\nbranch: {task['branch']}")
    exit_code = launch_for_task(store, task, command, integrate=not args.no_integrate)
    print(f"status: {task['status']}")
    if task.get("result_commit"):
        print(f"result: {task['result_commit']}")
    if task.get("integrated_commit"):
        print(f"integrated: {task['integrated_commit']} -> {task['target_branch']}")
    if task["status"] == READY and args.no_integrate:
        return 0
    return 0 if task.get("integrated_commit") else (exit_code or 2)


def task_belongs_to_repository(task: dict[str, Any], repository_common_dir: Path) -> bool:
    recorded = task.get("git_common_dir")
    return bool(recorded) and Path(str(recorded)).resolve() == repository_common_dir


def refresh_interrupted_tasks(store: Store, repository: Path) -> list[dict[str, Any]]:
    repository_common_dir = common_dir(repository)
    for snapshot in store.all():
        if not task_belongs_to_repository(snapshot, repository_common_dir):
            continue
        if snapshot.get("status") not in (CREATED, RUNNING) or process_alive(snapshot.get("process")):
            continue
        try:
            with store.lock(f"task:{snapshot['task_id']}", blocking=False):
                current = store.load(snapshot["task_id"])
                if current.get("status") in (CREATED, RUNNING) and not process_alive(current.get("process")):
                    preserve_interrupted_task(store, current)
        except LockBusy:
            continue
    return [task for task in store.all() if task_belongs_to_repository(task, repository_common_dir)]


def choose_recovery_task(tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
    ordered = sorted(tasks, key=lambda task: task.get("updated_at", ""), reverse=True)
    if len(ordered) == 1:
        return ordered[0]
    print("Interrupted tasks in this repository:")
    for index, task in enumerate(ordered, start=1):
        description = " ".join(str(task.get("description") or "interactive task").split())
        print(f"  {index}. {task['task_id']}  {description[:72]}")
    if not sys.stdin.isatty():
        choices = ", ".join(str(task["task_id"]) for task in ordered)
        raise AgentTaskError(f"multiple interrupted tasks require a terminal selection: {choices}")
    while True:
        answer = input("Resume which task? [1], n=new, q=cancel: ").strip().lower() or "1"
        if answer == "n":
            return None
        if answer == "q":
            raise AgentTaskError("cancelled")
        if answer.isdigit() and 1 <= int(answer) <= len(ordered):
            return ordered[int(answer) - 1]
        print("Choose a listed number, n, or q.")


def command_open(args: argparse.Namespace, store: Store) -> int:
    checkout = repo_root(Path.cwd().resolve())
    repository = primary_worktree(checkout)
    tasks = refresh_interrupted_tasks(store, repository)
    if not args.new:
        active = [
            task
            for task in tasks
            if task.get("agent") == args.agent
            and task.get("status") in (CREATED, RUNNING)
            and process_alive(task.get("process"))
        ]
        if active:
            task = max(active, key=lambda item: item.get("updated_at", ""))
            raise AgentTaskError(
                f"{args.agent} task {task['task_id']} is already running in {task['worktree_path']}\n"
                "Use --new only when a separate parallel task is intentional."
            )
        recoverable = [
            task for task in tasks if task.get("agent") == args.agent and task.get("status") == RECOVERY
        ]
        if recoverable:
            selected = choose_recovery_task(recoverable)
            if selected:
                print(
                    f"resuming: {selected['task_id']}\n"
                    f"worktree: {selected['worktree_path']}\n"
                    "Use --new next time to start a separate task."
                )
                recovery_args = argparse.Namespace(
                    task_id=selected["task_id"],
                    agent=args.agent,
                    no_integrate=args.no_integrate,
                    new_session=args.new_session,
                    prompt=args.description,
                    command=list(args.command),
                )
                return command_recover(recovery_args, store)
    return command_start(args, store)


def command_list(_args: argparse.Namespace, store: Store) -> int:
    tasks = sorted(store.all(), key=lambda item: item.get("created_at", ""), reverse=True)
    if not tasks:
        print("No agent tasks.")
        return 0
    print(f"{'TASK':31} {'STATUS':21} {'AGENT':8} {'TARGET':16} {'RESULT':10} NOTE")
    for task in tasks:
        note = "memory" if task.get("memory_warning") or task.get("memory_overwrites") else "-"
        print(
            f"{task['task_id'][:31]:31} {task.get('status', '?')[:21]:21} "
            f"{task.get('agent', '?')[:8]:8} {(task.get('target_branch') or '-')[:16]:16} "
            f"{(task.get('result_commit') or '-')[:10]:10} {note}"
        )
    return 0


def command_status(args: argparse.Namespace, store: Store) -> int:
    if not args.task_id:
        return command_list(args, store)
    print(json.dumps(store.load(args.task_id), indent=2, sort_keys=True))
    return 0


def command_integrate(args: argparse.Namespace, store: Store) -> int:
    with store.lock(f"task:{args.task_id}", blocking=False):
        task = store.load(args.task_id)
        if process_alive(task.get("process")):
            raise AgentTaskError("coding agent is still running")
        if not task.get("result_commit"):
            inspect_result(store, task, trust_clean_commit=True)
        success = task.get("status") == READY and integrate_task(store, task)
    print(f"{task['task_id']}: {task['status']}")
    return 0 if success else 2


def command_recover(args: argparse.Namespace, store: Store) -> int:
    with store.lock(f"task:{args.task_id}", blocking=False):
        task = store.load(args.task_id)
        if process_alive(task.get("process")):
            raise AgentTaskError("coding agent is still running")
        if task.get("integrated_commit"):
            raise AgentTaskError("result is already integrated; use cleanup for retained artifacts")
        recreate_worktree(store, task)
        context = prepare_recovery(task)
        agent = args.agent or task.get("agent", "codex")
        if agent == "custom" and not args.command:
            raise AgentTaskError("custom agents require a command after --")
        task["agent"] = agent
        task["resume_hint"] = resume_hint(agent)
        task["recovery_attempts"] = int(task.get("recovery_attempts", 0)) + 1
        store.save(task)
        prompt = f"Recover agent-task {task['task_id']}: {task.get('description', '')}\n\n{context}"
        extra_prompt = getattr(args, "prompt", None)
        if extra_prompt:
            prompt = f"{prompt}\n\nAdditional instruction: {extra_prompt}"
        command = list(args.command) or (
            default_agent_command(agent, prompt)
            if getattr(args, "new_session", False)
            else default_recovery_command(agent, prompt)
        )
        task.pop("interrupted_at", None)
        store.save(task)
        exit_code = launch_for_task(store, task, command, integrate=not args.no_integrate, task_locked=True)
    print(f"{task['task_id']}: {task['status']}")
    return 0 if task.get("integrated_commit") or (args.no_integrate and task["status"] == READY) else (exit_code or 2)


def command_cleanup(args: argparse.Namespace, store: Store) -> int:
    tasks = store.all() if args.all else [store.load(args.task_id)]
    failed = False
    for task in tasks:
        try:
            with store.lock(f"task:{task['task_id']}", blocking=False):
                task = store.load(task["task_id"])
                if process_alive(task.get("process")):
                    print(f"{task['task_id']}: active; skipped")
                    failed = True
                    continue
                cleaned = cleanup_task(store, task)
        except LockBusy:
            print(f"{task['task_id']}: busy; skipped")
            failed = True
            continue
        print(f"{task['task_id']}: {'cleaned' if cleaned else 'preserved'}")
        failed = failed or not cleaned
    return 2 if failed else 0


def record_orphans(store: Store) -> None:
    known = {str(Path(task["worktree_path"]).resolve()) for task in store.all() if task.get("worktree_path")}
    for repository_directory in store.worktrees.iterdir():
        if not repository_directory.is_dir():
            continue
        for path in repository_directory.iterdir():
            if not path.is_dir() or str(path.resolve()) in known or not (path / ".git").exists():
                continue
            try:
                common = common_dir(path)
                repository = common.parent if common.name == ".git" else repo_root(path)
                head = ref(path, "HEAD")
                branch = git(path, "branch", "--show-current").stdout.strip()
            except AgentTaskError:
                continue
            task_id = f"orphan-{hashlib.sha256(str(path).encode()).hexdigest()[:12]}"
            task = {
                "task_id": task_id,
                "repository": str(repository),
                "git_common_dir": str(common),
                "base_sha": head,
                "branch": branch,
                "target_branch": None,
                "worktree_path": str(path),
                "workdir_relative": ".",
                "agent": "unknown",
                "description": "unregistered managed worktree",
                "result_commit": head,
                "status": RECOVERY,
                "status_reason": "orphan discovered; preserved for operator inspection",
                "created_at": now(),
            }
            store.save(task)


def reconcile_one(store: Store, task: dict[str, Any], *, integrate: bool) -> None:
    if process_alive(task.get("process")):
        return
    status = task.get("status")
    if status == RUNNING:
        preserve_interrupted_task(store, task)
    elif status == CREATED:
        preserve_interrupted_task(store, task)
    elif status == READY and integrate:
        integrate_task(store, task)
    elif status in (INTEGRATED, FAILED):
        cleanup_task(store, task)


def command_reconcile(args: argparse.Namespace, store: Store) -> int:
    failed = False
    try:
        with store.lock("reconcile", blocking=False):
            record_orphans(store)
            repositories: set[Path] = set()
            for task in store.all():
                try:
                    with store.lock(f"task:{task['task_id']}", blocking=False):
                        task = store.load(task["task_id"])
                        reconcile_one(store, task, integrate=not args.no_integrate)
                        repositories.add(Path(task["repository"]))
                except LockBusy:
                    continue
                except Exception as error:
                    failed = True
                    task["reconcile_error"] = str(error)
                    store.save(task)
                    print(f"{task['task_id']}: {error}", file=sys.stderr)
            for repository in repositories:
                if repository.exists():
                    git(repository, "worktree", "prune", check=False)
    except LockBusy:
        return 0
    recovery = [task for task in store.all() if task.get("status") == RECOVERY]
    if recovery:
        failed = True
        print(f"agent-task: {len(recovery)} task(s) require recovery", file=sys.stderr)
    if not args.quiet:
        command_list(args, store)
    return 2 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-task", description="Run coding agents in disposable Git worktrees.")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    opening = subparsers.add_parser("open", help="resume interrupted work or start a new managed session")
    opening.add_argument("description", nargs="?")
    opening.add_argument("--task", help="task description for a custom command")
    opening.add_argument("--agent", choices=("codex", "claude", "custom"), default="codex")
    opening.add_argument("--target", help="local integration target branch")
    opening.add_argument("--check", action="append", default=[], help="post-merge check; repeatable")
    opening.add_argument("--no-integrate", action="store_true")
    opening.add_argument("--new", action="store_true", help="start separately even when interrupted work exists")
    opening.add_argument("--new-session", action="store_true", help="recover files in a fresh agent conversation")
    opening.set_defaults(func=command_open)

    start = subparsers.add_parser("start", help="create a worktree and launch an agent")
    start.add_argument("description", nargs="?")
    start.add_argument("--task", help="task description for a custom command")
    start.add_argument("--agent", choices=("codex", "claude", "custom"), default="codex")
    start.add_argument("--target", help="local integration target branch")
    start.add_argument("--check", action="append", default=[], help="post-merge check; repeatable")
    start.add_argument("--no-integrate", action="store_true")
    start.set_defaults(func=command_start)

    listing = subparsers.add_parser("list", help="list tasks")
    listing.set_defaults(func=command_list)
    status = subparsers.add_parser("status", help="show task metadata")
    status.add_argument("task_id", nargs="?")
    status.set_defaults(func=command_status)
    integrate = subparsers.add_parser("integrate", help="retry integration")
    integrate.add_argument("task_id")
    integrate.set_defaults(func=command_integrate)
    recover = subparsers.add_parser("recover", help="resume a preserved task")
    recover.add_argument("task_id")
    recover.add_argument("--agent", choices=("codex", "claude", "custom"))
    recover.add_argument("--no-integrate", action="store_true")
    recover.add_argument("--new-session", action="store_true", help="recover files without resuming the old chat")
    recover.add_argument("--prompt", help="additional instruction for the resumed chat")
    recover.set_defaults(func=command_recover)
    cleanup = subparsers.add_parser("cleanup", help="remove safe inactive worktrees")
    cleanup_target = cleanup.add_mutually_exclusive_group(required=True)
    cleanup_target.add_argument("task_id", nargs="?")
    cleanup_target.add_argument("--all", action="store_true")
    cleanup.set_defaults(func=command_cleanup)
    reconcile = subparsers.add_parser("reconcile", help="resume lifecycle and prune stale metadata")
    reconcile.add_argument("--no-integrate", action="store_true")
    reconcile.add_argument("--quiet", action="store_true")
    reconcile.set_defaults(func=command_reconcile)
    return parser


def cli_main() -> int:
    raw = sys.argv[1:]
    command: list[str] = []
    if "--" in raw:
        split = raw.index("--")
        command = raw[split + 1 :]
        raw = raw[:split]
    args = build_parser().parse_args(raw)
    args.command = command
    return int(args.func(args, Store()))


def main() -> int:
    try:
        invoked = Path(sys.argv[0]).name
        if invoked in ("git", "terraform", "tofu") and os.environ.get("AGENT_TASK_POLICY"):
            return policy_main(invoked)
        return cli_main()
    except AgentTaskError as error:
        print(f"agent-task: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("agent-task: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

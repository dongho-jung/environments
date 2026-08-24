#!/usr/bin/env python3
"""Small lifecycle harness for disposable coding-agent Git worktrees."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
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
METADATA_NAME = ".ai-metadata"
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
    return hashlib.sha256(str(common_dir(repository)).encode()).hexdigest()[:12]


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


def validate_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AgentTaskError(f"{METADATA_NAME} must contain a JSON object")
    if value.get("schema_version") != 1:
        raise AgentTaskError(f"{METADATA_NAME} schema_version must be 1")
    branching = value.get("branching", {})
    deployment = value.get("deployment", {})
    if not isinstance(branching, dict) or not isinstance(deployment, dict):
        raise AgentTaskError(f"{METADATA_NAME} branching and deployment must be JSON objects")
    target = branching.get("target_branch")
    if target is not None and not isinstance(target, str):
        raise AgentTaskError(f"{METADATA_NAME} branching.target_branch must be a string or null")
    tools = deployment.get("required_mcp_tools", [])
    if not isinstance(tools, list) or not all(isinstance(tool, str) for tool in tools):
        raise AgentTaskError(f"{METADATA_NAME} deployment.required_mcp_tools must be a string array")
    return value


def read_metadata(path: Path) -> dict[str, Any]:
    try:
        return validate_metadata(json.loads(path.read_text()))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AgentTaskError(f"cannot read {path}: {error}") from error


def metadata_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_metadata(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}")
    temporary.write_bytes(metadata_bytes(value))
    os.replace(temporary, path)


def metadata_template(target: str | None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "branching": {"target_branch": target, "strategy": None},
        "deployment": {"strategy": None, "environments": {}, "required_mcp_tools": [], "notes": []},
        "repository_notes": [],
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


def ensure_metadata(store: Store, repository: Path, current_branch: str) -> tuple[Path, dict[str, Any]]:
    root = primary_worktree(repository)
    path = root / METADATA_NAME
    with store.lock(f"metadata:{common_dir(repository)}"):
        if git(root, "ls-files", "--error-unmatch", METADATA_NAME, check=False).returncode == 0:
            raise AgentTaskError(f"{path} is tracked; repository memory must remain local")
        created = False
        if not path.exists():
            write_metadata(path, metadata_template(infer_target(repository, current_branch)))
            created = True
        if git(root, "check-ignore", "--quiet", METADATA_NAME, check=False).returncode != 0:
            if created:
                path.unlink()
            raise AgentTaskError(f"{path} is not ignored; install the global {METADATA_NAME} ignore first")
        value = read_metadata(path)
    return path, value


def merge_metadata(
    base: Any,
    current: Any,
    proposed: Any,
    path: str,
    conflicts: list[str],
) -> Any:
    if proposed == base:
        return current
    if current == base or current == proposed:
        return proposed
    if isinstance(base, dict) and isinstance(current, dict) and isinstance(proposed, dict):
        result: dict[str, Any] = {}
        for key in sorted(base.keys() | current.keys() | proposed.keys()):
            merged = merge_metadata(
                base.get(key, MISSING),
                current.get(key, MISSING),
                proposed.get(key, MISSING),
                f"{path}.{key}" if path else key,
                conflicts,
            )
            if merged is not MISSING:
                result[key] = merged
        return result
    conflicts.append(path or "<root>")
    return current


def stage_metadata(task: dict[str, Any], value: dict[str, Any]) -> None:
    path = Path(task["worktree_path"]) / METADATA_NAME
    write_metadata(path, value)
    task["metadata_base"] = value
    task["metadata_base_digest"] = digest(metadata_bytes(value))
    task["metadata_pending"] = True


def sync_metadata(store: Store, task: dict[str, Any]) -> bool:
    if not task.get("metadata_pending"):
        return True
    proposed_path = Path(task["worktree_path"]) / METADATA_NAME
    if not proposed_path.exists():
        task["metadata_error"] = f"managed {METADATA_NAME} copy is missing"
        store.save(task)
        return False
    try:
        proposed = read_metadata(proposed_path)
        base = validate_metadata(task["metadata_base"])
    except (AgentTaskError, KeyError) as error:
        task["metadata_error"] = str(error)
        store.save(task)
        return False
    if proposed == base:
        proposed_path.unlink()
        task["metadata_pending"] = False
        task.pop("metadata_error", None)
        store.save(task)
        return True

    canonical_path = Path(task["metadata_path"])
    with store.lock(f"metadata:{task['git_common_dir']}"):
        try:
            current = read_metadata(canonical_path)
        except AgentTaskError as error:
            task["metadata_error"] = str(error)
            store.save(task)
            return False
        conflicts: list[str] = []
        merged = validate_metadata(merge_metadata(base, current, proposed, "", conflicts))
        if conflicts:
            task["metadata_conflict"] = {
                "canonical_path": str(canonical_path),
                "fields": conflicts,
            }
            store.save(task)
            return False
        write_metadata(canonical_path, merged)

    proposed_path.unlink()
    task["metadata_base"] = merged
    task["metadata_base_digest"] = digest(metadata_bytes(merged))
    task["metadata_pending"] = False
    task["metadata_updated"] = True
    task.pop("metadata_conflict", None)
    task.pop("metadata_error", None)
    store.save(task)
    return True


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
        if command == "branch" and tail in ([], ["--show-current"]):
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


def task_environment(task: dict[str, Any]) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "AI_TASK_HARNESS": "agent-task",
            "AI_TASK_ID": task["task_id"],
            "AI_TASK_WORKTREE": task["worktree_path"],
            "AI_TASK_BRANCH": task["branch"],
            "AI_TASK_TARGET_BRANCH": task.get("target_branch") or "",
            "AI_REPO_METADATA": METADATA_NAME,
            "AI_REPO_METADATA_SOURCE": task.get("metadata_path") or "",
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
    lines = [line for line in output.splitlines() if line and line[3:] != METADATA_NAME]
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


def unlock_worktree(repository: Path, path: Path) -> None:
    git(repository, "worktree", "unlock", str(path), check=False)


def cleanup_task(store: Store, task: dict[str, Any], *, discard_ignored: bool = False) -> bool:
    path = Path(task["worktree_path"])
    if path.exists():
        normal, ignored = worktree_changes(path)
        if normal:
            task.setdefault("cleanup_pending_status", task.get("status"))
            set_status(store, task, RECOVERY, f"cleanup preserved uncommitted changes in {path}")
            return False
        if not sync_metadata(store, task):
            task.setdefault("cleanup_pending_status", task.get("status"))
            detail = task.get("metadata_error") or f"metadata conflict: {task.get('metadata_conflict', {}).get('fields', [])}"
            set_status(store, task, RECOVERY, f"cleanup preserved {METADATA_NAME}: {detail}")
            return False
        _normal, ignored = worktree_changes(path)
        if ignored and not discard_ignored:
            task.setdefault("cleanup_pending_status", task.get("status"))
            set_status(store, task, RECOVERY, f"cleanup preserved ignored files in {path}")
            return False
        unlock_worktree(Path(task["repository"]), path)
        arguments = ["worktree", "remove"]
        if ignored and discard_ignored:
            arguments.append("--force")
        result = git(Path(task["repository"]), *arguments, str(path), check=False)
        if result.returncode:
            git(Path(task["repository"]), "worktree", "lock", "--reason", f"agent-task:{task['task_id']}", str(path), check=False)
            set_status(store, task, RECOVERY, f"worktree removal failed: {result.stderr.strip()}")
            return False

    branch = task.get("branch")
    repository = Path(task["repository"])
    if branch and branch_exists(repository, branch):
        head = ref(repository, f"refs/heads/{branch}")
        terminal = task.get("cleanup_pending_status") or task.get("status")
        safe_to_delete = (
            (terminal == FAILED and head == task.get("base_sha"))
            or (terminal == INTEGRATED and task.get("integrated_commit") and is_ancestor(repository, head, task["integrated_commit"]))
        )
        if safe_to_delete:
            git(repository, "branch", "-D", branch)

    pending = task.pop("cleanup_pending_status", None)
    if pending:
        set_status(store, task, pending)
    else:
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
        if not sync_metadata(store, task):
            detail = task.get("metadata_error") or f"conflicting fields: {task.get('metadata_conflict', {}).get('fields', [])}"
            set_status(store, task, RECOVERY, f"{METADATA_NAME} update preserved: {detail}")
            return
    head = current_head(task)
    if not head or head == task.get("base_sha"):
        set_status(store, task, FAILED, "agent produced no commit")
        cleanup_task(store, task)
        return
    if not is_ancestor(Path(task["repository"]), task["base_sha"], head):
        set_status(store, task, RECOVERY, "result does not descend from the recorded base")
        return
    task["result_commit"] = head
    if task.get("agent_exit_code", 0) and not trust_clean_commit:
        set_status(store, task, RECOVERY, f"agent exited with {task['agent_exit_code']}; clean commit preserved")
        return
    set_status(store, task, READY)


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


def integrate_task(store: Store, task: dict[str, Any]) -> bool:
    repository = Path(task["repository"])
    target = task.get("target_branch")
    result_commit = task.get("result_commit")
    if not target or not result_commit:
        set_status(store, task, RECOVERY, "integration metadata is incomplete")
        return False

    with store.lock(f"integrate:{common_dir(repository)}:{target}"):
        task.update(store.load(task["task_id"]))
        target_ref = f"refs/heads/{target}"
        if not branch_exists(repository, target):
            set_status(store, task, RECOVERY, f"target branch no longer exists: {target}")
            return False
        target_sha = ref(repository, target_ref)
        if is_ancestor(repository, result_commit, target_sha):
            task["integrated_commit"] = target_sha
            set_status(store, task, INTEGRATED, "result was already present on target")
            cleanup_task(store, task)
            return True

        checkout = target_checkout(repository, target)
        if checkout and worktree_changes(checkout)[0]:
            set_status(store, task, READY, f"target checkout is dirty; integration queued: {checkout}")
            return False

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
                set_status(store, task, RECOVERY, "integration conflict; task worktree preserved")
                return False
            candidate_head = ref(candidate, "HEAD")
            set_status(store, task, VALIDATING)
            if not validate_candidate(store, task, candidate, target_sha):
                set_status(store, task, RECOVERY, "merged candidate failed validation")
                return False

            if ref(repository, target_ref) != target_sha:
                set_status(store, task, READY, "target advanced during validation; integration queued")
                return False
            if checkout:
                if worktree_changes(checkout)[0]:
                    set_status(store, task, READY, f"target checkout became dirty; integration queued: {checkout}")
                    return False
                advanced = git(checkout, "-c", "core.hooksPath=/dev/null", "merge", "--ff-only", candidate_head, check=False)
                if advanced.returncode:
                    set_status(store, task, READY, "target could not fast-forward; integration queued")
                    return False
            else:
                updated = git(repository, "update-ref", target_ref, candidate_head, target_sha, check=False)
                if updated.returncode:
                    set_status(store, task, READY, "target advanced; integration queued")
                    return False

            task["integrated_commit"] = candidate_head
            set_status(store, task, INTEGRATED)
        finally:
            remove_integration_worktree(repository, candidate)

    cleanup_task(store, task)
    return bool(task.get("integrated_commit"))


def finalize_task(store: Store, task: dict[str, Any], *, integrate: bool, trust_clean_commit: bool = False) -> None:
    inspect_result(store, task, trust_clean_commit=trust_clean_commit)
    if task.get("status") == READY and integrate:
        integrate_task(store, task)


def create_task(store: Store, args: argparse.Namespace) -> dict[str, Any]:
    cwd = Path.cwd().resolve()
    checkout = repo_root(cwd)
    current_branch = git(checkout, "branch", "--show-current").stdout.strip()
    repository = primary_worktree(checkout)
    metadata_path, metadata = ensure_metadata(store, repository, current_branch)
    configured_target = metadata.get("branching", {}).get("target_branch")
    target = args.target or configured_target
    if not target:
        raise AgentTaskError(f"no target branch; set --target or branching.target_branch in {metadata_path}")
    if not branch_exists(repository, target):
        raise AgentTaskError(f"target branch from {metadata_path} does not exist locally: {target}")
    if git(repository, "cat-file", "-e", f"refs/heads/{target}:{METADATA_NAME}", check=False).returncode == 0:
        raise AgentTaskError(f"{METADATA_NAME} is tracked on target branch {target}; repository memory must remain local")
    base = ref(repository, f"refs/heads/{target}")
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
        "target_branch": target,
        "branch": branch,
        "worktree_path": str(worktree),
        "workdir_relative": str(relative),
        "metadata_path": str(metadata_path),
        "metadata_base": metadata,
        "metadata_base_digest": digest(metadata_bytes(metadata)),
        "metadata_pending": False,
        "agent": args.agent,
        "description": args.task or args.description or "interactive agent task",
        "checks": args.check,
        "status": CREATED,
        "created_at": now(),
    }
    store.save(task)
    worktree.parent.mkdir(parents=True, exist_ok=True)
    try:
        git(repository, "worktree", "add", "-b", branch, str(worktree), base)
        git(repository, "worktree", "lock", "--reason", f"agent-task:{task_id}", str(worktree))
        stage_metadata(task, metadata)
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
    if task.get("metadata_path"):
        stage_metadata(task, read_metadata(Path(task["metadata_path"])))
        task.pop("metadata_conflict", None)
        task.pop("metadata_error", None)
        store.save(task)


def prepare_recovery(task: dict[str, Any]) -> str:
    path = Path(task["worktree_path"])
    notes: list[str] = []
    if task.get("metadata_conflict"):
        notes.append(
            f"Reconcile {METADATA_NAME} with the read-only current copy at $AI_REPO_METADATA_SOURCE; "
            f"conflicting fields: {task['metadata_conflict'].get('fields', [])}."
        )
    elif task.get("metadata_error"):
        notes.append(f"Repair {METADATA_NAME}: {task['metadata_error']}.")
    normal, _ignored = worktree_changes(path)
    if normal or not task.get("target_branch"):
        notes.append("Resume the preserved files and commit the completed result.")
        return " ".join(notes)
    repository = Path(task["repository"])
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


def launch_for_task(store: Store, task: dict[str, Any], command: Sequence[str], *, integrate: bool) -> int:
    try:
        exit_code = launch_agent(store, task, command)
    except Exception as error:
        task.pop("process", None)
        set_status(store, task, RECOVERY, f"agent launch failed: {error}")
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


def command_list(_args: argparse.Namespace, store: Store) -> int:
    tasks = sorted(store.all(), key=lambda item: item.get("created_at", ""), reverse=True)
    if not tasks:
        print("No agent tasks.")
        return 0
    print(f"{'TASK':31} {'STATUS':21} {'AGENT':8} {'TARGET':16} RESULT")
    for task in tasks:
        print(
            f"{task['task_id'][:31]:31} {task.get('status', '?')[:21]:21} "
            f"{task.get('agent', '?')[:8]:8} {(task.get('target_branch') or '-')[:16]:16} "
            f"{(task.get('result_commit') or '-')[:10]}"
        )
    return 0


def command_status(args: argparse.Namespace, store: Store) -> int:
    if not args.task_id:
        return command_list(args, store)
    print(json.dumps(store.load(args.task_id), indent=2, sort_keys=True))
    return 0


def command_integrate(args: argparse.Namespace, store: Store) -> int:
    task = store.load(args.task_id)
    if process_alive(task.get("process")):
        raise AgentTaskError("coding agent is still running")
    if not task.get("result_commit"):
        inspect_result(store, task, trust_clean_commit=True)
    success = task.get("status") == READY and integrate_task(store, task)
    print(f"{task['task_id']}: {task['status']}")
    return 0 if success else 2


def command_recover(args: argparse.Namespace, store: Store) -> int:
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
    store.save(task)
    prompt = f"Recover agent-task {task['task_id']}: {task.get('description', '')}\n\n{context}"
    command = list(args.command) or default_agent_command(agent, prompt)
    exit_code = launch_for_task(store, task, command, integrate=not args.no_integrate)
    print(f"{task['task_id']}: {task['status']}")
    return 0 if task.get("integrated_commit") or (args.no_integrate and task["status"] == READY) else (exit_code or 2)


def command_cleanup(args: argparse.Namespace, store: Store) -> int:
    tasks = store.all() if args.all else [store.load(args.task_id)]
    failed = False
    for task in tasks:
        if process_alive(task.get("process")):
            print(f"{task['task_id']}: active; skipped")
            failed = True
            continue
        cleaned = cleanup_task(store, task, discard_ignored=args.discard_ignored)
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
    status = task.get("status")
    if status == RUNNING:
        if process_alive(task.get("process")):
            return
        task.pop("process", None)
        finalize_task(store, task, integrate=integrate, trust_clean_commit=True)
    elif status == CREATED:
        finalize_task(store, task, integrate=integrate, trust_clean_commit=True)
    elif status == READY and integrate:
        integrate_task(store, task)
    elif status in (INTEGRATED, FAILED):
        cleanup_task(store, task)


def command_reconcile(args: argparse.Namespace, store: Store) -> int:
    try:
        with store.lock("reconcile", blocking=False):
            record_orphans(store)
            repositories: set[Path] = set()
            for task in store.all():
                try:
                    reconcile_one(store, task, integrate=not args.no_integrate)
                    repositories.add(Path(task["repository"]))
                except Exception as error:
                    task["reconcile_error"] = str(error)
                    store.save(task)
                    if not args.quiet:
                        print(f"{task['task_id']}: {error}", file=sys.stderr)
            for repository in repositories:
                if repository.exists():
                    git(repository, "worktree", "prune", check=False)
    except LockBusy:
        return 0
    if not args.quiet:
        command_list(args, store)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-task", description="Run coding agents in disposable Git worktrees.")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    start = subparsers.add_parser("start", help="create a worktree and launch an agent")
    start.add_argument("description", nargs="?")
    start.add_argument("--task", help="metadata description for a custom command")
    start.add_argument("--agent", choices=("codex", "claude", "custom"), default="codex")
    start.add_argument("--target", help="local target branch; defaults to the current branch")
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
    recover.set_defaults(func=command_recover)
    cleanup = subparsers.add_parser("cleanup", help="remove safe inactive worktrees")
    cleanup_target = cleanup.add_mutually_exclusive_group(required=True)
    cleanup_target.add_argument("task_id", nargs="?")
    cleanup_target.add_argument("--all", action="store_true")
    cleanup.add_argument("--discard-ignored", action="store_true", help="discard only ignored artifacts")
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

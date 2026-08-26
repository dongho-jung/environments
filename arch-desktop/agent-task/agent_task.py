#!/usr/bin/env python3
"""Lifecycle harness for disposable coding-agent Git worktrees."""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import time
from typing import Any, Callable, Iterator, Sequence


CREATED = "CREATED"
RUNNING = "RUNNING"
READY = "READY_TO_INTEGRATE"
INTEGRATING = "INTEGRATING"
VALIDATING = "VALIDATING"
INTEGRATED = "INTEGRATED"
COMPLETED = "COMPLETED_NO_CHANGES"
FAILED = "FAILED"
RECOVERY = "RECOVERY_REQUIRED"
MEMORY_NAME = ".ai-memory"
SESSION_LOCK_NAME = ".ai-lock"
FORBIDDEN_LOCAL_PATHS = (MEMORY_NAME, SESSION_LOCK_NAME)
SESSION_LOCK_SCHEMA = 1
TASK_RECORD_SCHEMA = 2
INBOX_SCHEMA = 1
MAX_JSON_FILE_BYTES = 8 * 1024 * 1024
MAX_MEMORY_BYTES = 1024 * 1024
MAX_INBOX_BYTES = 1024 * 1024
DEFAULT_CHECK_TIMEOUT_SECONDS = 3600.0
HANDOFF_EXIT_CODE = 75
SHELL_SIGINT_EXIT_CODE = 128 + int(signal.SIGINT)
NOTIFICATION_PROTOCOL = 1
LOCK_EXEC_SUBCOMMAND = "__lock-exec"
INBOX_HOOK_SUBCOMMAND = "__inbox-hook"
LOCK_FDS_ENV = "AGENT_TASK_INHERITED_LOCK_FDS"
LOCK_SESSION_PATH_ENV = "AGENT_TASK_LOCK_SESSION_PATH"
LOCK_SESSION_ID_ENV = "AGENT_TASK_LOCK_SESSION_ID"
AGENT_SESSION_PATH_ENV = "AGENT_TASK_SESSION_PATH"
AGENT_SESSION_ID_ENV = "AGENT_TASK_SESSION_ID"
MISSING = object()


class AgentTaskError(RuntimeError):
    pass


class LockBusy(AgentTaskError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def positive_seconds(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a number of seconds") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def validate_identifier(value: str, label: str) -> str:
    if not value or any(
        char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for char in value
    ):
        raise AgentTaskError(f"invalid {label}: {value!r}")
    return value


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
    if not isinstance(process, dict):
        return False
    try:
        pid = int(process.get("pid", 0))
    except (TypeError, ValueError):
        return False
    expected = process.get("start")
    if pid <= 1 or not isinstance(expected, str) or not expected:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return process_start(pid) == expected


def process_record(pid: int, *, role: str | None = None, pgid: int | None = None) -> dict[str, Any] | None:
    start = None
    for _attempt in range(20):
        start = process_start(pid)
        if start is not None:
            break
        try:
            os.kill(pid, 0)
        except OSError:
            break
        time.sleep(0.001)
    if start is None:
        return None
    record: dict[str, Any] = {"pid": pid, "start": start}
    if role:
        record["role"] = role
    if pgid is not None:
        record["pgid"] = pgid
    return record


def write_all(descriptor: int, payload: bytes) -> None:
    remaining = memoryview(payload)
    while remaining:
        written = os.write(descriptor, remaining)
        if not written:
            raise OSError("short write")
        remaining = remaining[written:]


def open_lock_file(path: Path) -> int:
    """Open one user-owned regular lock file without following links."""
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as error:
        raise AgentTaskError(f"cannot safely open lock file {path}: {error}") from error
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            raise AgentTaskError(f"unsafe lock file refused: {path}")
        if stat.S_IMODE(info.st_mode) != 0o600:
            os.fchmod(descriptor, 0o600)
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def read_file_safely(path: Path, *, max_bytes: int = MAX_JSON_FILE_BYTES) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise OSError(f"cannot safely open {path}: {error}") from error
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            raise OSError(f"unsafe file refused: {path}")
        if info.st_size > max_bytes:
            raise OSError(f"file is too large: {path}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise OSError(f"file is too large: {path}")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def read_json_file_safely(path: Path, *, max_bytes: int = MAX_JSON_FILE_BYTES) -> Any:
    return json.loads(read_file_safely(path, max_bytes=max_bytes))


def atomic_write_private(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    if os.path.lexists(path):
        try:
            existing = os.lstat(path)
        except OSError as error:
            raise AgentTaskError(f"cannot inspect existing file {path}: {error}") from error
        if not stat.S_ISREG(existing.st_mode) or existing.st_uid != os.getuid() or existing.st_nlink != 1:
            raise AgentTaskError(f"unsafe destination refused: {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{os.urandom(6).hex()}")
    flags = (
        os.O_CREAT
        | os.O_EXCL
        | os.O_WRONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(temporary, flags, mode)
        try:
            write_all(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def validate_task_record(value: Any, *, expected_task_id: str | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AgentTaskError("task registry entry must be a JSON object")
    task_id = value.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise AgentTaskError("task registry entry has no task id")
    validate_identifier(task_id, "task id in registry")
    if expected_task_id is not None and task_id != expected_task_id:
        raise AgentTaskError(f"task registry id mismatch: expected {expected_task_id!r}, found {task_id!r}")
    schema = value.get("schema_version")
    if schema not in (None, 1, TASK_RECORD_SCHEMA):
        raise AgentTaskError(f"unsupported task registry schema: {schema!r}")
    return value


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
        self.sessions = self.root / "sessions"
        self.inboxes = self.root / "inboxes"
        self.controls = self.root / "controls"
        self.proposals = self.root / "memory-proposals"
        for path in (
            self.root,
            self.tasks,
            self.worktrees,
            self.integrations,
            self.scratch,
            self.locks,
            self.sessions,
            self.inboxes,
            self.controls,
            self.proposals,
        ):
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            info = path.stat(follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
                raise AgentTaskError(f"unsafe state directory refused: {path}")
            if stat.S_IMODE(info.st_mode) != 0o700:
                path.chmod(0o700)

    def task_path(self, task_id: str) -> Path:
        validate_identifier(task_id, "task id")
        return self.tasks / f"{task_id}.json"

    def save(self, task: dict[str, Any]) -> None:
        validate_task_record(task)
        task["schema_version"] = TASK_RECORD_SCHEMA
        task["updated_at"] = now()
        path = self.task_path(task["task_id"])
        payload = (json.dumps(task, indent=2, sort_keys=True) + "\n").encode()
        if len(payload) > MAX_JSON_FILE_BYTES:
            raise AgentTaskError(f"task registry entry is too large: {task['task_id']}")
        atomic_write_private(path, payload)

    def load(self, task_id: str) -> dict[str, Any]:
        path = self.task_path(task_id)
        if not os.path.lexists(path):
            raise AgentTaskError(f"unknown task: {task_id}")
        try:
            return validate_task_record(read_json_file_safely(path), expected_task_id=task_id)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise AgentTaskError(f"cannot safely read task registry entry {path}: {error}") from error

    def all(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for path in self.tasks.glob("*.json"):
            try:
                result.append(validate_task_record(read_json_file_safely(path), expected_task_id=path.stem))
            except (AgentTaskError, OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
                print(f"agent-task: unreadable registry entry preserved: {path}: {error}", file=sys.stderr)
        return result

    def lock_path(self, name: str) -> Path:
        key = hashlib.sha256(name.encode()).hexdigest()
        return self.locks / f"{key}.lock"

    def checkout_identity(self, checkout: Path) -> str:
        return f"{common_dir(checkout)}\0{checkout.resolve()}"

    def checkout_lock_path(self, checkout: Path) -> Path:
        return self.lock_path(f"checkout:{self.checkout_identity(checkout)}")

    def checkout_session_path(self, checkout: Path) -> Path:
        key = hashlib.sha256(self.checkout_identity(checkout).encode()).hexdigest()
        return self.sessions / f"{key}.json"

    def inbox_path(self, session_id: str) -> Path:
        validate_identifier(session_id, "session id")
        return self.inboxes / f"{session_id}.json"

    def control_socket_path(self, session_id: str) -> Path:
        validate_identifier(session_id, "session id")
        return self.controls / f"{session_id}.sock"

    def repository_activity_path(self, repository: Path) -> Path:
        return self.lock_path(f"repository-activity:{common_dir(repository)}")

    @contextlib.contextmanager
    def lock(self, name: str, *, blocking: bool = True) -> Iterator[None]:
        descriptor = open_lock_file(self.lock_path(name))
        operation = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            try:
                fcntl.flock(descriptor, operation)
            except BlockingIOError as error:
                raise LockBusy(f"operation already running: {name}") from error
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


def empty_inbox(session_id: str) -> dict[str, Any]:
    validate_identifier(session_id, "session id")
    return {
        "schema_version": INBOX_SCHEMA,
        "session_id": session_id,
        "messages": [],
        "updated_at": now(),
    }


def validate_inbox(value: Any, *, expected_session_id: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AgentTaskError("session inbox must be a JSON object")
    if value.get("schema_version") != INBOX_SCHEMA:
        raise AgentTaskError(f"unsupported session inbox schema: {value.get('schema_version')!r}")
    session_id = value.get("session_id")
    if session_id != expected_session_id:
        raise AgentTaskError(
            f"session inbox id mismatch: expected {expected_session_id!r}, found {session_id!r}"
        )
    messages = value.get("messages")
    if not isinstance(messages, list):
        raise AgentTaskError("session inbox messages must be a JSON array")
    for message in messages:
        if not isinstance(message, dict):
            raise AgentTaskError("session inbox message must be a JSON object")
        event_id = message.get("id")
        if not isinstance(event_id, str):
            raise AgentTaskError("session inbox message has no event id")
        validate_identifier(event_id, "inbox event id")
        if message.get("status") not in ("pending", "delivered", "accepted", "resolved"):
            raise AgentTaskError(f"invalid inbox event status: {message.get('status')!r}")
        if not isinstance(message.get("prompt"), str) or not message["prompt"].strip():
            raise AgentTaskError("session inbox message has no prompt")
    return value


def read_session_inbox(store: Store, session_id: str) -> dict[str, Any]:
    path = store.inbox_path(session_id)
    if not os.path.lexists(path):
        return empty_inbox(session_id)
    try:
        return validate_inbox(
            read_json_file_safely(path, max_bytes=MAX_INBOX_BYTES),
            expected_session_id=session_id,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise AgentTaskError(f"cannot safely read session inbox {path}: {error}") from error


def write_session_inbox(store: Store, inbox: dict[str, Any]) -> None:
    session_id = inbox.get("session_id")
    if not isinstance(session_id, str):
        raise AgentTaskError("session inbox has no session id")
    validate_inbox(inbox, expected_session_id=session_id)
    inbox["updated_at"] = now()
    payload = (json.dumps(inbox, indent=2, sort_keys=True) + "\n").encode()
    if len(payload) > MAX_INBOX_BYTES:
        raise AgentTaskError(f"session inbox is too large: {session_id}")
    atomic_write_private(store.inbox_path(session_id), payload)


def inbox_event_id(session_id: str, task_id: str) -> str:
    digest = hashlib.sha256(f"integration-ready\0{session_id}\0{task_id}".encode()).hexdigest()[:24]
    return f"ready-{digest}"


def integration_notice_prompt(task: dict[str, Any], event_id: str) -> str:
    task_id = task["task_id"]
    return (
        f"agent-task event {event_id}: managed task {task_id} is complete and waiting for harness integration, "
        "but this session currently owns a repository lease. Finish the smallest safe checkpoint for your "
        "current work. Do not merge, cherry-pick, switch branches, or clean worktrees manually. Then run "
        f"`agent-task handoff {event_id}` so the harness can release this session, finalize any "
        "managed work, and retry the queued integration automatically. Use `agent-task inbox` to inspect "
        "the durable event before handing off."
    )


def enqueue_integration_notice(store: Store, session: dict[str, Any], task: dict[str, Any]) -> str:
    session_id = session.get("session_id")
    if not isinstance(session_id, str):
        raise AgentTaskError("active session has no session id")
    task_id = task.get("task_id")
    if not isinstance(task_id, str):
        raise AgentTaskError("integration notice has no task id")
    event_id = inbox_event_id(session_id, task_id)
    with store.lock(f"inbox:{session_id}"):
        inbox = read_session_inbox(store, session_id)
        existing = next((message for message in inbox["messages"] if message.get("id") == event_id), None)
        if existing is None:
            inbox["messages"].append(
                {
                    "id": event_id,
                    "type": "integration_ready",
                    "status": "pending",
                    "task_id": task_id,
                    "target_branch": task.get("target_branch"),
                    "repository": task.get("repository"),
                    "prompt": integration_notice_prompt(task, event_id),
                    "created_at": now(),
                }
            )
        elif existing.get("status") == "resolved":
            existing["status"] = "pending"
            existing["prompt"] = integration_notice_prompt(task, event_id)
            existing["requeued_at"] = now()
            existing.pop("resolved_at", None)
        write_session_inbox(store, inbox)
    return event_id


def pending_inbox_messages(
    store: Store,
    session_id: str,
    *,
    include_delivered: bool = False,
) -> list[dict[str, Any]]:
    states = {"pending", "delivered"} if include_delivered else {"pending"}
    with store.lock(f"inbox:{session_id}"):
        inbox = read_session_inbox(store, session_id)
        return [dict(message) for message in inbox["messages"] if message.get("status") in states]


def update_inbox_event(
    store: Store,
    session_id: str,
    event_id: str,
    status: str,
    *,
    detail: str | None = None,
) -> dict[str, Any]:
    if status not in ("delivered", "accepted", "resolved"):
        raise AgentTaskError(f"unsupported inbox event transition: {status}")
    with store.lock(f"inbox:{session_id}"):
        inbox = read_session_inbox(store, session_id)
        message = next((item for item in inbox["messages"] if item.get("id") == event_id), None)
        if message is None:
            raise AgentTaskError(f"unknown inbox event: {event_id}")
        current = message.get("status")
        allowed = {
            "delivered": {"pending", "delivered"},
            "accepted": {"pending", "delivered", "accepted"},
            "resolved": {"pending", "delivered", "accepted", "resolved"},
        }[status]
        if current not in allowed:
            raise AgentTaskError(f"inbox event {event_id} cannot move from {current} to {status}")
        message["status"] = status
        message[f"{status}_at"] = now()
        if detail:
            message[f"{status}_via"] = detail
        write_session_inbox(store, inbox)
        return dict(message)


def resolve_task_notices(store: Store, task_id: str) -> None:
    for path in store.inboxes.glob("*.json"):
        session_id = path.stem
        try:
            with store.lock(f"inbox:{session_id}"):
                inbox = read_session_inbox(store, session_id)
                changed = False
                for message in inbox["messages"]:
                    if message.get("task_id") == task_id and message.get("status") != "resolved":
                        message["status"] = "resolved"
                        message["resolved_at"] = now()
                        changed = True
                if changed:
                    write_session_inbox(store, inbox)
        except AgentTaskError as error:
            print(f"agent-task: cannot resolve inbox {path}: {error}", file=sys.stderr)


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
        return validate_memory(read_json_file_safely(path, max_bytes=MAX_MEMORY_BYTES))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise AgentTaskError(f"cannot read {path}: {error}") from error


def memory_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def write_memory(path: Path, value: dict[str, Any]) -> None:
    validate_memory(value)
    atomic_write_private(path, memory_bytes(value))


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


def checkout_session_metadata(
    checkout: Path,
    session_id: str,
    *,
    agent: str | None = None,
    task_id: str | None = None,
    working_directory: Path | None = None,
    inbox_path: Path | None = None,
    control_socket: Path | None = None,
) -> dict[str, Any]:
    owner = process_record(os.getpid(), role="launcher")
    if owner is None:
        raise AgentTaskError("cannot record checkout session process identity")
    metadata: dict[str, Any] = {
        "schema_version": SESSION_LOCK_SCHEMA,
        "kind": "agent-session",
        "session_id": session_id,
        "checkout": str(checkout.resolve()),
        "git_common_dir": str(common_dir(checkout)),
        "base_sha": ref(checkout, "HEAD"),
        "source_branch": git(checkout, "branch", "--show-current").stdout.strip() or None,
        "process": owner,
        "recorded_at": now(),
    }
    if agent:
        metadata["agent"] = agent
    if task_id:
        metadata["task_id"] = task_id
    if working_directory is not None:
        metadata["working_directory"] = str(working_directory.resolve())
    if inbox_path is not None:
        metadata["notification_protocol"] = NOTIFICATION_PROTOCOL
        metadata["inbox_path"] = str(inbox_path)
    if control_socket is not None:
        metadata["control_socket"] = str(control_socket)
    return metadata


def valid_checkout_session(value: Any, checkout: Path) -> bool:
    if not isinstance(value, dict):
        return False
    base_sha = value.get("base_sha")
    source_branch = value.get("source_branch")
    process = value.get("process")
    return bool(
        value.get("schema_version") == SESSION_LOCK_SCHEMA
        and value.get("kind") == "agent-session"
        and value.get("checkout") == str(checkout.resolve())
        and value.get("git_common_dir") == str(common_dir(checkout))
        and isinstance(base_sha, str)
        and re.fullmatch(r"[0-9a-f]{40,64}", base_sha) is not None
        and (source_branch is None or isinstance(source_branch, str))
        and isinstance(process, dict)
        and process_alive(process)
    )


def lock_file_is_busy(path: Path) -> bool:
    descriptor = open_lock_file(path)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        return False
    finally:
        os.close(descriptor)


def read_active_checkout_session(store: Store, checkout: Path, *, attempts: int = 10) -> dict[str, Any] | None:
    """Read metadata only when its corresponding lock still has a live owner."""
    try:
        sources = [(store.checkout_session_path(checkout), store.checkout_lock_path(checkout))]
        legacy = checkout / SESSION_LOCK_NAME
        if os.path.lexists(legacy):
            sources.append((legacy, legacy))
    except (AgentTaskError, OSError):
        return None
    for attempt in range(attempts):
        for metadata_path, lock_path in sources:
            try:
                value = read_json_file_safely(metadata_path)
                if valid_checkout_session(value, checkout) and lock_file_is_busy(lock_path):
                    return value
            except (AgentTaskError, OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
        if attempt + 1 < attempts:
            time.sleep(0.01)
    return None


@contextlib.contextmanager
def repository_activity_lock(
    store: Store,
    repository: Path,
    *,
    exclusive: bool,
    blocking: bool,
) -> Iterator[bool]:
    descriptor = open_lock_file(store.repository_activity_path(repository))
    operation = (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | (0 if blocking else fcntl.LOCK_NB)
    acquired = True
    try:
        try:
            fcntl.flock(descriptor, operation)
        except BlockingIOError:
            acquired = False
        yield acquired
    finally:
        if acquired:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


@contextlib.contextmanager
def checkout_lock_files(store: Store, checkout: Path) -> Iterator[CheckoutReservation | None]:
    """Reserve the stable checkout lock and any live legacy lock inode."""
    descriptors: list[int] = []
    acquired = True
    try:
        stable = open_lock_file(store.checkout_lock_path(checkout))
        descriptors.append(stable)
        try:
            fcntl.flock(stable, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            acquired = False

        legacy = checkout / SESSION_LOCK_NAME
        if acquired and os.path.lexists(legacy):
            legacy_descriptor = open_lock_file(legacy)
            descriptors.append(legacy_descriptor)
            try:
                fcntl.flock(legacy_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                acquired = False
        yield CheckoutReservation(tuple(descriptors)) if acquired else None
    finally:
        for descriptor in reversed(descriptors):
            # Closing keeps an inherited flock alive in the lock supervisor; an
            # explicit LOCK_UN here would release the shared open-file lock.
            os.close(descriptor)


class CheckoutReservation:
    def __init__(self, descriptors: tuple[int, ...]) -> None:
        self.descriptors = descriptors
        self.released = False
        self.session_path: Path | None = None
        self.session_id: str | None = None
        self.handoff_task_ids: list[str] = []

    def __bool__(self) -> bool:
        return bool(self.descriptors)

    def __iter__(self) -> Iterator[int]:
        return iter(self.descriptors)

    def release(self) -> None:
        if self.released:
            return
        for descriptor in self.descriptors:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        self.released = True

    def attach_session(self, path: Path, session_id: str) -> None:
        self.session_path = path
        self.session_id = session_id

    def transfer_session_owner(self, pid: int) -> None:
        if self.session_path is None or self.session_id is None:
            return
        transfer_checkout_session_owner(self.session_path, self.session_id, pid)

    def capture_handoff_tasks(self) -> list[str]:
        if self.session_path is None or self.session_id is None:
            return []
        try:
            value = read_json_file_safely(self.session_path)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return []
        if not isinstance(value, dict) or value.get("session_id") != self.session_id:
            return []
        raw = value.get("handoff_task_ids")
        if not isinstance(raw, list):
            return []
        self.handoff_task_ids = [item for item in raw if isinstance(item, str)]
        return list(self.handoff_task_ids)


def transfer_checkout_session_owner(path: Path, session_id: str, pid: int) -> None:
    owner = process_record(pid, role="lock-supervisor")
    if owner is None:
        raise AgentTaskError("cannot record checkout lock supervisor identity")
    try:
        value = read_json_file_safely(path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise AgentTaskError(f"cannot update checkout session metadata: {error}") from error
    if not isinstance(value, dict) or value.get("session_id") != session_id:
        raise AgentTaskError("checkout session metadata changed before agent launch")
    value["process"] = owner
    value["supervised_at"] = now()
    value["notification_ready"] = False
    value["notification_state"] = "starting"
    atomic_write_private(path, (json.dumps(value, sort_keys=True) + "\n").encode())


def remove_session_metadata(store: Store, checkout: Path, session_id: str) -> None:
    path = store.checkout_session_path(checkout)
    try:
        value = read_json_file_safely(path)
        if isinstance(value, dict) and value.get("session_id") == session_id:
            path.unlink(missing_ok=True)
            store.inbox_path(session_id).unlink(missing_ok=True)
            store.control_socket_path(session_id).unlink(missing_ok=True)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return


@contextlib.contextmanager
def checkout_session_lock(
    store: Store,
    checkout: Path,
    *,
    record_session_base: bool = False,
    agent: str | None = None,
    task_id: str | None = None,
    working_directory: Path | None = None,
) -> Iterator[CheckoutReservation | None]:
    """Reserve a checkout under the repository activity gate."""
    with repository_activity_lock(store, checkout, exclusive=False, blocking=True) as activity_available:
        if not activity_available:
            yield None
            return
        with checkout_lock_files(store, checkout) as checkout_reservation:
            if not checkout_reservation:
                yield None
                return
            session_id = os.urandom(16).hex()
            if record_session_base:
                session_path = store.checkout_session_path(checkout)
                inbox_path = store.inbox_path(session_id)
                control_socket = store.control_socket_path(session_id)
                write_session_inbox(store, empty_inbox(session_id))
                payload = json.dumps(
                    checkout_session_metadata(
                        checkout,
                        session_id,
                        agent=agent,
                        task_id=task_id,
                        working_directory=working_directory or checkout,
                        inbox_path=inbox_path,
                        control_socket=control_socket,
                    ),
                    sort_keys=True,
                ) + "\n"
                atomic_write_private(session_path, payload.encode())
                checkout_reservation.attach_session(session_path, session_id)
            try:
                yield checkout_reservation
            finally:
                if record_session_base and checkout_reservation.released:
                    remove_session_metadata(store, checkout, session_id)


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
        tracked = [
            name
            for name in FORBIDDEN_LOCAL_PATHS
            if git(root, "ls-files", "--error-unmatch", name, check=False).returncode == 0
        ]
        if tracked:
            raise AgentTaskError(f"machine-local paths are tracked in this checkout: {', '.join(tracked)}")
        created = False
        if not os.path.lexists(path):
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
    fingerprint = None
    preserved_path = None
    if raw is not None:
        fingerprint = {
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        proposal_path = store.proposals / f"{task['task_id']}-{os.urandom(4).hex()}.invalid"
        atomic_write_private(proposal_path, raw)
        preserved_path = str(proposal_path)
    task["memory_proposal"] = {
        "reason": reason,
        "fingerprint": fingerprint,
        "preserved_path": preserved_path,
        "recorded_at": now(),
    }
    task["memory_pending"] = False
    task["memory_warning"] = reason
    task.pop("memory_update", None)
    store.save(task)


def clear_memory_warning(task: dict[str, Any]) -> None:
    task.pop("memory_proposal", None)
    task.pop("memory_warning", None)


def capture_memory_proposal(store: Store, task: dict[str, Any]) -> None:
    """Archive a task's local memory edit without changing canonical memory."""
    if not task.get("memory_pending"):
        return
    proposed_path = Path(task["worktree_path"]) / MEMORY_NAME
    if not os.path.lexists(proposed_path):
        archive_memory_proposal(store, task, f"managed {MEMORY_NAME} copy is missing")
        return
    try:
        raw = read_file_safely(proposed_path, max_bytes=MAX_MEMORY_BYTES)
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

    task["memory_update"] = {
        "base": base,
        "proposed": proposed,
        "recorded_at": now(),
    }
    task["memory_pending"] = False
    clear_memory_warning(task)
    store.save(task)


def apply_memory_update(store: Store, task: dict[str, Any]) -> None:
    """Merge a captured proposal only after the code result is integrated."""
    update = task.get("memory_update")
    if not isinstance(update, dict):
        return
    try:
        proposed = validate_memory(update["proposed"])
        base = validate_memory(update["base"])
    except (AgentTaskError, KeyError, TypeError) as error:
        archive_memory_proposal(store, task, str(error), raw=json.dumps(update, sort_keys=True).encode())
        return

    canonical_path = Path(task["memory_path"])
    with store.lock(f"memory:{task['git_common_dir']}"):
        try:
            current = read_memory(canonical_path)
        except AgentTaskError as error:
            archive_memory_proposal(store, task, str(error), raw=memory_bytes(proposed))
            return
        overwrites: list[str] = []
        merged = validate_memory(merge_memory(base, current, proposed, "", overwrites))
        if overwrites:
            task["memory_overwrites"] = {"fields": overwrites, "recorded_at": now()}
        else:
            task.pop("memory_overwrites", None)
        write_memory(canonical_path, merged)

    task["memory_base"] = merged
    task["memory_updated"] = True
    task.pop("memory_update", None)
    clear_memory_warning(task)
    store.save(task)


def task_working_directory(task: dict[str, Any]) -> Path:
    worktree = Path(task["worktree_path"]).resolve()
    relative = Path(task.get("workdir_relative") or ".")
    working_directory = (worktree / relative).resolve()
    if not working_directory.is_relative_to(worktree) or not working_directory.is_dir():
        return worktree
    return working_directory


def command_executable_index(command: Sequence[str], executable: str) -> int | None:
    if not command:
        return None
    index = 0
    if Path(command[0]).name == "env":
        index = 1
        while index < len(command):
            value = command[index]
            if value == "--":
                index += 1
                break
            if "=" in value and not value.startswith("-"):
                index += 1
                continue
            break
    if index < len(command) and Path(command[index]).name == executable:
        return index
    return None


CODEX_GLOBAL_VALUE_OPTIONS = {
    "--add-dir",
    "--ask-for-approval",
    "-a",
    "--cd",
    "-C",
    "--config",
    "-c",
    "--disable",
    "--enable",
    "--image",
    "-i",
    "--model",
    "-m",
    "--local-provider",
    "--profile",
    "-p",
    "--remote",
    "--remote-auth-token-env",
    "--sandbox",
    "-s",
}
CODEX_SUBCOMMANDS = {
    "apply",
    "a",
    "archive",
    "app-server",
    "cloud",
    "cloud-tasks",
    "completion",
    "debug",
    "delete",
    "doctor",
    "exec",
    "e",
    "features",
    "fork",
    "login",
    "logout",
    "mcp",
    "mcp-server",
    "migrate-rollouts",
    "plugin",
    "remote-control",
    "resume",
    "review",
    "sandbox",
    "exec-server",
    "help",
    "unarchive",
    "update",
}


def codex_subcommand(command: Sequence[str]) -> str | None:
    executable = command_executable_index(command, "codex")
    if executable is None:
        return None
    index = executable + 1
    while index < len(command):
        value = command[index]
        if value == "--":
            return None
        if value in CODEX_GLOBAL_VALUE_OPTIONS:
            index += 2
            continue
        if value.startswith("-"):
            index += 1
            continue
        return value if value in CODEX_SUBCOMMANDS else None
    return None


def graceful_codex_interrupt(agent: str, command: Sequence[str], exit_code: int) -> bool:
    return (
        exit_code == SHELL_SIGINT_EXIT_CODE
        and agent == "codex"
        and command_executable_index(command, "codex") is not None
        and codex_subcommand(command) in (None, "resume", "fork")
    )


def record_agent_exit(task: dict[str, Any], exit_code: int, *, graceful: bool = False) -> None:
    task["agent_exit_code"] = exit_code
    if graceful:
        task["agent_exit_graceful"] = True
    else:
        task.pop("agent_exit_graceful", None)


def agent_exit_failed(task: dict[str, Any]) -> bool:
    exit_code = task.get("agent_exit_code", 0)
    return bool(exit_code) and not (
        exit_code == SHELL_SIGINT_EXIT_CODE and task.get("agent_exit_graceful") is True
    )


def normalize_codex_working_directory(command: Sequence[str], origin: Path) -> tuple[list[str], Path]:
    normalized = list(command)
    executable = command_executable_index(normalized, "codex")
    if executable is None:
        return normalized, origin
    selected = origin
    index = executable + 1
    while index < len(normalized):
        value = normalized[index]
        if value == "--":
            break
        candidate: str | None = None
        if value in ("-C", "--cd"):
            if index + 1 >= len(normalized):
                raise AgentTaskError(f"{value} requires a working directory")
            candidate = normalized[index + 1]
            resolved = (origin / candidate).resolve() if not Path(candidate).is_absolute() else Path(candidate).resolve()
            normalized[index + 1] = str(resolved)
            index += 1
        elif value.startswith("--cd="):
            candidate = value.partition("=")[2]
            resolved = (origin / candidate).resolve() if not Path(candidate).is_absolute() else Path(candidate).resolve()
            normalized[index] = f"--cd={resolved}"
        if candidate is not None:
            if not resolved.is_dir():
                raise AgentTaskError(f"Codex working directory does not exist: {resolved}")
            selected = resolved
        index += 1
    return normalized, selected


def prepare_launch_working_directory(args: argparse.Namespace, *, origin: Path | None = None) -> Path:
    base = (origin or Path.cwd()).resolve()
    command, selected = normalize_codex_working_directory(list(getattr(args, "command", [])), base)
    args.command = command
    args.launch_cwd = selected
    return selected


def validate_foreground_agent_command(agent: str, command: Sequence[str], *, lock_managed: bool) -> None:
    if not lock_managed:
        return
    claude = agent == "claude" or command_executable_index(command, "claude") is not None
    if not claude:
        return
    unsafe = {
        "--background",
        "--bg",
        "--tmux",
        "--worktree",
        "-w",
    }
    for value in command:
        if value in unsafe or any(value.startswith(f"{flag}=") for flag in ("--tmux", "--worktree")):
            raise AgentTaskError(
                "Claude background, tmux, and built-in worktree modes own a separate worktree lifecycle; "
                "launch them directly with c instead of nesting them in an agent-task worktree"
            )


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


def native_agent_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        "AGENT_TASK_POLICY",
        LOCK_FDS_ENV,
        LOCK_SESSION_PATH_ENV,
        LOCK_SESSION_ID_ENV,
        AGENT_SESSION_PATH_ENV,
        AGENT_SESSION_ID_ENV,
        "AI_REPO_MEMORY",
        "AI_REPO_MEMORY_SOURCE",
        "AI_TASK_BRANCH",
        "AI_TASK_HARNESS",
        "AI_TASK_ID",
        "AI_TASK_TARGET_BRANCH",
        "AI_TASK_WORKTREE",
    ):
        environment.pop(name, None)
    return environment


def guarded_agent_invocation(
    command: Sequence[str],
    environment: dict[str, str],
    pass_fds: Sequence[int],
    *,
    checkout_reservation: CheckoutReservation | None = None,
) -> tuple[list[str], dict[str, str]]:
    descriptors = tuple(pass_fds)
    if not descriptors:
        return list(command), environment
    guarded_environment = environment.copy()
    guarded_environment[LOCK_FDS_ENV] = ",".join(str(descriptor) for descriptor in descriptors)
    if checkout_reservation is not None and checkout_reservation.session_path is not None:
        assert checkout_reservation.session_id is not None
        guarded_environment[LOCK_SESSION_PATH_ENV] = str(checkout_reservation.session_path)
        guarded_environment[LOCK_SESSION_ID_ENV] = checkout_reservation.session_id
    wrapper = [sys.executable, str(Path(__file__).resolve()), LOCK_EXEC_SUBCOMMAND, "--", *command]
    return wrapper, guarded_environment


def become_child_subreaper() -> None:
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
    except (AttributeError, OSError) as error:
        raise AgentTaskError(f"cannot enable descendant supervision: {error}") from error


def update_session_metadata(path: Path, session_id: str, updates: dict[str, Any]) -> None:
    try:
        value = read_json_file_safely(path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise AgentTaskError(f"cannot update checkout session metadata: {error}") from error
    if not isinstance(value, dict) or value.get("session_id") != session_id:
        raise AgentTaskError("checkout session metadata changed unexpectedly")
    value.update(updates)
    atomic_write_private(path, (json.dumps(value, sort_keys=True) + "\n").encode())


def codex_remote_command(command: Sequence[str], socket_path: Path) -> list[str] | None:
    executable = command_executable_index(command, "codex")
    if executable is None or codex_subcommand(command) not in (None, "resume", "fork"):
        return None
    if any(
        value == "--remote" or value.startswith("--remote=")
        for value in command[executable + 1 :]
    ):
        return None
    result = list(command)
    result[executable + 1 : executable + 1] = ["--remote", f"unix://{socket_path}"]
    return result


def start_codex_app_server(
    command: Sequence[str],
    socket_path: Path,
    inherited_descriptors: Sequence[int],
) -> tuple[int, list[str]] | None:
    remote_command = codex_remote_command(command, socket_path)
    if remote_command is None:
        return None
    executable = command_executable_index(command, "codex")
    assert executable is not None
    socket_path.unlink(missing_ok=True)
    server_command = [*command[: executable + 1], "app-server", "--listen", f"unix://{socket_path}"]
    try:
        server_pid = os.fork()
    except OSError as error:
        raise AgentTaskError(f"cannot start Codex App Server: {error}") from error
    if server_pid == 0:
        for descriptor in inherited_descriptors:
            os.close(descriptor)
        try:
            os.setsid()
            devnull = os.open(os.devnull, os.O_RDWR)
            for descriptor in (0, 1, 2):
                os.dup2(devnull, descriptor)
            if devnull > 2:
                os.close(devnull)
            os.execvpe(server_command[0], server_command, os.environ)
        except OSError:
            os._exit(127)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if socket_path.exists():
            return server_pid, remote_command
        try:
            finished, status = os.waitpid(server_pid, os.WNOHANG)
        except ChildProcessError:
            finished, status = server_pid, 0
        if finished:
            detail = os.waitstatus_to_exitcode(status)
            raise AgentTaskError(f"Codex App Server exited before opening its control socket ({detail})")
        time.sleep(0.02)
    try:
        os.killpg(server_pid, signal.SIGTERM)
    except OSError:
        pass
    raise AgentTaskError("Codex App Server did not open its control socket")


async def _codex_rpc_request(
    websocket: Any,
    request_id: int,
    method: str,
    params: dict[str, Any],
) -> Any:
    await websocket.send(json.dumps({"id": request_id, "method": method, "params": params}))
    deadline = time.monotonic() + 3.0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AgentTaskError(f"Codex App Server timed out during {method}")
        import asyncio

        raw = await asyncio.wait_for(websocket.recv(), timeout=remaining)
        response = json.loads(raw)
        if response.get("id") != request_id:
            continue
        if response.get("error") is not None:
            raise AgentTaskError(f"Codex App Server rejected {method}: {response['error']}")
        return response.get("result")


def codex_status_type(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        status_type = value.get("type")
        return status_type if isinstance(status_type, str) else None
    return None


async def _deliver_codex_prompt(
    socket_path: Path,
    working_directory: Path,
    prompt: str,
    connector: Callable[[], Any] | None,
) -> None:
    if connector is None:
        try:
            from websockets.asyncio.client import unix_connect
        except ImportError as error:
            raise AgentTaskError("python-websockets is required for Codex session notifications") from error

        def default_connector() -> Any:
            return unix_connect(
                str(socket_path),
                uri="ws://localhost/rpc",
                compression=None,
                user_agent_header=None,
                open_timeout=2,
                close_timeout=1,
            )

        connector = default_connector

    async with connector() as websocket:
        request_id = 1
        await _codex_rpc_request(
            websocket,
            request_id,
            "initialize",
            {
                "clientInfo": {
                    "name": "agent-task",
                    "title": "agent-task notification bridge",
                    "version": "1",
                }
            },
        )
        await websocket.send(json.dumps({"method": "initialized", "params": {}}))
        request_id += 1
        for _attempt in range(3):
            listed = await _codex_rpc_request(
                websocket,
                request_id,
                "thread/list",
                {"cwd": str(working_directory.resolve()), "sourceKinds": ["cli", "appServer"]},
            )
            request_id += 1
            threads = listed.get("data", []) if isinstance(listed, dict) else []
            exact = [
                thread
                for thread in threads
                if isinstance(thread, dict)
                and isinstance(thread.get("id"), str)
                and thread.get("cwd") == str(working_directory.resolve())
            ]
            if not exact:
                raise AgentTaskError("Codex App Server has no CLI thread for this checkout")
            receivable = [
                thread
                for thread in exact
                if codex_status_type(thread.get("status")) in ("active", "idle")
            ]
            if not receivable:
                raise AgentTaskError("Codex App Server has no loaded CLI thread for this checkout")
            thread = next(
                (thread for thread in receivable if codex_status_type(thread.get("status")) == "active"),
                receivable[0],
            )
            thread_id = thread["id"]
            status_type = codex_status_type(thread.get("status"))
            try:
                if status_type == "active":
                    detail = await _codex_rpc_request(
                        websocket,
                        request_id,
                        "thread/read",
                        {"threadId": thread_id, "includeTurns": True},
                    )
                    request_id += 1
                    loaded = detail.get("thread", {}) if isinstance(detail, dict) else {}
                    turns = loaded.get("turns", []) if isinstance(loaded, dict) else []
                    active_turn = next(
                        (
                            turn
                            for turn in reversed(turns)
                            if isinstance(turn, dict)
                            and isinstance(turn.get("id"), str)
                            and codex_status_type(turn.get("status")) in ("inProgress", "active")
                        ),
                        turns[-1] if turns and isinstance(turns[-1], dict) else None,
                    )
                    if not isinstance(active_turn, dict) or not isinstance(active_turn.get("id"), str):
                        raise AgentTaskError("Codex active thread has no steerable turn")
                    await _codex_rpc_request(
                        websocket,
                        request_id,
                        "turn/steer",
                        {
                            "threadId": thread_id,
                            "expectedTurnId": active_turn["id"],
                            "input": [{"type": "text", "text": prompt}],
                        },
                    )
                    return
                if status_type == "idle":
                    await _codex_rpc_request(
                        websocket,
                        request_id,
                        "turn/start",
                        {
                            "threadId": thread_id,
                            "input": [{"type": "text", "text": prompt}],
                        },
                    )
                    return
                raise AgentTaskError(f"Codex thread cannot receive a notification while {status_type or 'unknown'}")
            except AgentTaskError:
                if _attempt == 2:
                    raise
                request_id += 1


def deliver_codex_prompt(
    socket_path: Path,
    working_directory: Path,
    prompt: str,
    *,
    connector: Callable[[], Any] | None = None,
) -> None:
    import asyncio

    asyncio.run(_deliver_codex_prompt(socket_path, working_directory, prompt, connector))


def deliver_pending_codex_notifications(
    store: Store,
    session_id: str,
    socket_path: Path,
    working_directory: Path,
) -> None:
    pending = pending_inbox_messages(store, session_id)
    for message in pending:
        deliver_codex_prompt(socket_path, working_directory, message["prompt"])
        update_inbox_event(store, session_id, message["id"], "delivered", detail="codex-app-server")


def terminal_inbox_alert(session_id: str, count: int) -> None:
    message = (
        f"\r\n\a[agent-task] {count} integration handoff event(s) are waiting in session "
        f"{session_id}. Run: agent-task inbox\r\n"
    ).encode()
    try:
        descriptor = os.open("/dev/tty", os.O_WRONLY | getattr(os, "O_NONBLOCK", 0))
    except OSError:
        sys.stderr.write(message.decode())
        sys.stderr.flush()
        return
    try:
        write_all(descriptor, message)
    finally:
        os.close(descriptor)


def accepted_handoff_tasks(store: Store, session_id: str) -> list[str]:
    with store.lock(f"inbox:{session_id}"):
        inbox = read_session_inbox(store, session_id)
        authorized = any(message.get("status") == "accepted" for message in inbox["messages"])
        changed = False
        if authorized:
            for message in inbox["messages"]:
                if (
                    message.get("type") == "integration_ready"
                    and message.get("status") in ("pending", "delivered")
                ):
                    message["status"] = "accepted"
                    message["accepted_at"] = now()
                    message["accepted_via"] = "session-handoff"
                    changed = True
        if changed:
            write_session_inbox(store, inbox)
        return [
            message["task_id"]
            for message in inbox["messages"]
            if message.get("status") == "accepted" and isinstance(message.get("task_id"), str)
        ]


def terminate_process_tree_child(pid: int, signum: int) -> None:
    try:
        os.kill(pid, signum)
    except OSError:
        return


def direct_child_pids(pid: int) -> list[int]:
    try:
        raw = Path(f"/proc/{pid}/task/{pid}/children").read_text()
    except OSError:
        return []
    result: list[int] = []
    for value in raw.split():
        try:
            child = int(value)
        except ValueError:
            continue
        if child > 1:
            result.append(child)
    return result


def command_lock_exec(raw: Sequence[str]) -> int:
    command = list(raw)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise AgentTaskError("lock wrapper has no agent command")
    encoded = os.environ.pop(LOCK_FDS_ENV, "")
    try:
        descriptors = tuple(int(value) for value in encoded.split(",") if value)
    except ValueError as error:
        raise AgentTaskError("lock wrapper received invalid descriptors") from error
    if not descriptors:
        raise AgentTaskError("lock wrapper received no descriptors")
    become_child_subreaper()
    session_path = os.environ.pop(LOCK_SESSION_PATH_ENV, "")
    session_id = os.environ.pop(LOCK_SESSION_ID_ENV, "")
    if bool(session_path) != bool(session_id):
        raise AgentTaskError("lock wrapper received incomplete session metadata")
    metadata: dict[str, Any] = {}
    store: Store | None = None
    control_pid: int | None = None
    control_socket: Path | None = None
    working_directory = Path.cwd().resolve()
    if session_path:
        metadata_path = Path(session_path)
        transfer_checkout_session_owner(metadata_path, session_id, os.getpid())
        try:
            loaded = read_json_file_safely(metadata_path)
            metadata = loaded if isinstance(loaded, dict) else {}
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            metadata = {}
        store = Store()
        working_directory = Path(str(metadata.get("working_directory") or Path.cwd())).resolve()
        socket_value = metadata.get("control_socket")
        if isinstance(socket_value, str):
            control_socket = Path(socket_value)
        if control_socket is not None:
            try:
                started = start_codex_app_server(command, control_socket, descriptors)
                if started is not None:
                    control_pid, command = started
                    update_session_metadata(
                        metadata_path,
                        session_id,
                        {"control_status": "ready", "control_started_at": now()},
                    )
            except AgentTaskError as error:
                update_session_metadata(
                    metadata_path,
                    session_id,
                    {"control_status": "unavailable", "control_error": str(error)},
                )
                print(f"agent-task: Codex notification bridge unavailable: {error}", file=sys.stderr)
        os.environ[AGENT_SESSION_PATH_ENV] = session_path
        os.environ[AGENT_SESSION_ID_ENV] = session_id
    try:
        agent_pid = os.fork()
    except OSError as error:
        raise AgentTaskError(f"cannot start supervised agent: {error}") from error
    if agent_pid == 0:
        for descriptor in descriptors:
            os.close(descriptor)
        try:
            os.execvpe(command[0], command, os.environ)
        except OSError as error:
            print(f"agent-task: cannot execute supervised agent: {error}", file=sys.stderr)
            os._exit(127)

    notification_requested = False
    handoff_requested = False

    def forward_signal(signum: int, _frame: Any) -> None:
        try:
            os.kill(agent_pid, signum)
        except OSError:
            return

    def request_notification(_signum: int, _frame: Any) -> None:
        nonlocal notification_requested
        notification_requested = True

    def request_handoff(_signum: int, _frame: Any) -> None:
        nonlocal handoff_requested
        handoff_requested = True

    previous_handlers = {
        signum: signal.signal(signum, forward_signal)
        for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM)
    }
    previous_handlers[signal.SIGUSR1] = signal.signal(signal.SIGUSR1, request_notification)
    previous_handlers[signal.SIGUSR2] = signal.signal(signal.SIGUSR2, request_handoff)
    if session_path:
        update_session_metadata(
            Path(session_path),
            session_id,
            {
                "notification_ready": True,
                "notification_state": "ready",
                "notification_ready_at": now(),
            },
        )
        notification_requested = True
    main_status: int | None = None
    control_status: int | None = None
    intentional_handoff = False
    handoff_deadline: float | None = None
    descendant_deadline: float | None = None
    notification_retry_at: float | None = None
    notification_closed = False
    try:
        while True:
            reaped_any = False
            while True:
                try:
                    child_pid, status = os.waitpid(-1, os.WNOHANG)
                except InterruptedError:
                    continue
                except ChildProcessError:
                    child_pid = -1
                    break
                if child_pid == 0:
                    break
                reaped_any = True
                if child_pid == agent_pid:
                    main_status = status
                elif control_pid is not None and child_pid == control_pid:
                    control_status = status

            if main_status is not None and session_path and not notification_closed:
                update_session_metadata(
                    Path(session_path),
                    session_id,
                    {
                        "notification_ready": False,
                        "notification_state": "closed",
                        "notification_closed_at": now(),
                    },
                )
                notification_closed = True

            if session_path and store is not None and main_status is None:
                if notification_requested or (
                    notification_retry_at is not None and time.monotonic() >= notification_retry_at
                ):
                    notification_requested = False
                    pending = pending_inbox_messages(store, session_id)
                    if pending:
                        if control_pid is not None and control_status is None and control_socket is not None:
                            try:
                                deliver_pending_codex_notifications(
                                    store,
                                    session_id,
                                    control_socket,
                                    working_directory,
                                )
                                notification_retry_at = None
                            except (AgentTaskError, OSError, json.JSONDecodeError) as error:
                                notification_retry_at = time.monotonic() + 10.0
                                terminal_inbox_alert(session_id, len(pending))
                                update_session_metadata(
                                    Path(session_path),
                                    session_id,
                                    {"last_notification_error": str(error)},
                                )
                        else:
                            terminal_inbox_alert(session_id, len(pending))
                            notification_retry_at = None

                if handoff_requested and not intentional_handoff:
                    tasks = accepted_handoff_tasks(store, session_id)
                    if tasks:
                        intentional_handoff = True
                        handoff_deadline = time.monotonic() + 0.5
                        update_session_metadata(
                            Path(session_path),
                            session_id,
                            {
                                "handoff_task_ids": sorted(set(tasks)),
                                "handoff_started_at": now(),
                            },
                        )
                    handoff_requested = False

                if intentional_handoff and handoff_deadline is not None and time.monotonic() >= handoff_deadline:
                    tasks = accepted_handoff_tasks(store, session_id)
                    update_session_metadata(
                        Path(session_path),
                        session_id,
                        {"handoff_task_ids": sorted(set(tasks))},
                    )
                    terminate_process_tree_child(agent_pid, signal.SIGTERM)
                    handoff_deadline = None

            if main_status is not None and control_pid is not None and control_status is None:
                try:
                    os.killpg(control_pid, signal.SIGTERM)
                except OSError:
                    pass

            if intentional_handoff and main_status is not None:
                descendants = direct_child_pids(os.getpid())
                if descendants and descendant_deadline is None:
                    for descendant in descendants:
                        terminate_process_tree_child(descendant, signal.SIGTERM)
                    descendant_deadline = time.monotonic() + 1.0
                elif descendants and descendant_deadline is not None and time.monotonic() >= descendant_deadline:
                    for descendant in descendants:
                        terminate_process_tree_child(descendant, signal.SIGKILL)
                elif not descendants:
                    descendant_deadline = None

            if child_pid == -1:
                break
            if not reaped_any:
                time.sleep(0.05)
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        if control_socket is not None:
            control_socket.unlink(missing_ok=True)
    if intentional_handoff:
        return HANDOFF_EXIT_CODE
    return os.waitstatus_to_exitcode(main_status) if main_status is not None else 127


def launch_native_agent(
    args: argparse.Namespace,
    *,
    pass_fds: Sequence[int] = (),
    checkout_reservation: CheckoutReservation | None = None,
) -> int:
    explicit = list(args.command)
    if args.agent == "custom" and not explicit:
        raise AgentTaskError("custom agents require a command after --")
    command = explicit or default_agent_command(args.agent, args.description)
    validate_foreground_agent_command(args.agent, command, lock_managed=bool(pass_fds))
    command, environment = guarded_agent_invocation(
        command,
        native_agent_environment(),
        pass_fds,
        checkout_reservation=checkout_reservation,
    )
    return subprocess.run(
        command,
        cwd=Path(getattr(args, "launch_cwd", Path.cwd())).resolve(),
        env=environment,
        check=False,
        pass_fds=tuple(pass_fds),
    ).returncode


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


def default_chat_resume_command(
    agent: str,
    session_id: str | None,
    *,
    last: bool,
    include_non_interactive: bool,
) -> list[str]:
    if agent != "codex":
        raise AgentTaskError("saved-chat resume is currently supported only for Codex")
    if session_id and last:
        raise AgentTaskError("choose a session id or --last, not both")
    command = [
        "codex",
        "resume",
        "--dangerously-bypass-approvals-and-sandbox",
        "-c",
        'tui.resume_cwd="current"',
    ]
    if session_id:
        command.append(session_id)
    else:
        command.append("--all")
        if last:
            command.append("--last")
    if include_non_interactive:
        command.append("--include-non-interactive")
    return command


RESUME_VALUE_OPTIONS = CODEX_GLOBAL_VALUE_OPTIONS


def resume_arguments_have_session(arguments: Sequence[str]) -> bool:
    index = 0
    while index < len(arguments):
        value = arguments[index]
        if value == "--":
            return index + 1 < len(arguments)
        if value in ("--last", "--all"):
            return True
        if value in RESUME_VALUE_OPTIONS:
            index += 2
            continue
        if value.startswith("-") or "=" in value.partition("=")[0]:
            index += 1
            continue
        return True
    return False


def passthrough_chat_resume_command(arguments: Sequence[str]) -> list[str]:
    command = [
        "codex",
        "resume",
        "--dangerously-bypass-approvals-and-sandbox",
        "-c",
        'tui.resume_cwd="current"',
    ]
    if not resume_arguments_have_session(arguments):
        command.append("--all")
    command.extend(arguments)
    return command


def resume_hint(agent: str) -> str | None:
    if agent == "codex":
        return "codex resume --last"
    if agent == "claude":
        return "claude --continue"
    return None


def task_environment(task: dict[str, Any]) -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop(AGENT_SESSION_PATH_ENV, None)
    environment.pop(AGENT_SESSION_ID_ENV, None)
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
        if line
        and not (
            line[:2] in ("??", "!!")
            and line[3:] in (MEMORY_NAME, SESSION_LOCK_NAME)
        )
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


def commit_tracks_forbidden_paths(repository: Path, commit: str) -> list[str]:
    return [
        path
        for path in FORBIDDEN_LOCAL_PATHS
        if git(repository, "cat-file", "-e", f"{commit}:{path}", check=False).returncode == 0
    ]


def forbidden_history(
    repository: Path,
    result_commit: str,
    excluded_commit: str,
) -> list[dict[str, Any]]:
    listed = git(repository, "rev-list", result_commit, f"^{excluded_commit}", check=False)
    if listed.returncode:
        raise AgentTaskError("cannot inspect result commit history")
    findings: list[dict[str, Any]] = []
    for commit in listed.stdout.splitlines():
        paths = commit_tracks_forbidden_paths(repository, commit)
        if paths:
            findings.append({"commit": commit, "paths": paths})
    return findings


def trees_differ(repository: Path, older: str, newer: str) -> bool:
    result = git(repository, "diff", "--quiet", older, newer, check=False)
    if result.returncode not in (0, 1):
        raise AgentTaskError(f"cannot compare result tree {older}..{newer}")
    return result.returncode == 1


def managed_worktree_path(store: Store, task: dict[str, Any]) -> Path:
    value = task.get("worktree_path")
    if not isinstance(value, str) or not value:
        raise AgentTaskError("task has no managed worktree path")
    path = Path(value).resolve()
    root = store.worktrees.resolve()
    if not path.is_relative_to(root) or path.name != task.get("task_id") or path.parent.parent != root:
        raise AgentTaskError(f"refused unexpected managed worktree path: {path}")
    return path


def unlock_worktree(repository: Path, path: Path) -> None:
    git(repository, "worktree", "unlock", str(path), check=False)


def cleanup_task_reserved(store: Store, task: dict[str, Any]) -> bool:
    path = managed_worktree_path(store, task)
    changed = False
    if path.exists():
        normal, _ignored = worktree_changes(path)
        if normal:
            set_status(store, task, RECOVERY, f"cleanup preserved uncommitted changes in {path}")
            return False
        capture_memory_proposal(store, task)
        normal, ignored = worktree_changes(path)
        if normal:
            set_status(store, task, RECOVERY, f"cleanup preserved uncommitted changes in {path}")
            return False
        if ignored:
            summary = {"count": len(ignored), "sample": [line[3:] for line in ignored[:20]]}
            task["discarded_ignored_artifacts"] = summary
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

    if task.get("integrated_commit") or task.get("status") == COMPLETED:
        apply_memory_update(store, task)

    branch = task.get("branch")
    repository = Path(task["repository"])
    if branch and branch_exists(repository, branch):
        head = ref(repository, f"refs/heads/{branch}")
        safe_to_delete = (
            (task.get("status") == FAILED and head == task.get("base_sha"))
            or (
                task.get("status") == COMPLETED
                and isinstance(task.get("base_sha"), str)
                and not trees_differ(repository, task["base_sha"], head)
            )
            or (task.get("integrated_commit") and is_ancestor(repository, head, task["integrated_commit"]))
        )
        if safe_to_delete:
            git(repository, "branch", "-D", branch)
            task.setdefault("branch_deleted_at", now())
            changed = True

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


def cleanup_task(
    store: Store,
    task: dict[str, Any],
    *,
    repository_reserved: bool = False,
    checkout_reserved: bool = False,
) -> bool:
    path = managed_worktree_path(store, task)
    if not path.exists():
        return cleanup_task_reserved(store, task)

    repository = Path(task["repository"])
    activity = (
        contextlib.nullcontext(True)
        if repository_reserved
        else repository_activity_lock(store, repository, exclusive=False, blocking=True)
    )
    with activity as activity_available:
        if not activity_available:
            task["cleanup_warning"] = "repository is busy; cleanup queued"
            store.save(task)
            return False
        reservation = contextlib.nullcontext(True) if checkout_reserved else checkout_lock_files(store, path)
        with reservation as checkout_available:
            if not checkout_available:
                task["cleanup_warning"] = f"worktree has an active agent; cleanup queued: {path}"
                store.save(task)
                return False
            task.pop("cleanup_warning", None)
            return cleanup_task_reserved(store, task)


def launch_agent(
    store: Store,
    task: dict[str, Any],
    command: Sequence[str],
    *,
    pass_fds: Sequence[int] = (),
    checkout_reservation: CheckoutReservation | None = None,
) -> int:
    validate_foreground_agent_command(task.get("agent", "custom"), command, lock_managed=True)
    guarded_command, environment = guarded_agent_invocation(
        command,
        task_environment(task),
        pass_fds,
        checkout_reservation=checkout_reservation,
    )
    task.pop("process", None)
    store.save(task)
    try:
        process = subprocess.Popen(
            guarded_command,
            cwd=task_working_directory(task),
            env=environment,
            pass_fds=tuple(pass_fds),
        )
    except OSError as error:
        raise AgentTaskError(f"cannot launch coding agent: {error}") from error
    identity = process_record(process.pid, role="agent")
    if identity is not None:
        task["process"] = identity
    else:
        task.pop("process", None)
    set_status(store, task, RUNNING)
    try:
        exit_code = process.wait()
    except BaseException:
        task["launcher_interrupted_at"] = now()
        store.save(task)
        raise
    else:
        task.pop("process", None)
    record_agent_exit(
        task,
        exit_code,
        graceful=graceful_codex_interrupt(str(task.get("agent") or "custom"), command, exit_code),
    )
    store.save(task)
    return exit_code


def inspect_result(store: Store, task: dict[str, Any], *, trust_clean_commit: bool = False) -> None:
    path = managed_worktree_path(store, task)
    repository = Path(task["repository"])
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
            capture_memory_proposal(store, task)
        if agent_exit_failed(task):
            set_status(store, task, RECOVERY, f"agent exited with {task['agent_exit_code']}; session preserved")
            return
        set_status(store, task, COMPLETED, "agent completed without repository changes")
        apply_memory_update(store, task)
        cleanup_task(store, task)
        return
    if not is_ancestor(repository, task["base_sha"], head):
        set_status(store, task, RECOVERY, "result does not descend from the recorded base")
        return
    task["result_commit"] = head
    target = task.get("target_branch")
    excluded = (
        ref(repository, f"refs/heads/{target}")
        if isinstance(target, str) and branch_exists(repository, target)
        else task["base_sha"]
    )
    findings = forbidden_history(repository, head, excluded)
    if findings:
        task["forbidden_history"] = findings
        task["memory_pending"] = False
        task.pop("memory_update", None)
        paths = sorted({name for finding in findings for name in finding["paths"]})
        task["memory_warning"] = "result history contains machine-local files; proposal was not captured"
        set_status(store, task, RECOVERY, f"result history tracks forbidden paths: {', '.join(paths)}")
        cleanup_task(store, task)
        return
    task.pop("forbidden_history", None)
    if path.exists():
        capture_memory_proposal(store, task)
    if agent_exit_failed(task) and not trust_clean_commit:
        set_status(store, task, RECOVERY, f"agent exited with {task['agent_exit_code']}; clean commit preserved")
        cleanup_task(store, task)
        return
    if not trees_differ(repository, task["base_sha"], head):
        reason = "agent completed without repository changes"
        if task.get("memory_update"):
            reason += "; repository memory updated"
        set_status(store, task, COMPLETED, reason)
        apply_memory_update(store, task)
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


def remove_integration_worktree(repository: Path, path: Path) -> bool:
    git(repository, "worktree", "remove", "--force", str(path), check=False)
    if path.exists():
        return False
    git(repository, "worktree", "prune", check=False)
    expected = str(path.resolve())
    return all(record.get("worktree") != expected for record in listed_worktrees(repository))


@contextlib.contextmanager
def reserve_repository_checkouts(
    store: Store,
    repository: Path,
) -> Iterator[tuple[bool, Path | None]]:
    """Reserve every checkout while the caller holds the repository activity gate."""
    with contextlib.ExitStack() as stack:
        paths = sorted(
            (Path(record["worktree"]).resolve() for record in listed_worktrees(repository) if record.get("worktree")),
            key=str,
        )
        for path in paths:
            available = stack.enter_context(checkout_lock_files(store, path))
            if not available:
                yield False, path
                return
        yield True, None


def validation_commands(task: dict[str, Any], candidate: Path, target_sha: str) -> list[tuple[list[str], Path]]:
    candidate_task = dict(task)
    candidate_task["worktree_path"] = str(candidate)
    task_directory = task_working_directory(candidate_task)
    commands = [(["sh", "-lc", value], task_directory) for value in task.get("checks", [])]
    changed = git(candidate, "diff", "--name-only", f"{target_sha}..HEAD").stdout.splitlines()
    if any(path.endswith(".tf") for path in changed) and shutil.which("terraform"):
        commands.append((["terraform", "fmt", "-check", "-recursive", "."], candidate))
    return commands


def candidate_is_unchanged(candidate: Path, expected_head: str) -> tuple[bool, str | None]:
    current = git(candidate, "rev-parse", "--verify", "HEAD", check=False)
    if current.returncode or current.stdout.strip() != expected_head:
        return False, "validation changed candidate HEAD"
    normal, _ignored = worktree_changes(candidate)
    if normal:
        return False, f"validation changed candidate files: {normal[:20]}"
    return True, None


def validate_candidate(
    store: Store,
    task: dict[str, Any],
    candidate: Path,
    target_sha: str,
    expected_head: str,
) -> bool:
    candidate_task = dict(task)
    candidate_task["worktree_path"] = str(candidate)
    unchanged, reason = candidate_is_unchanged(candidate, expected_head)
    if not unchanged:
        task["validation_failure"] = {"reason": reason}
        store.save(task)
        return False
    for command, working_directory in validation_commands(task, candidate, target_sha):
        print(f"validate: {shlex.join(command)}")
        process = subprocess.Popen(
            command,
            cwd=working_directory,
            env=task_environment(candidate_task),
            start_new_session=True,
        )
        validation_owner = process_record(process.pid, role="validation", pgid=process.pid)
        if validation_owner is not None:
            task["validation_process"] = validation_owner
        else:
            task.pop("validation_process", None)
        store.save(task)
        timed_out = False
        timeout = float(task.get("check_timeout_seconds", DEFAULT_CHECK_TIMEOUT_SECONDS))
        try:
            exit_code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            validation_owner = validation_owner or process_record(
                process.pid,
                role="validation",
                pgid=process.pid,
            )
            terminate_owned_process(validation_owner)
            try:
                exit_code = process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                exit_code = 124
            else:
                exit_code = 124
        except BaseException:
            terminate_owned_process(validation_owner)
            raise
        finally:
            task.pop("validation_process", None)
            store.save(task)
        unchanged, reason = candidate_is_unchanged(candidate, expected_head)
        if not unchanged:
            task["validation_failure"] = {
                "command": command,
                "exit_code": exit_code,
                "reason": reason,
            }
            store.save(task)
            return False
        if timed_out:
            task["validation_failure"] = {
                "command": command,
                "exit_code": 124,
                "reason": f"validation exceeded {timeout:g} seconds",
            }
            store.save(task)
            return False
        if exit_code:
            task["validation_failure"] = {"command": command, "exit_code": exit_code}
            store.save(task)
            return False
    task.pop("validation_failure", None)
    store.save(task)
    return True


def terminate_owned_process(process: dict[str, Any] | None) -> None:
    if not process_alive(process):
        return
    assert process is not None
    pid = int(process["pid"])
    pgid = int(process.get("pgid", pid))
    try:
        if os.getpgid(pid) != pgid or pgid != pid:
            return
        os.killpg(pgid, signal.SIGTERM)
    except (OSError, ValueError):
        return
    deadline = time.monotonic() + 1.0
    while process_alive(process) and time.monotonic() < deadline:
        time.sleep(0.02)
    if process_alive(process):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except OSError:
            pass


def defer_integration(
    store: Store,
    task: dict[str, Any],
    status: str,
    reason: str,
    *,
    repository_reserved: bool = False,
) -> bool:
    set_status(store, task, status, reason)
    cleanup_task(store, task, repository_reserved=repository_reserved)
    return False


def active_notification_sessions(store: Store, repository: Path) -> list[dict[str, Any]]:
    repository_common_dir = str(common_dir(repository))
    result: list[dict[str, Any]] = []
    for path in store.sessions.glob("*.json"):
        try:
            value = read_json_file_safely(path)
            if not isinstance(value, dict) or value.get("notification_protocol") != NOTIFICATION_PROTOCOL:
                continue
            checkout_value = value.get("checkout")
            if not isinstance(checkout_value, str) or value.get("git_common_dir") != repository_common_dir:
                continue
            process = value.get("process")
            if not isinstance(process, dict) or process.get("role") != "lock-supervisor":
                continue
            if value.get("notification_state") not in ("starting", "ready"):
                continue
            checkout = Path(checkout_value)
            if (
                valid_checkout_session(value, checkout)
                and store.checkout_session_path(checkout) == path
                and lock_file_is_busy(store.checkout_lock_path(checkout))
            ):
                result.append(value)
        except (AgentTaskError, OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return result


def notify_active_sessions(store: Store, repository: Path, task: dict[str, Any]) -> int:
    notified = 0
    for session in active_notification_sessions(store, repository):
        try:
            enqueue_integration_notice(store, session, task)
            process = session.get("process")
            if not process_alive(process):
                continue
            assert isinstance(process, dict)
            if session.get("notification_state") == "ready" and session.get("notification_ready") is True:
                os.kill(int(process["pid"]), signal.SIGUSR1)
            notified += 1
        except (AgentTaskError, OSError, TypeError, ValueError) as error:
            print(
                f"agent-task: could not notify active session {session.get('session_id')}: {error}",
                file=sys.stderr,
            )
    return notified


def queued_for_active_session_reason(store: Store, repository: Path, task: dict[str, Any], reason: str) -> str:
    notified = notify_active_sessions(store, repository, task)
    if notified:
        return f"{reason}; handoff requested from {notified} active session(s)"
    return reason


def integrate_task(store: Store, task: dict[str, Any]) -> bool:
    repository = Path(task["repository"])
    target = task.get("target_branch")
    result_commit = task.get("result_commit")
    if not target or not result_commit:
        return defer_integration(store, task, RECOVERY, "integration metadata is incomplete")
    if branch_exists(repository, target):
        findings = forbidden_history(repository, result_commit, ref(repository, f"refs/heads/{target}"))
        if findings:
            task["forbidden_history"] = findings
            store.save(task)
            paths = sorted({name for finding in findings for name in finding["paths"]})
            return defer_integration(
                store,
                task,
                RECOVERY,
                f"result history tracks forbidden paths: {', '.join(paths)}",
            )

    try:
        with store.lock(f"integrate:{common_dir(repository)}:{target}", blocking=False):
            with repository_activity_lock(store, repository, exclusive=True, blocking=False) as repository_available:
                if not repository_available:
                    return defer_integration(
                        store,
                        task,
                        READY,
                        queued_for_active_session_reason(
                            store,
                            repository,
                            task,
                            "repository has an active agent; integration queued",
                        ),
                    )
                candidate = store.integrations / repo_key(repository) / task["task_id"]
                if not remove_integration_worktree(repository, candidate):
                    return defer_integration(
                        store,
                        task,
                        RECOVERY,
                        f"stale integration worktree could not be removed: {candidate}",
                        repository_reserved=True,
                    )
                with reserve_repository_checkouts(store, repository) as (checkouts_available, busy_checkout):
                    if not checkouts_available:
                        return defer_integration(
                            store,
                            task,
                            READY,
                            queued_for_active_session_reason(
                                store,
                                repository,
                                task,
                                f"checkout has an active or legacy agent; integration queued: {busy_checkout}",
                            ),
                            repository_reserved=True,
                        )
                    return integrate_task_with_repository_reserved(
                        store,
                        task,
                        repository,
                        target,
                        result_commit,
                        candidate,
                    )
    except LockBusy:
        return defer_integration(store, task, READY, "another integration is running; integration queued")


def integrate_task_with_repository_reserved(
    store: Store,
    task: dict[str, Any],
    repository: Path,
    target: str,
    result_commit: str,
    candidate: Path,
) -> bool:
    target_ref = f"refs/heads/{target}"
    if not branch_exists(repository, target):
        return defer_integration(
            store, task, RECOVERY, f"target branch no longer exists: {target}", repository_reserved=True
        )
    target_sha = ref(repository, target_ref)
    base_sha = task.get("base_sha")
    if not isinstance(base_sha, str) or not is_ancestor(repository, base_sha, result_commit):
        return defer_integration(
            store, task, RECOVERY, "result does not descend from the recorded base", repository_reserved=True
        )
    findings = forbidden_history(repository, result_commit, target_sha)
    if findings:
        task["forbidden_history"] = findings
        store.save(task)
        paths = sorted({name for finding in findings for name in finding["paths"]})
        return defer_integration(
            store,
            task,
            RECOVERY,
            f"result history tracks forbidden paths: {', '.join(paths)}",
            repository_reserved=True,
        )
    if is_ancestor(repository, result_commit, target_sha):
        task["integrated_commit"] = target_sha
        set_status(store, task, INTEGRATED, "result was already present on target")
        resolve_task_notices(store, task["task_id"])
        apply_memory_update(store, task)
        cleanup_task(store, task, repository_reserved=True)
        return True
    if not is_ancestor(repository, base_sha, target_sha):
        return defer_integration(
            store,
            task,
            RECOVERY,
            "target no longer descends from the task base; automatic integration refused",
            repository_reserved=True,
        )

    checkout = target_checkout(repository, target)
    if checkout and worktree_changes(checkout)[0]:
        return defer_integration(
            store, task, READY, f"target checkout is dirty; integration queued: {checkout}", repository_reserved=True
        )

    candidate.parent.mkdir(parents=True, exist_ok=True)
    owner = process_record(os.getpid(), role="integration")
    if owner is None:
        return defer_integration(
            store,
            task,
            RECOVERY,
            "cannot record integration process identity",
            repository_reserved=True,
        )
    task["integration_process"] = owner
    task["integration_candidate"] = str(candidate)
    set_status(store, task, INTEGRATING)
    try:
        git(repository, "-c", "core.hooksPath=/dev/null", "worktree", "add", "--detach", str(candidate), target_sha)
        merge = git(
            candidate,
            "-c",
            "core.hooksPath=/dev/null",
            "merge",
            "--no-ff",
            "-m",
            "chore: integrate agent task",
            "-m",
            f"- 관리형 에이전트 결과 통합\n  - 작업 ID: {task['task_id']}",
            result_commit,
            check=False,
        )
        if merge.returncode:
            return defer_integration(
                store, task, RECOVERY, "integration conflict; committed result preserved", repository_reserved=True
            )
        candidate_head = ref(candidate, "HEAD")
        set_status(store, task, VALIDATING)
        if not validate_candidate(store, task, candidate, target_sha, candidate_head):
            return defer_integration(
                store, task, RECOVERY, "merged candidate failed validation", repository_reserved=True
            )

        unchanged, mutation_reason = candidate_is_unchanged(candidate, candidate_head)
        if not unchanged:
            task["validation_failure"] = {"reason": mutation_reason}
            store.save(task)
            return defer_integration(
                store, task, RECOVERY, "merged candidate changed after validation", repository_reserved=True
            )

        if ref(repository, target_ref) != target_sha:
            return defer_integration(
                store, task, READY, "target advanced during validation; integration queued", repository_reserved=True
            )
        current_checkout = target_checkout(repository, target)
        initial_checkout = checkout.resolve() if checkout else None
        final_checkout = current_checkout.resolve() if current_checkout else None
        if final_checkout != initial_checkout:
            return defer_integration(
                store,
                task,
                READY,
                "target checkout topology changed during validation; integration queued",
                repository_reserved=True,
            )
        if current_checkout:
            if worktree_changes(current_checkout)[0]:
                return defer_integration(
                    store,
                    task,
                    READY,
                    f"target checkout became dirty; integration queued: {current_checkout}",
                    repository_reserved=True,
                )
            advanced = git(
                current_checkout,
                "-c",
                "core.hooksPath=/dev/null",
                "merge",
                "--ff-only",
                candidate_head,
                check=False,
            )
            if advanced.returncode:
                return defer_integration(
                    store, task, READY, "target could not fast-forward; integration queued", repository_reserved=True
                )
        else:
            updated = git(repository, "update-ref", target_ref, candidate_head, target_sha, check=False)
            if updated.returncode:
                return defer_integration(
                    store, task, READY, "target advanced; integration queued", repository_reserved=True
                )

        task["integrated_commit"] = candidate_head
        set_status(store, task, INTEGRATED)
        resolve_task_notices(store, task["task_id"])
        apply_memory_update(store, task)
    finally:
        terminate_owned_process(task.get("validation_process"))
        if remove_integration_worktree(repository, candidate):
            task.pop("integration_cleanup_warning", None)
        else:
            task["integration_cleanup_warning"] = f"integration worktree cleanup failed: {candidate}"
        task.pop("validation_process", None)
        task.pop("integration_process", None)
        task.pop("integration_candidate", None)
        store.save(task)

    cleanup_task(store, task, repository_reserved=True)
    return bool(task.get("integrated_commit"))


def finalize_task(store: Store, task: dict[str, Any], *, integrate: bool, trust_clean_commit: bool = False) -> None:
    inspect_result(store, task, trust_clean_commit=trust_clean_commit)
    if task.get("status") != READY:
        return
    cleaned = cleanup_task(store, task)
    if integrate and bool(task.get("auto_integrate", True)) and cleaned:
        integrate_task(store, task)


def active_branch_creation_base(
    repository: Path,
    branch: str,
    captured_base: str,
    target_sha: str,
    live_head: str,
    recorded_at: str | None,
) -> str | None:
    """Return this session's actual branch-creation commit when reflog records it."""
    if not recorded_at:
        return None
    try:
        recorded_epoch = dt.datetime.fromisoformat(recorded_at).timestamp()
    except (TypeError, ValueError):
        return None
    result = git(
        repository,
        "reflog",
        "show",
        "--format=%H%x00%ct%x00%gs",
        f"refs/heads/{branch}",
        check=False,
    )
    if result.returncode:
        return None
    for line in result.stdout.splitlines():
        fields = line.split("\0", 2)
        if len(fields) != 3:
            continue
        commit, epoch_value, message = fields
        if not message.startswith("branch: Created from"):
            continue
        try:
            created_epoch = float(epoch_value)
        except ValueError:
            continue
        if created_epoch + 1 < recorded_epoch:
            continue
        if (
            is_ancestor(repository, captured_base, commit)
            and is_ancestor(repository, commit, target_sha)
            and is_ancestor(repository, commit, live_head)
        ):
            return commit
    return None


def choose_task_base(
    repository: Path,
    checkout: Path,
    target: str,
    args: argparse.Namespace,
) -> tuple[str, str, str | None]:
    """Choose a base that is guaranteed to be in the integration target's history."""
    target_sha = ref(repository, f"refs/heads/{target}")
    if not bool(getattr(args, "isolate_from_active_checkout", False)):
        return target_sha, "integration_target", target

    recorded_base = getattr(args, "active_session_base_sha", None)
    source_branch = getattr(args, "active_session_source_branch", None)
    recorded_at = getattr(args, "active_session_recorded_at", None)
    if isinstance(recorded_base, str):
        resolved = git(repository, "rev-parse", "--verify", f"{recorded_base}^{{commit}}", check=False)
        if resolved.returncode == 0:
            captured = resolved.stdout.strip()
            if is_ancestor(repository, captured, target_sha):
                live_branch = git(checkout, "branch", "--show-current", check=False).stdout.strip()
                if live_branch == target:
                    return captured, "checkout_session_start", source_branch
                live_head = git(checkout, "rev-parse", "--verify", "HEAD", check=False)
                if live_head.returncode == 0:
                    live_head_sha = live_head.stdout.strip()
                    created = active_branch_creation_base(
                        repository,
                        live_branch,
                        captured,
                        target_sha,
                        live_head_sha,
                        recorded_at if isinstance(recorded_at, str) else None,
                    )
                    if created:
                        return created, "active_branch_creation", source_branch
                    merge_base = git(
                        repository,
                        "merge-base",
                        live_head_sha,
                        target_sha,
                        check=False,
                    )
                    if merge_base.returncode == 0:
                        fork = merge_base.stdout.strip()
                        if is_ancestor(repository, captured, fork) and is_ancestor(repository, fork, target_sha):
                            return fork, "active_checkout_fork_point", source_branch
                return captured, "checkout_session_start", source_branch

    print(f"active checkout has no usable session base; starting from target {target}")
    return target_sha, "integration_target", target


def create_task(store: Store, args: argparse.Namespace) -> dict[str, Any]:
    cwd = Path(getattr(args, "launch_cwd", Path.cwd())).resolve()
    checkout = repo_root(cwd)
    current_branch = git(checkout, "branch", "--show-current").stdout.strip()
    repository = primary_worktree(checkout)
    dirty, _ignored = worktree_changes(checkout)
    if dirty:
        print(f"current checkout changes stay in place and are not inherited: {checkout}")
    inference_branch = getattr(args, "active_session_source_branch", None) or current_branch
    memory_path, memory = ensure_memory(store, repository, inference_branch)
    configured_target = memory.get("settings", {}).get("integration_target")
    target = args.target or configured_target
    if not target:
        raise AgentTaskError(f"no target branch; set --target or settings.integration_target in {memory_path}")
    if not branch_exists(repository, target):
        raise AgentTaskError(f"target branch from {memory_path} does not exist locally: {target}")
    tracked_target_paths = commit_tracks_forbidden_paths(repository, ref(repository, f"refs/heads/{target}"))
    if tracked_target_paths:
        raise AgentTaskError(
            f"machine-local paths are tracked on target branch {target}: {', '.join(tracked_target_paths)}"
        )
    base, base_source, source_branch = choose_task_base(repository, checkout, target, args)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    random = os.urandom(3).hex()
    task_id = f"{stamp}-{random}"
    branch = f"ai/{args.agent}/{task_id}"
    worktree = store.worktrees / repo_key(repository) / task_id
    relative = cwd.relative_to(checkout)
    owner = process_record(os.getpid(), role="launcher")
    if owner is None:
        raise AgentTaskError("cannot record task launcher process identity")
    task: dict[str, Any] = {
        "schema_version": TASK_RECORD_SCHEMA,
        "task_id": task_id,
        "repository": str(repository),
        "git_common_dir": str(common_dir(repository)),
        "base_sha": base,
        "base_source": base_source,
        "source_branch": source_branch,
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
        "check_timeout_seconds": float(
            getattr(args, "check_timeout", DEFAULT_CHECK_TIMEOUT_SECONDS)
        ),
        "auto_integrate": not bool(getattr(args, "no_integrate", False)),
        "status": CREATED,
        "created_at": now(),
        "process": owner,
    }
    store.save(task)
    worktree.parent.mkdir(parents=True, exist_ok=True)
    try:
        git(repository, "-c", "core.hooksPath=/dev/null", "worktree", "add", "-b", branch, str(worktree), base)
        git(repository, "worktree", "lock", "--reason", f"agent-task:{task_id}", str(worktree))
        stage_memory(task, memory)
        store.save(task)
    except Exception as error:
        set_status(store, task, FAILED, str(error))
        raise
    return task


def recreate_worktree(store: Store, task: dict[str, Any]) -> None:
    path = managed_worktree_path(store, task)
    if path.exists():
        return
    repository = Path(task["repository"])
    branch = task["branch"]
    if not branch_exists(repository, branch):
        start = task.get("result_commit") or task["base_sha"]
        git(repository, "branch", branch, start)
    path.parent.mkdir(parents=True, exist_ok=True)
    git(repository, "-c", "core.hooksPath=/dev/null", "worktree", "add", str(path), branch)
    git(repository, "worktree", "lock", "--reason", f"agent-task:{task['task_id']}", str(path))
    if task.get("memory_path"):
        update = task.pop("memory_update", None)
        if isinstance(update, dict):
            base = validate_memory(update["base"])
            proposed = validate_memory(update["proposed"])
            write_memory(path / MEMORY_NAME, proposed)
            task["memory_base"] = base
            task["memory_pending"] = True
        else:
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
    repository = Path(task["repository"])
    head = ref(path, "HEAD")
    target = task.get("target_branch")
    excluded = (
        ref(repository, f"refs/heads/{target}")
        if isinstance(target, str) and branch_exists(repository, target)
        else task["base_sha"]
    )
    findings = forbidden_history(repository, head, excluded)
    if findings:
        paths = sorted({name for finding in findings for name in finding["paths"]})
        notes.append(
            "Rewrite the task's unpublished commits so these machine-local paths never appear in history: "
            f"{', '.join(paths)}. A later deletion commit is not sufficient."
        )
    if task.get("interrupted_at"):
        notes.append("Resume the interrupted session and continue from its preserved files and commits.")
        return " ".join(notes)
    normal, _ignored = worktree_changes(path)
    if normal or not task.get("target_branch"):
        notes.append("Resume the preserved files and commit the completed result.")
        return " ".join(notes)
    if not branch_exists(repository, task["target_branch"]):
        notes.append(f"The target branch {task['target_branch']} no longer exists; repair the task metadata first.")
        return " ".join(notes)
    if git(path, "rev-parse", "--verify", "MERGE_HEAD", check=False).returncode == 0:
        notes.append("A target merge is already in progress. Resolve only those conflicts and commit.")
        return " ".join(notes)
    target_sha = ref(repository, f"refs/heads/{task['target_branch']}")
    if is_ancestor(repository, target_sha, head):
        notes.append("The task already contains the current target; finish and commit the result.")
        return " ".join(notes)
    merge = git(path, "-c", "core.hooksPath=/dev/null", "merge", "--no-ff", "--no-commit", target_sha, check=False)
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
        worktree = managed_worktree_path(store, task)
        launch_error: BaseException | None = None
        handoff_task_ids: list[str] = []
        session_id: str | None = None
        with checkout_session_lock(
            store,
            worktree,
            record_session_base=True,
            agent=str(task.get("agent") or "custom"),
            task_id=task["task_id"],
            working_directory=task_working_directory(task),
        ) as checkout_reservation:
            if not checkout_reservation:
                raise AgentTaskError(f"worktree already has an active agent: {worktree}")
            try:
                if isinstance(checkout_reservation, CheckoutReservation):
                    session_id = checkout_reservation.session_id
                inherited = tuple(checkout_reservation) if isinstance(checkout_reservation, CheckoutReservation) else ()
                exit_code = launch_agent(
                    store,
                    task,
                    command,
                    pass_fds=inherited,
                    checkout_reservation=(
                        checkout_reservation
                        if isinstance(checkout_reservation, CheckoutReservation)
                        else None
                    ),
                )
                if isinstance(checkout_reservation, CheckoutReservation):
                    handoff_task_ids = checkout_reservation.capture_handoff_tasks()
                    checkout_reservation.release()
            except BaseException as error:
                launch_error = error
        if launch_error is not None:
            if process_alive(task.get("process")):
                set_status(store, task, RUNNING, "launcher ended while the coding agent was still active")
            else:
                task.pop("process", None)
                set_status(store, task, FAILED, f"agent launch failed: {launch_error}")
                cleanup_task(store, task)
            raise launch_error
        if exit_code == HANDOFF_EXIT_CODE and handoff_task_ids:
            record_agent_exit(task, 0)
            task["handoff_completed_at"] = now()
            store.save(task)
            exit_code = 0
        finalize_task(store, task, integrate=integrate)
        if session_id is not None:
            attachment_results = finalize_session_attachments(
                store,
                session_id,
                int(task.get("agent_exit_code", exit_code)),
                graceful=task.get("agent_exit_graceful") is True,
            )
            if attachment_results:
                task["attachments"] = [result["task_id"] for result in attachment_results]
                failures = [
                    result
                    for result in attachment_results
                    if result["status"] not in (INTEGRATED, COMPLETED)
                    and not (result["status"] == READY and not result["auto_integrate"])
                ]
                if failures:
                    task["attachment_failures"] = failures
                else:
                    task.pop("attachment_failures", None)
                store.save(task)
        if handoff_task_ids:
            retry_handoff_integrations(store, handoff_task_ids)
        retry_ready_integrations_for_repository(
            store,
            Path(task["repository"]),
            exclude_task_ids=(task["task_id"],),
        )
        return 0 if task.get("agent_exit_graceful") is True else exit_code


def command_start(args: argparse.Namespace, store: Store) -> int:
    if not hasattr(args, "launch_cwd"):
        prepare_launch_working_directory(args)
    explicit = list(args.command)
    if args.agent == "custom" and not explicit:
        raise AgentTaskError("custom agents require a command after --")
    command = explicit or default_agent_command(args.agent, args.description)
    validate_foreground_agent_command(args.agent, command, lock_managed=True)
    checkout = repo_root(Path(args.launch_cwd).resolve())
    repository = primary_worktree(checkout)
    with repository_activity_lock(store, repository, exclusive=False, blocking=True) as repository_available:
        if not repository_available:
            raise AgentTaskError("repository is unavailable for task creation")
        task = create_task(store, args)
    print(f"task: {task['task_id']}\nworktree: {task['worktree_path']}\nbranch: {task['branch']}")
    exit_code = launch_for_task(store, task, command, integrate=bool(task.get("auto_integrate", True)))
    print(f"status: {task['status']}")
    if task.get("result_commit"):
        print(f"result: {task['result_commit']}")
    if task.get("integrated_commit"):
        print(f"integrated: {task['integrated_commit']} -> {task['target_branch']}")
    if task.get("attachment_failures"):
        return 2
    if task["status"] == COMPLETED:
        return 0
    if task["status"] == READY and not task.get("auto_integrate", True):
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


def overlay_json(current: Any, local: Any) -> Any:
    if isinstance(current, dict) and isinstance(local, dict):
        result = {key: json.loads(json.dumps(value)) for key, value in current.items()}
        for key, value in local.items():
            result[key] = overlay_json(result[key], value) if key in result else json.loads(json.dumps(value))
        return result
    return json.loads(json.dumps(local))


def prepare_native_repository_memory(store: Store, repository: Path, checkout: Path) -> dict[str, Any]:
    current_branch = git(checkout, "branch", "--show-current").stdout.strip()
    canonical_path, canonical = ensure_memory(store, repository, current_branch)
    local_path = checkout / MEMORY_NAME
    secondary = checkout.resolve() != canonical_path.parent.resolve()
    if secondary:
        if os.path.lexists(local_path):
            local = read_memory(local_path)
            synchronized = validate_memory(overlay_json(canonical, local))
            synchronized["settings"]["integration_target"] = canonical["settings"].get("integration_target")
        else:
            synchronized = canonical
        write_memory(local_path, synchronized)
    return {
        "base": canonical,
        "canonical_path": str(canonical_path),
        "local_path": str(local_path),
        "secondary": secondary,
    }


def finalize_native_repository_memory(store: Store, session: dict[str, Any]) -> None:
    if not session.get("secondary"):
        canonical_path = Path(session["canonical_path"])
        try:
            read_memory(canonical_path)
        except AgentTaskError as error:
            print(f"agent-task: native {MEMORY_NAME} is invalid and was left in place: {error}", file=sys.stderr)
        return
    local_path = Path(session["local_path"])
    canonical_path = Path(session["canonical_path"])
    try:
        proposed = read_memory(local_path)
        base = validate_memory(session["base"])
        with store.lock(f"memory:{common_dir(local_path.parent)}"):
            current = read_memory(canonical_path)
            overwrites: list[str] = []
            merged = validate_memory(merge_memory(base, current, proposed, "", overwrites))
            write_memory(canonical_path, merged)
            write_memory(local_path, merged)
        if overwrites:
            print(
                f"agent-task: native {MEMORY_NAME} merge overwrote concurrent fields: {', '.join(overwrites)}",
                file=sys.stderr,
            )
    except AgentTaskError as error:
        print(f"agent-task: native {MEMORY_NAME} update preserved in {local_path}: {error}", file=sys.stderr)


def launch_native_with_memory(
    args: argparse.Namespace,
    store: Store,
    repository: Path,
    checkout: Path,
    *,
    pass_fds: Sequence[int] = (),
    checkout_reservation: CheckoutReservation | None = None,
) -> int:
    session = prepare_native_repository_memory(store, repository, checkout)
    try:
        return launch_native_agent(
            args,
            pass_fds=pass_fds,
            checkout_reservation=checkout_reservation,
        )
    finally:
        if isinstance(session, dict):
            finalize_native_repository_memory(store, session)


def command_open(args: argparse.Namespace, store: Store) -> int:
    prepare_launch_working_directory(args)
    if bool(getattr(args, "local", False)):
        if args.auto or args.managed or args.new or getattr(args, "require_current", False):
            raise AgentTaskError("--local cannot be combined with managed checkout modes")
        return launch_native_agent(args)
    if codex_subcommand(args.command) == "review":
        args.require_current = True
    validate_foreground_agent_command(
        args.agent,
        list(args.command) or default_agent_command(args.agent, args.description),
        lock_managed=True,
    )
    if args.new:
        args.auto = False
        args.managed = True
    if getattr(args, "require_current", False):
        if args.managed or args.new:
            raise AgentTaskError("--require-current cannot create a managed worktree")
        args.auto = True
    if not args.auto and not args.managed and not args.new:
        args.auto = True
    checkout = repo_root(Path(args.launch_cwd).resolve())
    repository = primary_worktree(checkout)
    if args.auto:
        native_exit_code: int | None = None
        handoff_task_ids: list[str] = []
        with checkout_session_lock(
            store,
            checkout,
            record_session_base=True,
            agent=args.agent,
            working_directory=Path(args.launch_cwd),
        ) as checkout_reservation:
            if checkout_reservation:
                inherited = tuple(checkout_reservation) if isinstance(checkout_reservation, CheckoutReservation) else ()
                native_exit_code = launch_native_with_memory(
                    args,
                    store,
                    repository,
                    checkout,
                    pass_fds=inherited,
                    checkout_reservation=(
                        checkout_reservation
                        if isinstance(checkout_reservation, CheckoutReservation)
                        else None
                    ),
                )
                if isinstance(checkout_reservation, CheckoutReservation):
                    handoff_task_ids = checkout_reservation.capture_handoff_tasks()
                    checkout_reservation.release()
        if native_exit_code is not None:
            if native_exit_code == HANDOFF_EXIT_CODE and handoff_task_ids:
                handoff_success = retry_handoff_integrations(store, handoff_task_ids)
                retry_ready_integrations_for_repository(store, repository)
                return 0 if handoff_success else 2
            retry_ready_integrations_for_repository(store, repository)
            return native_exit_code
        if getattr(args, "require_current", False):
            raise AgentTaskError(
                f"current checkout is busy; refusing to run this command against a different snapshot: {checkout}"
            )
        active_session = read_active_checkout_session(store, checkout)
        args.isolate_from_active_checkout = True
        args.active_session_base_sha = active_session.get("base_sha") if active_session else None
        args.active_session_source_branch = active_session.get("source_branch") if active_session else None
        args.active_session_recorded_at = active_session.get("recorded_at") if active_session else None
        print(f"checkout already has an active agent: {checkout}\nstarting an isolated worktree")
        args.new = True
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
            print(
                f"{args.agent} task {task['task_id']} is already running in {task['worktree_path']}\n"
                "starting a separate managed worktree"
            )
            args.new = True
        if not args.new:
            recoverable = [
                task for task in tasks if task.get("agent") == args.agent and task.get("status") == RECOVERY
            ]
            if recoverable:
                selected = choose_recovery_task(recoverable)
                if selected:
                    print(f"resuming: {selected['task_id']}\nworktree: {selected['worktree_path']}")
                    recovery_args = argparse.Namespace(
                        task_id=selected["task_id"],
                        agent=args.agent,
                        integration_policy=False if args.no_integrate else None,
                        new_session=args.new_session,
                        prompt=args.description,
                        command=list(args.command),
                    )
                    return command_recover(recovery_args, store)
    return command_start(args, store)


def command_resume(args: argparse.Namespace, store: Store) -> int:
    passthrough = list(getattr(args, "command", []))
    if passthrough and (args.session_id or args.last or args.all or args.include_non_interactive):
        raise AgentTaskError("pass Codex resume options either before or after --, not both")
    saved_chat_requested = bool(
        passthrough or args.session_id or args.last or args.all or args.include_non_interactive
    )
    args.description = "resume a saved Codex session"
    args.task = args.description
    args.command = (
        passthrough_chat_resume_command(passthrough)
        if passthrough
        else default_chat_resume_command(
            args.agent,
            args.session_id,
            last=args.last,
            include_non_interactive=args.include_non_interactive,
        )
    )
    prepare_launch_working_directory(args)
    checkout = repo_root(Path(args.launch_cwd).resolve())
    repository = primary_worktree(checkout)
    tasks = refresh_interrupted_tasks(store, repository)

    if not saved_chat_requested:
        recoverable = [
            task for task in tasks if task.get("agent") == args.agent and task.get("status") == RECOVERY
        ]
        if recoverable:
            selected = choose_recovery_task(recoverable)
            if selected:
                print(f"resuming task: {selected['task_id']}\nworktree: {selected['worktree_path']}")
                recovery_args = argparse.Namespace(
                    task_id=selected["task_id"],
                    agent=args.agent,
                    integration_policy=False if args.no_integrate else None,
                    new_session=False,
                    prompt=None,
                    command=[],
                )
                return command_recover(recovery_args, store)

    print(f"resuming in a fresh managed worktree from: {checkout}")
    return command_start(args, store)


def command_list(_args: argparse.Namespace, store: Store) -> int:
    tasks = sorted(store.all(), key=lambda item: item.get("created_at", ""), reverse=True)
    if not tasks:
        print("No agent tasks.")
        return 0
    print(f"{'TASK':31} {'STATUS':21} {'AGENT':8} {'TARGET':16} {'RESULT':10} NOTE")
    for task in tasks:
        notes: list[str] = []
        if not task.get("auto_integrate", True) and task.get("status") == READY:
            notes.append("manual-integration")
        if task.get("memory_warning") or task.get("memory_overwrites") or task.get("memory_update"):
            notes.append("memory")
        note = ",".join(notes) or "-"
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


def clear_interrupted_integration(store: Store, task: dict[str, Any]) -> None:
    terminate_owned_process(task.get("validation_process"))
    candidate_value = task.get("integration_candidate")
    if candidate_value:
        candidate = Path(str(candidate_value)).resolve()
        integrations_root = store.integrations.resolve()
        if candidate.is_relative_to(integrations_root):
            if remove_integration_worktree(Path(task["repository"]), candidate):
                task.pop("integration_cleanup_warning", None)
            else:
                task["integration_cleanup_warning"] = f"integration worktree cleanup failed: {candidate}"
        else:
            task["integration_cleanup_warning"] = f"refused unexpected integration path: {candidate}"
    task.pop("validation_process", None)
    task.pop("integration_process", None)
    task.pop("integration_candidate", None)
    store.save(task)


def recognize_result_already_on_target(store: Store, task: dict[str, Any]) -> bool:
    repository_value = task.get("repository")
    target = task.get("target_branch")
    result_commit = task.get("result_commit")
    if not all(isinstance(value, str) and value for value in (repository_value, target, result_commit)):
        return False
    repository = Path(repository_value)
    if not branch_exists(repository, target):
        return False
    target_sha = ref(repository, f"refs/heads/{target}")
    if not is_ancestor(repository, result_commit, target_sha):
        return False
    task["integrated_commit"] = target_sha
    task.pop("legacy_integration_interrupted", None)
    set_status(store, task, INTEGRATED, "recorded result is already present on target")
    resolve_task_notices(store, task["task_id"])
    apply_memory_update(store, task)
    cleanup_task(store, task)
    return True


def recover_interrupted_integration(
    store: Store,
    task: dict[str, Any],
    *,
    integrate: bool,
    allow_legacy_retry: bool = False,
) -> None:
    owner = task.get("integration_process")
    legacy_owner = not isinstance(owner, dict) or owner.get("role") != "integration"
    if process_alive(task.get("integration_process")):
        return
    clear_interrupted_integration(store, task)
    if recognize_result_already_on_target(store, task):
        return
    if legacy_owner and not allow_legacy_retry:
        task["legacy_integration_interrupted"] = True
        set_status(
            store,
            task,
            RECOVERY,
            "legacy interrupted integration has no owner metadata; explicit operator review required",
        )
        return
    repository = Path(task["repository"])
    target = task.get("target_branch")
    result_commit = task.get("result_commit")
    if target and result_commit and branch_exists(repository, target):
        target_sha = ref(repository, f"refs/heads/{target}")
        set_status(store, task, READY, "interrupted integration reset and queued")
        if integrate:
            integrate_task(store, task)
        return
    set_status(store, task, RECOVERY, "interrupted integration metadata is incomplete")


def command_integrate(args: argparse.Namespace, store: Store) -> int:
    with store.lock(f"task:{args.task_id}", blocking=False):
        task = store.load(args.task_id)
        task["auto_integrate"] = True
        store.save(task)
        if process_alive(task.get("process")):
            raise AgentTaskError("coding agent is still running")
        if task.get("status") == RECOVERY and task.pop("legacy_integration_interrupted", False):
            set_status(store, task, READY, "operator approved retry of legacy interrupted integration")
        if task.get("status") in (INTEGRATING, VALIDATING):
            if process_alive(task.get("integration_process")):
                raise AgentTaskError("integration is still running")
            recover_interrupted_integration(store, task, integrate=False, allow_legacy_retry=True)
        if not task.get("result_commit"):
            inspect_result(store, task, trust_clean_commit=True)
        if task.get("status") == INTEGRATED:
            resolve_task_notices(store, task["task_id"])
            success = True
        else:
            success = task.get("status") == READY and integrate_task(store, task)
    print(f"{task['task_id']}: {task['status']}")
    return 0 if success else 2


def retry_handoff_integrations(store: Store, task_ids: Sequence[str]) -> bool:
    success = True
    for task_id in dict.fromkeys(task_ids):
        try:
            result = command_integrate(argparse.Namespace(task_id=task_id), store)
        except (AgentTaskError, LockBusy) as error:
            print(f"agent-task: handoff integration for {task_id} remains queued: {error}", file=sys.stderr)
            success = False
        else:
            success = result == 0 and success
    return success


def retry_ready_integrations_for_repository(
    store: Store,
    repository: Path,
    *,
    exclude_task_ids: Sequence[str] = (),
) -> bool:
    excluded = set(exclude_task_ids)
    repository_common_dir = common_dir(repository)
    ready = [
        task["task_id"]
        for task in sorted(store.all(), key=lambda item: item.get("created_at", ""))
        if task.get("task_id") not in excluded
        and task_belongs_to_repository(task, repository_common_dir)
        and task.get("status") == READY
        and bool(task.get("auto_integrate", True))
        and not process_alive(task.get("process"))
    ]
    return retry_handoff_integrations(store, ready)


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
        policy = getattr(args, "integration_policy", None)
        if policy is None and bool(getattr(args, "no_integrate", False)):
            policy = False
        if policy is not None:
            task["auto_integrate"] = policy
        else:
            task.setdefault("auto_integrate", True)
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
        exit_code = launch_for_task(
            store,
            task,
            command,
            integrate=bool(task.get("auto_integrate", True)),
            task_locked=True,
        )
    print(f"{task['task_id']}: {task['status']}")
    return (
        0
        if task.get("integrated_commit")
        or task.get("status") == COMPLETED
        or (not task.get("auto_integrate", True) and task["status"] == READY)
        else (exit_code or 2)
    )


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
    if process_alive(task.get("process")) or process_alive(task.get("integration_process")):
        return
    status = task.get("status")
    if task.get("integration_candidate") and status not in (INTEGRATING, VALIDATING):
        clear_interrupted_integration(store, task)
    if status == RUNNING:
        if task.get("attachment_session_id"):
            task.pop("process", None)
            task["attachment_reconciled_at"] = now()
            record_agent_exit(task, 0)
            store.save(task)
            finalize_task(
                store,
                task,
                integrate=integrate and bool(task.get("auto_integrate", True)),
                trust_clean_commit=True,
            )
        else:
            preserve_interrupted_task(store, task)
    elif status == CREATED:
        preserve_interrupted_task(store, task)
    elif status in (INTEGRATING, VALIDATING):
        recover_interrupted_integration(store, task, integrate=integrate and bool(task.get("auto_integrate", True)))
    elif status == READY and integrate and bool(task.get("auto_integrate", True)):
        if task.get("integration_candidate"):
            clear_interrupted_integration(store, task)
        integrate_task(store, task)
    elif status == RECOVERY and task.get("result_commit"):
        recognize_result_already_on_target(store, task)
    elif status in (INTEGRATED, COMPLETED, FAILED):
        if task.get("integration_candidate"):
            clear_interrupted_integration(store, task)
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


def current_agent_session(store: Store, session_id: str | None = None) -> tuple[str, Path, dict[str, Any]]:
    selected = session_id or os.environ.get(AGENT_SESSION_ID_ENV)
    if not selected:
        raise AgentTaskError("this command must run inside a managed agent session, or use --session")
    validate_identifier(selected, "session id")
    configured_path = os.environ.get(AGENT_SESSION_PATH_ENV) if session_id is None else None
    if configured_path:
        path = Path(configured_path).resolve()
    else:
        matches: list[Path] = []
        for candidate in store.sessions.glob("*.json"):
            try:
                value = read_json_file_safely(candidate)
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(value, dict) and value.get("session_id") == selected:
                matches.append(candidate.resolve())
        if len(matches) != 1:
            raise AgentTaskError(f"cannot find one active session record for {selected}")
        path = matches[0]
    if path.parent != store.sessions.resolve():
        raise AgentTaskError(f"refused session metadata outside the state directory: {path}")
    try:
        value = read_json_file_safely(path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise AgentTaskError(f"cannot read current session metadata: {error}") from error
    if not isinstance(value, dict) or value.get("session_id") != selected:
        raise AgentTaskError("current session metadata no longer matches this process")
    return selected, path, value


def attachment_tasks(store: Store, session_id: str) -> list[dict[str, Any]]:
    return sorted(
        [task for task in store.all() if task.get("attachment_session_id") == session_id],
        key=lambda task: task.get("created_at", ""),
    )


def finalize_session_attachments(
    store: Store,
    session_id: str,
    agent_exit_code: int,
    *,
    graceful: bool = False,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for snapshot in attachment_tasks(store, session_id):
        try:
            with store.lock(f"task:{snapshot['task_id']}", blocking=False):
                task = store.load(snapshot["task_id"])
                if task.get("status") in (CREATED, RUNNING):
                    task.pop("process", None)
                    record_agent_exit(task, agent_exit_code, graceful=graceful)
                    task["attachment_finished_at"] = now()
                    store.save(task)
                    finalize_task(
                        store,
                        task,
                        integrate=bool(task.get("auto_integrate", True)),
                    )
                results.append(
                    {
                        "task_id": task["task_id"],
                        "status": task.get("status"),
                        "auto_integrate": bool(task.get("auto_integrate", True)),
                    }
                )
                print(f"attachment {task['task_id']}: {task.get('status')}")
        except LockBusy:
            results.append(
                {
                    "task_id": snapshot["task_id"],
                    "status": snapshot.get("status"),
                    "auto_integrate": bool(snapshot.get("auto_integrate", True)),
                    "reason": "attachment lifecycle is busy",
                }
            )
    return results


def command_attach(args: argparse.Namespace, store: Store) -> int:
    session_id, _session_path, session = current_agent_session(store)
    parent_task_id = session.get("task_id")
    if not isinstance(parent_task_id, str):
        raise AgentTaskError("secondary repositories can only attach to a managed task")
    parent = store.load(parent_task_id)
    owner = session.get("process")
    parent_owner = parent.get("process")
    if (
        not isinstance(owner, dict)
        or owner.get("role") != "lock-supervisor"
        or not process_alive(owner)
        or not isinstance(parent_owner, dict)
        or parent_owner.get("pid") != owner.get("pid")
        or parent_owner.get("start") != owner.get("start")
    ):
        raise AgentTaskError("managed task supervisor is no longer active")

    requested = Path(args.path).expanduser().resolve()
    if not requested.is_dir():
        raise AgentTaskError(f"secondary repository path does not exist: {requested}")
    checkout = repo_root(requested)
    repository = primary_worktree(checkout)
    repository_common_dir = common_dir(repository)
    if repository_common_dir == Path(parent["git_common_dir"]).resolve():
        raise AgentTaskError("the requested path belongs to the task's existing repository")

    lock_name = f"attachment:{session_id}:{repository_common_dir}"
    with store.lock(lock_name):
        for existing in attachment_tasks(store, session_id):
            recorded_common_dir = existing.get("git_common_dir")
            recorded_worktree = existing.get("worktree_path")
            if (
                isinstance(recorded_common_dir, str)
                and Path(recorded_common_dir).resolve() == repository_common_dir
                and existing.get("status") in (CREATED, RUNNING)
                and isinstance(recorded_worktree, str)
                and Path(recorded_worktree).is_dir()
            ):
                print(
                    f"task: {existing['task_id']}\n"
                    f"worktree: {existing['worktree_path']}\n"
                    f"branch: {existing['branch']}"
                )
                return 0

        attach_args = argparse.Namespace(
            launch_cwd=requested,
            agent=str(parent.get("agent") or session.get("agent") or "codex"),
            target=None,
            check=[],
            check_timeout=DEFAULT_CHECK_TIMEOUT_SECONDS,
            no_integrate=not bool(parent.get("auto_integrate", True)),
            task=f"secondary repository attached to {parent_task_id}",
            description=f"secondary repository attached to {parent_task_id}",
            isolate_from_active_checkout=False,
        )
        with repository_activity_lock(store, repository, exclusive=False, blocking=True) as available:
            if not available:
                raise AgentTaskError(f"secondary repository is unavailable: {repository}")
            task = create_task(store, attach_args)
        task["attachment_session_id"] = session_id
        task["attachment_parent_task_id"] = parent_task_id
        task["attachment_source_path"] = str(requested)
        task["process"] = dict(owner)
        set_status(store, task, RUNNING)

    print(f"task: {task['task_id']}\nworktree: {task['worktree_path']}\nbranch: {task['branch']}")
    return 0


def command_inbox(args: argparse.Namespace, store: Store) -> int:
    session_id, _path, _session = current_agent_session(store, getattr(args, "session", None))
    with store.lock(f"inbox:{session_id}"):
        inbox = read_session_inbox(store, session_id)
    event_id = getattr(args, "event_id", None)
    messages = inbox["messages"]
    if event_id:
        messages = [message for message in messages if message.get("id") == event_id]
        if not messages:
            raise AgentTaskError(f"unknown inbox event: {event_id}")
    else:
        messages = [message for message in messages if message.get("status") != "resolved"]
    if getattr(args, "json", False):
        print(json.dumps({"session_id": session_id, "messages": messages}, indent=2, sort_keys=True))
        return 0
    if not messages:
        print(f"{session_id}: inbox empty")
        return 0
    for message in messages:
        print(f"{message['id']}: {message['status']} ({message.get('type', 'message')})")
        print(f"  {message['prompt']}")
    return 0


def command_handoff(args: argparse.Namespace, store: Store) -> int:
    session_id, _path, session = current_agent_session(store)
    if session.get("notification_protocol") != NOTIFICATION_PROTOCOL:
        raise AgentTaskError("this session predates the handoff protocol; restart it with o or c")
    event_id = validate_identifier(args.event_id, "inbox event id")
    pending = pending_inbox_messages(store, session_id, include_delivered=True)
    message = next((item for item in pending if item.get("id") == event_id), None)
    if message is None:
        raise AgentTaskError(f"inbox event is not pending: {event_id}")
    if message.get("type") != "integration_ready" or not isinstance(message.get("task_id"), str):
        raise AgentTaskError(f"inbox event cannot trigger a repository handoff: {event_id}")
    owner = session.get("process")
    if (
        not isinstance(owner, dict)
        or owner.get("role") != "lock-supervisor"
        or session.get("notification_state") != "ready"
        or not process_alive(owner)
    ):
        raise AgentTaskError("session supervisor is no longer active")
    update_inbox_event(store, session_id, event_id, "accepted", detail="agent-command")
    try:
        os.kill(int(owner["pid"]), signal.SIGUSR2)
    except OSError as error:
        raise AgentTaskError(f"cannot notify the session supervisor: {error}") from error
    print(
        f"handoff accepted: {event_id}\n"
        "agent-task will close this foreground session and retry integration after its lease is released."
    )
    return 0


def command_inbox_hook() -> int:
    session_id = os.environ.get(AGENT_SESSION_ID_ENV)
    if not session_id:
        return 0
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            return 0
        payload = json.loads(raw or b"{}")
        event_name = payload.get("hook_event_name") if isinstance(payload, dict) else None
        if event_name not in ("Stop", "UserPromptSubmit"):
            return 0
        store = Store()
        pending = pending_inbox_messages(store, session_id)
        if not pending:
            return 0
        prompt = "\n\n".join(message["prompt"] for message in pending)
        if event_name == "Stop":
            output = {"decision": "block", "reason": prompt}
        else:
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": prompt,
                }
            }
        print(json.dumps(output))
        sys.stdout.flush()
        for message in pending:
            update_inbox_event(store, session_id, message["id"], "delivered", detail=f"claude-{event_name}")
    except (AgentTaskError, OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        print(f"agent-task inbox hook: {error}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-task", description="Run coding agents in disposable Git worktrees.")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    opening = subparsers.add_parser("open", help="launch natively, or isolate automatically when the checkout is busy")
    opening.add_argument("description", nargs="?")
    opening.add_argument("--task", help="task description for a custom command")
    opening.add_argument("--agent", choices=("codex", "claude", "custom"), default="codex")
    opening.add_argument("--target", help="local integration target branch")
    opening.add_argument("--check", action="append", default=[], help="post-merge check; repeatable")
    opening.add_argument(
        "--check-timeout",
        type=positive_seconds,
        default=DEFAULT_CHECK_TIMEOUT_SECONDS,
        help="per-check timeout in seconds (default: 3600)",
    )
    opening.add_argument("--no-integrate", action="store_true")
    opening.add_argument("--auto", action="store_true", help="use this checkout when free, otherwise create a worktree")
    opening.add_argument("--managed", action="store_true", help="resume or create a managed worktree task")
    opening.add_argument("--new", action="store_true", help="start separately even when interrupted work exists")
    opening.add_argument("--local", action="store_true", help="bypass checkout locking explicitly")
    opening.add_argument(
        "--require-current",
        action="store_true",
        help="fail if the current checkout is busy instead of using another snapshot",
    )
    opening.add_argument("--new-session", action="store_true", help="recover files in a fresh agent conversation")
    opening.set_defaults(func=command_open)

    resuming = subparsers.add_parser(
        "resume",
        help="resume preserved work or attach a saved Codex chat to a managed worktree",
    )
    resuming.add_argument("session_id", nargs="?", help="Codex session id or name")
    resuming.add_argument("--agent", choices=("codex",), default="codex")
    resuming.add_argument("--last", action="store_true", help="resume the latest saved chat across all directories")
    resuming.add_argument("--all", action="store_true", help="accepted for parity; the picker always searches all directories")
    resuming.add_argument("--include-non-interactive", action="store_true")
    resuming.add_argument("--target", help="local integration target branch")
    resuming.add_argument("--check", action="append", default=[], help="post-merge check; repeatable")
    resuming.add_argument(
        "--check-timeout",
        type=positive_seconds,
        default=DEFAULT_CHECK_TIMEOUT_SECONDS,
        help="per-check timeout in seconds (default: 3600)",
    )
    resuming.add_argument("--no-integrate", action="store_true")
    resuming.set_defaults(func=command_resume)

    start = subparsers.add_parser("start", help="create a worktree and launch an agent")
    start.add_argument("description", nargs="?")
    start.add_argument("--task", help="task description for a custom command")
    start.add_argument("--agent", choices=("codex", "claude", "custom"), default="codex")
    start.add_argument("--target", help="local integration target branch")
    start.add_argument("--check", action="append", default=[], help="post-merge check; repeatable")
    start.add_argument(
        "--check-timeout",
        type=positive_seconds,
        default=DEFAULT_CHECK_TIMEOUT_SECONDS,
        help="per-check timeout in seconds (default: 3600)",
    )
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
    inbox = subparsers.add_parser("inbox", help="show durable events for the current agent session")
    inbox.add_argument("event_id", nargs="?")
    inbox.add_argument("--session", help="inspect a specific active session")
    inbox.add_argument("--json", action="store_true")
    inbox.set_defaults(func=command_inbox)
    handoff = subparsers.add_parser("handoff", help="release this session and retry a queued integration")
    handoff.add_argument("event_id")
    handoff.set_defaults(func=command_handoff)
    attach = subparsers.add_parser("attach", help="attach a secondary repository to the current managed task")
    attach.add_argument("path")
    attach.set_defaults(func=command_attach)
    recover = subparsers.add_parser("recover", help="resume a preserved task")
    recover.add_argument("task_id")
    recover.add_argument("--agent", choices=("codex", "claude", "custom"))
    recover_policy = recover.add_mutually_exclusive_group()
    recover_policy.add_argument("--integrate", dest="integration_policy", action="store_true")
    recover_policy.add_argument("--no-integrate", dest="integration_policy", action="store_false")
    recover.set_defaults(integration_policy=None)
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
    if raw and raw[0] == LOCK_EXEC_SUBCOMMAND:
        return command_lock_exec(raw[1:])
    if raw and raw[0] == INBOX_HOOK_SUBCOMMAND:
        return command_inbox_hook()
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
        return cli_main()
    except AgentTaskError as error:
        print(f"agent-task: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("agent-task: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

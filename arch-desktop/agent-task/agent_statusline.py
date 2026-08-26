#!/usr/bin/env python3
"""Fast, read-only active-worktree status renderer for agent UIs."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
from typing import Any, Sequence


ACTIVE_STATUSES = {"CREATED", "RUNNING"}
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_INPUT_BYTES = 1024 * 1024
TASK_CONTEXT_SCHEMA = 1
JIRA_ISSUE_PATTERN = re.compile(r"(?<![A-Z0-9])([A-Z][A-Z0-9_]{1,31}-[1-9][0-9]*)(?![A-Z0-9])")


def read_regular_json(path: Path) -> Any:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or info.st_size > MAX_FILE_BYTES
        ):
            raise OSError("unsafe status input")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise OSError("status input is too large")
            chunks.append(chunk)
        return json.loads(b"".join(chunks))
    finally:
        os.close(descriptor)


def owned_directory(path: Path) -> bool:
    try:
        info = path.stat(follow_symlinks=False)
    except OSError:
        return False
    return stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()


def process_start(pid: int) -> str | None:
    try:
        value = Path(f"/proc/{pid}/stat").read_text()
        return value[value.rfind(")") + 2 :].split()[19]
    except (OSError, IndexError):
        return None


def process_alive(process: Any) -> bool:
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


def compact_ascii(value: Any, *, fallback: str, limit: int = 48) -> str:
    text = "".join(
        character if 32 <= ord(character) < 127 else "?"
        for character in " ".join(str(value or "").split())
    )
    return (text or fallback)[:limit]


def jira_issue_from_task_text(task: dict[str, Any]) -> str | None:
    for field in ("description", "source_branch"):
        value = task.get(field)
        if isinstance(value, str) and (match := JIRA_ISSUE_PATTERN.search(value)):
            return match.group(1)
    return None


def task_context(contexts: Path, task_id: str) -> dict[str, Any]:
    path = contexts / f"{task_id}.json"
    if not os.path.lexists(path):
        return {}
    try:
        value = read_regular_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != TASK_CONTEXT_SCHEMA
        or value.get("task_id") != task_id
    ):
        return {}
    issue = value.get("jira_issue")
    if not isinstance(issue, str) or re.fullmatch(r"[A-Z][A-Z0-9_]{1,31}-[1-9][0-9]*", issue) is None:
        value.pop("jira_issue", None)
    return value


def active_worktree_tasks(state: Path) -> list[dict[str, Any]]:
    tasks = state / "tasks"
    contexts = state / "contexts"
    if not owned_directory(tasks) or (contexts.exists() and not owned_directory(contexts)):
        return []
    result: list[dict[str, Any]] = []
    for path in tasks.glob("*.json"):
        try:
            task = read_regular_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            continue
        if not (
            isinstance(task, dict)
            and task.get("task_id") == path.stem
            and task.get("status") in ACTIVE_STATUSES
            and isinstance(task.get("worktree_path"), str)
            and bool(task["worktree_path"])
            and process_alive(task.get("process"))
        ):
            continue
        item = dict(task)
        context = task_context(contexts, path.stem) if contexts.is_dir() else {}
        issue = context.get("jira_issue") or jira_issue_from_task_text(item)
        if isinstance(issue, str):
            item["statusline_jira_issue"] = issue
        result.append(item)
    return result


def task_for_working_directory(tasks: Sequence[dict[str, Any]], current_directory: str | None) -> str | None:
    if not current_directory:
        return None
    try:
        current = Path(current_directory).expanduser().resolve()
    except (OSError, RuntimeError):
        return None
    matches: list[tuple[int, str]] = []
    for task in tasks:
        task_id = task.get("task_id")
        worktree_value = task.get("worktree_path")
        if not isinstance(task_id, str) or not isinstance(worktree_value, str):
            continue
        try:
            worktree = Path(worktree_value).expanduser().resolve()
        except (OSError, RuntimeError):
            continue
        if current == worktree or current.is_relative_to(worktree):
            matches.append((len(worktree.parts), task_id))
    return max(matches, default=(0, ""))[1] or None


def task_label(task: dict[str, Any], *, current: bool) -> str:
    repository = compact_ascii(Path(str(task.get("repository") or "repository")).name, fallback="repo", limit=28)
    agent = compact_ascii(task.get("agent"), fallback="agent", limit=8)
    task_id = str(task.get("task_id") or "")
    match = re.fullmatch(r"\d{8}-(\d{2})(\d{2})\d{2}-[A-Za-z0-9]+", task_id)
    stamp = f"@{match.group(1)}:{match.group(2)}" if match else ""
    attachment = "+" if task.get("attachment_parent_task_id") else ""
    issue_value = task.get("statusline_jira_issue")
    issue = f"[{compact_ascii(issue_value, fallback='Jira', limit=40)}]" if issue_value else ""
    marker = "*" if current else ""
    return f"{marker}{agent}/{repository}{stamp}{attachment}{issue}"


def claude_worktree_label(payload: dict[str, Any]) -> str | None:
    workspace = payload.get("workspace")
    if not isinstance(workspace, dict):
        return None
    worktree = workspace.get("git_worktree")
    if not isinstance(worktree, str) or not worktree.strip():
        return None
    repository = workspace.get("repo")
    repository_name = repository.get("name") if isinstance(repository, dict) else None
    if not isinstance(repository_name, str) or not repository_name:
        project = workspace.get("project_dir") or workspace.get("current_dir") or payload.get("cwd")
        repository_name = Path(str(project)).name if project else "repo"
    return (
        f"*claude/{compact_ascii(repository_name, fallback='repo', limit=28)}"
        f"@{compact_ascii(worktree, fallback='worktree', limit=24)}"
    )


def render(
    tasks: Sequence[dict[str, Any]],
    *,
    current_task_id: str | None,
    width: int,
    epoch: float,
    extra_entry: str | None,
) -> str:
    ordered = sorted(tasks, key=lambda task: str(task.get("created_at") or ""), reverse=True)
    current_entries: list[str] = []
    other_entries: list[str] = []
    for task in ordered:
        current = task.get("task_id") == current_task_id
        (current_entries if current else other_entries).append(task_label(task, current=current))
    if extra_entry:
        current_entries.insert(0, extra_entry)
    count = len(current_entries) + len(other_entries)
    if not count:
        return ""
    visible_width = max(12, min(width, 1000))
    prefix = f"WT {count} | "
    if current_entries:
        prefix += " | ".join(current_entries)
        if other_entries:
            prefix += " | "
    body = " | ".join(other_entries)
    complete = prefix + body
    if len(complete) <= visible_width:
        return complete
    if not other_entries or len(prefix) >= visible_width:
        return prefix[:visible_width]
    track = " · ".join(other_entries) + "   "
    offset = int(epoch) % len(track)
    return prefix + (track * 2)[offset : offset + visible_width - len(prefix)]


def terminal_width(explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    try:
        return max(12, int(os.environ.get("COLUMNS", "")))
    except ValueError:
        return 100


def read_claude_payload() -> dict[str, Any]:
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            return {}
        value = json.loads(raw) if raw.strip() else {}
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def positive_width(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(prog="agent-task-statusline")
    parser.add_argument("--claude", action="store_true")
    parser.add_argument("--width", type=positive_width)
    parser.add_argument("--epoch", type=float, help=argparse.SUPPRESS)
    args = parser.parse_args()
    payload = read_claude_payload() if args.claude else {}
    workspace = payload.get("workspace")
    current_directory = workspace.get("current_dir") if isinstance(workspace, dict) else None
    if not isinstance(current_directory, str):
        current_directory = payload.get("cwd") if isinstance(payload.get("cwd"), str) else None
    state = Path(os.environ.get("AGENT_TASK_STATE_DIR", "~/.local/state/agent-task")).expanduser()
    tasks = active_worktree_tasks(state)
    current_task_id = task_for_working_directory(tasks, current_directory) or os.environ.get("AI_TASK_ID")
    known_ids = {task.get("task_id") for task in tasks}
    extra = claude_worktree_label(payload) if args.claude and current_task_id not in known_ids else None
    line = render(
        tasks,
        current_task_id=current_task_id,
        width=terminal_width(args.width),
        epoch=args.epoch if args.epoch is not None else time.time(),
        extra_entry=extra,
    )
    if line:
        print(line)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, TypeError, ValueError):
        raise SystemExit(0)

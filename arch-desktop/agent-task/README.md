# agent-task

`agent-task` runs each Codex or Claude coding session in a temporary branch and
worktree. The agent owns file edits and commits; the harness owns integration
and cleanup.

```text
open -> interrupted task -------------------------> resume the native chat
     -> new task -> agent exits with dirty files -> RECOVERY_REQUIRED
                 -> agent process disappears ----> RECOVERY_REQUIRED (never auto-integrate)
                 -> clean commit ----------------> integrate
                                                   |-- success -> cleanup
                                                   `-- conflict/check failure -> recovery
```

Task state is keyed by repository and agent. One interrupted task resumes
automatically; several produce a small picker. Recovery reuses the exact
worktree path and runs `codex resume --last` or `claude --continue`, so the
original conversation is restored without remembering a session ID.

## Use

The installed shell functions launch managed sessions:

```sh
o implement the login timeout
c implement the login timeout
o                         # resume interrupted Codex work, or start fresh
c --new new parallel task # intentionally bypass an interrupted Claude task
```

Outside a Git repository, or when the first argument is a native CLI flag, the
launchers preserve the direct Codex/Claude behavior.

Operator commands are available directly:

```sh
agent-task open "implement feature X" --agent codex
agent-task start "implement feature X" --agent codex
agent-task start "implement feature X" --agent claude --target develop
agent-task start --agent custom --task "custom run" -- ./runner

agent-task list
agent-task status TASK_ID
agent-task integrate TASK_ID
agent-task recover TASK_ID
agent-task recover TASK_ID --new-session
agent-task cleanup TASK_ID
agent-task reconcile
```

Repeat `--check 'command'` to validate the merged candidate. Changed Terraform
files also run `terraform fmt -check` when Terraform is installed. v1 does not
guess application-specific build or test commands.

## Repository memory

The globally ignored `.ai-memory` JSON file accumulates verified, machine-local
knowledge about any repository concern. The harness creates it on first use and
gives each task a private copy.

```json
{
  "schema_version": 1,
  "settings": {"integration_target": "main"},
  "memories": {
    "testing.primary-command": {
      "summary": "Run make test before integration.",
      "evidence": "The repository Makefile and CI use the same target.",
      "updated_at": "2026-08-24T18:00:00+09:00"
    }
  }
}
```

`settings.integration_target` is the only field the harness interprets.
`memories` is an open map of stable dotted keys to objects with a required
`summary`; entries can describe architecture, workflows, commands, testing,
conventions, deployment, dependencies, tools, or gotchas.

Independent keys merge automatically. For a same-key race, the last completed
task wins and the overwritten key remains visible in `agent-task status`.
Invalid memory is archived in task state without blocking code integration, and
`.ai-memory` is rejected if it appears in a result commit. Memory is context,
not authority; it must not contain secrets, guesses, or new transient task
progress, and remembered tools never authorize external mutation.

## Safety and cleanup

- Bubblewrap exposes only the assigned worktree, shared Git data, and the
  selected agent's state as writable host paths.
- The command wrapper blocks branch/worktree/ref/config operations and
  Terraform/OpenTofu mutation commands. It guards accidental misuse, not a
  deliberately hostile process or every possible remote API.
- Integration is serialized per repository and target branch, while coding
  remains parallel.
- The target ref advances only after a clean merge candidate and configured
  checks succeed. The harness does not fetch, push, deploy, or apply Terraform.
- A new task starts from the current checkout's `HEAD`; the memory setting names
  its integration target. A dirty checkout is refused rather than silently
  leaving its work out of the temporary worktree.
- Uncommitted tracked or untracked work keeps its worktree. After a clean commit,
  ignored build artifacts are disposable and are recorded by path before removal.
- Per-task locks keep foreground commands and the hourly reconciler from
  changing the same registry entry concurrently.
- Reconciliation marks dead `CREATED`/`RUNNING` processes for recovery, retries
  explicitly ready work, removes safe terminal worktrees, and registers unknown
  managed worktrees for inspection. It never treats a crash-time commit as done.

Everything is centralized under `~/.local/state/agent-task` by default. New
worktrees use `worktrees/<repo-name>-<short-hash>/<task-id>/`; integration
worktrees and scratch data live in sibling directories and are removed after
use. Conflict resolution, remote synchronization, deployment, and
repository-specific build discovery remain explicit operator concerns.

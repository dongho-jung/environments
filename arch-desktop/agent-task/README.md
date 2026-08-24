# agent-task

`agent-task` lets the first Codex session use the current checkout and moves
only concurrent sessions into temporary branches and worktrees. An ignored
`.ai-lock` at the checkout root is held with `flock` for the life of the agent,
so exits and crashes release ownership automatically even though the empty file
remains. Claude keeps an explicit opt-in launcher. The agent owns file edits and
commits, while the harness owns integration and cleanup for its one assigned
repository.

```text
open --auto -> checkout free ----------------------> native Codex session
            -> checkout busy -> managed worktree --> clean commit -> integrate
                                                    |-- success -> cleanup
                                                    `-- conflict/check failure -> recovery
                              -> interrupted ------> resume the native chat
```

Task state is keyed by repository and agent. One interrupted task resumes
automatically; several produce a small picker. Recovery reuses the exact
worktree path and runs `codex resume --last` or `claude --continue`, so the
original conversation is restored without remembering a session ID.

Codex's built-in `/resume` picker is scoped to the current working directory.
It therefore works normally for the first, in-place session. Use `o resume` to
cross a worktree boundary: it first offers preserved tasks from the current
repository, then runs the all-directory picker with `tui.resume_cwd=current`.
The selected chat attaches to the current checkout when its `.ai-lock` is free,
or to a fresh worktree when another agent is already using that checkout.

## Use

The Codex launcher makes isolation automatic only on contention:

```sh
o                                   # current checkout, or a worktree if busy
o implement the login timeout       # same automatic checkout selection
o resume                            # preserved task, or all saved Codex chats
o resume SESSION_ID                 # current checkout, or a worktree if busy
o --local                           # bypass .ai-lock and run here explicitly
o --new                             # force a new managed worktree
o --task                            # compatibility path for managed recovery

c implement the login timeout       # native Claude session in this checkout
c --new implement a parallel task   # new managed Claude worktree
c --task                            # resume/create a managed Claude task
```

Outside Git, inside an already managed task, with `o --local`, or for Codex
administration subcommands such as `doctor`, `login`, and `mcp`, `o` runs Codex
directly. Ordinary repository sessions use `agent-task open --auto`: an
available checkout runs natively and a busy one gets a new worktree. Claude
arguments and native subcommands still pass through directly unless `--new` or
`--task` is present.

For compatibility with shell functions loaded before this change,
`agent-task open` also launches the requested agent natively unless `--managed`
or `--new` is present. This means updating the linked `agent-task` executable is
enough to unstick an already-open shell; re-sourcing the function is optional.

Operator commands are available directly:

```sh
agent-task open "implement feature X" --agent codex # native compatibility path
agent-task open --auto "implement feature X" --agent codex
agent-task open --managed "implement feature X" --agent codex
agent-task open --managed --new "parallel feature" --agent codex
agent-task resume --agent codex
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

## Lifecycle and cleanup

- Managed agents start in the assigned worktree but run with normal filesystem
  access. There is no Bubblewrap mount namespace, path allowlist, or Git command
  wrapper.
- The harness owns only the assigned repository's temporary branch, worktree,
  integration, and cleanup lifecycle. It does not restrict filesystem paths,
  network access, remote status inspection, other repositories, or otherwise
  authorized operational tools.
- Integration is serialized per repository and target branch, while coding
  remains parallel.
- The target ref advances only after a clean merge candidate and configured
  checks succeed. Automatic harness integration itself does not fetch, push,
  deploy, or apply Terraform; the launched agent can perform user-authorized
  remote or operational work normally.
- A new task starts from the current checkout's `HEAD`; the memory setting names
  its integration target. Explicit worktree requests refuse a dirty checkout.
  Automatic contention deliberately leaves the active session's uncommitted
  files in place and starts the parallel task from committed `HEAD`.
- Integration never advances a checked-out target while its `.ai-lock` is held.
  The completed managed task is queued until the in-place agent exits and the
  target checkout is clean.
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
use. The automatic lifecycle remains repository-agnostic; application-specific
remote synchronization, deployment, and build discovery remain normal agent or
operator work according to the request.

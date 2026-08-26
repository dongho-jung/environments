# agent-task

`agent-task` follows a repository-owned checkout policy: sessions either edit
the reserved current checkout without creating a task branch, or always use
temporary branches and worktrees. Stable checkout locks and separate session
metadata live under
`~/.local/state/agent-task`; no file inside the working tree is the source of
lock ownership. A small supervisor holds the descriptor while the foreground
CLI and every descendant it leaves behind are alive; the agent itself does not
inherit the descriptor. A dead shell launcher therefore cannot release a
checkout while its agent is still alive, and a daemonized child cannot keep
editing after the checkout has been handed to another session. The
ignored `.ai-lock` name is inspected only to interoperate safely with a session
started by an older harness. The agent owns file edits and commits, while the
harness owns integration and cleanup for its one assigned repository.

```text
settings.agent_task_mode=current  -> reserved current checkout
settings.agent_task_mode=worktree -> managed worktree -> clean commit -> integrate
                                                      |-- success -> cleanup
                                                      |-- active lease -> inbox + handoff
                                                      `-- conflict/check failure -> recovery
```

Managed task state is keyed by repository and agent. One interrupted task
resumes automatically; several produce a small picker. Recovery reuses the exact
worktree path. Codex recovery asks App Server for the newest chat whose current
working directory exactly matches that worktree and resumes it by ID; if the
first launch ended before a chat was saved, recovery opens a fresh chat over the
preserved files. Claude recovery runs `claude --continue`.

Codex's built-in `/resume` picker is scoped to the current working directory.
It therefore works normally in `current` mode. Use `o resume` to cross a
worktree boundary: it first offers preserved tasks from the current repository,
then runs the all-directory picker with `tui.resume_cwd=current`.
The selected chat follows the same remembered repository policy.

## Repository checkout policy

Store the durable choice in the ignored repository memory:

```json
{
  "settings": {
    "integration_target": "main",
    "agent_task_mode": "worktree"
  }
}
```

Use `worktree` when independent tasks and validation can safely run in parallel.
Use `current` when the repository has an inherently serialized workflow, shared
generated state, or tooling that requires the canonical checkout. A `current`
repository fails when that checkout is already reserved; it never silently
switches to a task branch. A `worktree` repository isolates the first task too.

Existing repositories without `settings.agent_task_mode` retain the older
contention-aware behavior (current checkout when free, worktree when busy) until
an agent verifies the repository's collision boundaries and records one of the
two durable modes. Transient lock ownership is never written to memory.

## Session handoff

When a completed managed task cannot integrate because another harness session
still owns a repository lease, `agent-task` writes a deduplicated event to that
session's private inbox under `~/.local/state/agent-task/inboxes/` and rings its
supervisor with `SIGUSR1`. The signal is only a doorbell; the durable JSON event
is the source of truth. A supervisor advertises protocol support before it can
be signalled, so sessions launched by an older version are never sent a signal
they do not handle.

For Codex, every new interactive harness session gets its own `codex app-server`
Unix socket. The supervisor uses the supported JSON-RPC interface to
`turn/steer` the current turn or `turn/start` an idle one. For Claude, `Stop` and
`UserPromptSubmit` hooks inject the same inbox event at the next safe lifecycle
point; the supervisor also prints a terminal alert. Claude does not currently
offer an equivalent supported local API for waking an already idle TUI.

The receiving agent finishes the smallest safe checkpoint and runs the command
included in the event:

```sh
agent-task inbox
agent-task handoff ready-0123456789abcdef01234567
```

`handoff` records acceptance, asks the supervisor to end the foreground CLI,
releases the checkout lease through the normal lifecycle, finalizes any current
managed task, and retries each queued integration. It does not ask either agent
to merge, cherry-pick, switch branches, or clean worktrees. A graceful ordinary
exit (`/exit` or the interactive Codex TUI's exit status 130 after `Ctrl+C`)
also drains auto-integrate tasks for that repository immediately after releasing
its lease. The harness retains the raw 130 in task metadata while classifying it
as graceful only for interactive `codex`, `codex resume`, and `codex fork`
commands; non-interactive and non-Codex exits remain failures. Handoff is the
active mechanism that asks a still-working agent to checkpoint and yield.
Abrupt launcher death or a hard kill still leaves task records for the scheduled
`reconcile` fallback.

## Use

Both launchers follow the remembered repository policy:

```sh
o                                   # repository-selected current/worktree mode
o implement the login timeout       # same remembered selection
o resume                            # preserved task, or all saved Codex chats
o resume SESSION_ID                 # repository-selected current/worktree mode
o resume --last -m MODEL PROMPT     # Codex resume flags pass through unchanged
o -C ../another-repo PROMPT         # reserve the repository selected by -C
o review --uncommitted              # requires this exact checkout to be free
o --local                           # bypass locking and run here explicitly
o --new                             # force a new managed worktree
o --task                            # compatibility path for managed recovery

c implement the login timeout       # repository-selected current/worktree mode
c --local                            # bypass locking and run here explicitly
c --new implement a parallel task   # new managed Claude worktree
c --task                            # resume/create a managed Claude task
c --bg investigate a flaky test     # Claude-managed background worktree
c agents                            # manage Claude background sessions directly
c -w feature-auth                   # Claude-managed explicit worktree
```

Outside Git, inside an already managed task, with `o --local`/`c --local`, or
for administrative subcommands such as `doctor`, `login`, and `mcp`, the shell
launchers run the CLI directly. Ordinary repository sessions and mutating Codex
subcommands use `agent-task open --auto`, which reads
`settings.agent_task_mode`. Direct `agent-task open` has the same
repository-policy default; `agent-task open --local` is its explicit bypass. An
unclassified repository alone uses the compatibility contention fallback.

Codex `review` and Claude `ultrareview` are tied to the exact current checkout;
they fail if it is busy instead of silently reviewing a different worktree.
Codex `apply`, `exec`, `fork`, `cloud`, and `sandbox` go through contention
handling because they can create or apply local changes. Codex `-C`/`--cd` is
resolved before lock selection. Claude background, tmux, agent-view management,
and built-in worktree modes pass directly to Claude because they own a separate
worktree/session lifecycle; the shell wrapper does not wrap or integrate them as
`agent-task` tasks. For ordinary sessions, the harness supervisor keeps the
lease until adopted background descendants exit instead of abandoning them.

The personal `o` and `c` launchers intentionally retain their configured
permission-bypass modes. That is an operator policy, not a guarantee supplied by
this harness: `agent-task` coordinates Git lifecycle but does not turn those
modes into an external security sandbox. `--local` changes checkout locking,
not that configured permission policy.

Operator commands are available directly:

```sh
agent-task open "implement feature X" --agent codex # repository policy
agent-task open --auto "implement feature X" --agent codex
agent-task open --local "inspect here" --agent codex
agent-task open --managed "implement feature X" --agent codex
agent-task open --managed --new "parallel feature" --agent codex
agent-task resume --agent codex
agent-task start "implement feature X" --agent codex
agent-task start "implement feature X" --agent claude --target develop
agent-task start --agent custom --task "custom run" -- ./runner

agent-task list
agent-task status TASK_ID
agent-task inbox
agent-task handoff EVENT_ID
agent-task integrate TASK_ID
agent-task recover TASK_ID
agent-task recover TASK_ID --new-session
agent-task cleanup TASK_ID
agent-task reconcile
```

Repeat `--check 'command'` to validate the merged candidate. A check runs from
the task's original repository-relative directory, has a one-hour default
timeout (override with `--check-timeout SECONDS`), and must leave both candidate
HEAD and all tracked or non-ignored untracked files unchanged. Changed Terraform
files also run `terraform fmt -check` from the candidate root when Terraform is
installed. v1 does not guess application-specific build or test commands.

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
Invalid memory is fingerprinted in task state and preserved as a private file
under `memory-proposals/` without blocking code integration. Both `.ai-memory`
and `.ai-lock` are rejected if they appear in any newly introduced commit, even
when a later commit deletes them. A valid proposal is
captured before its worktree is removed but is merged into canonical memory only
after the corresponding code commit reaches the target, or after a successful
task that made no repository change. Failed validation, conflicts, and
`--no-integrate` code results therefore cannot publish premature facts. Memory is
context, not authority; it must not contain secrets, guesses, or new transient
task progress, and remembered tools never authorize external mutation.
Native sessions in a manually created secondary Git worktree get a local memory
copy that is merged safely back into the primary worktree when the foreground
session exits.

## Lifecycle and cleanup

- Managed agents start in the assigned worktree but run with normal filesystem
  access. There is no Bubblewrap mount namespace, path allowlist, or Git command
  wrapper.
- The harness owns only the assigned repository's temporary branch, worktree,
  integration, and cleanup lifecycle. It does not restrict filesystem paths,
  network access, remote status inspection, other repositories, or otherwise
  authorized operational tools.
- Coding remains parallel. Integration takes an exclusive repository activity
  lease and queues while any harness agent is active, then reserves every known
  checkout for the ref update and working-tree synchronization.
- The target ref advances only after a clean merge candidate and configured
  checks succeed. Checks cannot rewrite the candidate and time out instead of
  holding an integration forever. Automatic harness integration itself does not
  fetch, push, deploy, or apply Terraform; the launched agent can perform
  user-authorized remote or operational work normally.
- Every explicit managed task starts from the integration target's committed
  `HEAD`, never from an arbitrary current feature branch. A dirty checkout is
  left untouched. During the unclassified compatibility fallback, the harness
  uses the active branch's actual creation commit from its reflog when that
  branch was created during the session. If no usable creation record exists,
  it uses a safe merge-base bounded by the captured session-start commit. While
  the active agent remains on the target branch, the captured session-start
  commit is used directly, so its mid-session commits are not inherited. Missing or invalid
  live-session metadata falls back to target `HEAD`.
- Immediately before integration, the harness rechecks that the result descends
  from its recorded base, that the target still descends from that base, that
  the target ref has not moved, and that target checkout topology and cleanliness
  are unchanged. A failed invariant queues or preserves the task instead of
  moving a branch.
- `--no-integrate` is stored on the task. The hourly reconciler keeps such a
  result ready until an explicit `agent-task integrate TASK_ID` overrides it.
- A successful foreground command with no repository change is recorded as
  `COMPLETED_NO_CHANGES`, not as a failure.
- Uncommitted tracked or untracked work keeps its worktree. After a successful
  clean commit, ignored build artifacts are recorded in task state and removed
  with the disposable worktree.
- Managed worktree creation disables repository hooks, integration commits use
  the configured Git signing policy, and their generated message follows the
  repository's conventional commit format.
- Per-task locks keep foreground commands and the hourly reconciler from
  changing the same registry entry concurrently.
- Reconciliation marks dead `CREATED`/`RUNNING` processes for recovery, resets
  dead `INTEGRATING`/`VALIDATING` attempts, terminates their owned validation
  process groups, detects an already-applied result, retries ready work, removes
  safe terminal worktrees, and registers unknown managed worktrees for
  inspection. A transient record from an older harness with no owner metadata is
  closed automatically only when its exact result is already present on the
  target; otherwise it is preserved for an explicit
  `agent-task integrate TASK_ID` and never retried automatically. Reconciliation
  never treats a crash-time agent commit as done.

Everything is centralized under `~/.local/state/agent-task` by default. Stable
leases live in `locks/`, live metadata in `sessions/`, and new worktrees in
`worktrees/<repo-name>-<short-hash>/<task-id>/`; integration worktrees and
scratch data live in sibling directories and are removed after use. Invalid
memory proposals remain in the private `memory-proposals/` directory for manual
recovery. The
automatic lifecycle remains repository-agnostic; application-specific remote
synchronization, deployment, and build discovery remain normal agent or
operator work according to the request.

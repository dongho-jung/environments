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
settings.agent_task_mode=worktree -> managed worktree -> clean commit
                                                      |-- publish -> target; session continues
                                                      `-- exit -> integrate -> cleanup/recovery
```

Managed task state is keyed by repository and agent. One interrupted task
resumes automatically; several produce a small picker. A managed Codex process
uses the stable original repository-relative path as its session cwd while
`AI_TASK_WORKTREE` and `AI_TASK_WORKDIR` identify the isolated repository and
starting directory it must edit. The worktree is also passed through Codex's
`--add-dir`. Claude and legacy Codex tasks continue directly in their assigned
worktree. Codex recovery asks App Server for the newest chat whose cwd exactly
matches the preserved task's session cwd and resumes it by ID; if no matching
chat was saved, it opens a fresh chat over the preserved files. Claude recovery
runs `claude --continue`.

Codex's built-in `/resume` picker is scoped to the current working directory.
New managed chats therefore stay grouped under the original repository path
instead of disposable worktree paths. `o resume` still offers preserved tasks
first and can use the all-directory picker for legacy saved chats. The selected
chat follows the same remembered repository policy.

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
`turn/steer` the current turn or `turn/start` an idle one. Delivery failures stay
in the durable inbox and retry without writing raw output into Codex's
full-screen TUI. For Claude, `Stop` and `UserPromptSubmit` hooks inject the same
inbox event at the next safe lifecycle point; the supervisor also prints a
terminal alert. Claude does not currently offer an equivalent supported local
API for waking an already idle TUI.

The receiving agent finishes the smallest safe checkpoint and runs the command
included in the event:

```sh
agent-task inbox
agent-task handoff ready-0123456789abcdef01234567
```

`handoff` records acceptance, asks the supervisor to end the foreground CLI,
releases the checkout lease through the normal lifecycle, finalizes any current
managed task, and retries each queued integration. It does not ask either agent
to merge, cherry-pick, switch branches, or clean worktrees. Interactive Codex
handoff first requests the same graceful shutdown as `Ctrl+C`, allowing the TUI
to restore the terminal and leave its alternate screen; it falls back to
`SIGTERM` only if Codex does not exit promptly. A graceful ordinary exit
(`/exit` or the interactive Codex TUI's exit status 130 after `Ctrl+C`) also
drains auto-integrate tasks for that repository immediately after releasing its
lease. The harness retains the raw 130 in task metadata while classifying it as
graceful only for interactive `codex`, `codex resume`, and `codex fork`
commands; non-interactive and non-Codex exits remain failures. Handoff is the
active mechanism that asks a still-working agent to checkpoint and yield.
Abrupt launcher death or a hard kill still leaves task records for the scheduled
`reconcile` fallback.

## Codex task coordination

Codex 0.150 added `@` references between Codex tasks, a shared-daemon
`codex agents` browser, and `codex queue` for messaging a named session. Those
features coordinate conversations; they do not acquire a checkout lease,
create an `agent-task` worktree, validate a commit, or integrate a result.
Codex-native child tasks within a managed chat remain useful for bounded
parallel investigation, and their progress appears in the native footer.

Top-level `o` tasks intentionally keep separate App Server sockets so an inbox
event can steer or wake one exact harness session. Use `o --new` when parallel
work needs an independently integrated checkout, and use Codex task references
for context or messages among tasks already operating inside a safe checkout
lifecycle. The shared Codex task browser is not a replacement for the harness
when a task can mutate a repository.

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

agent-task context --jira CAPE-123
agent-task context --clear-jira
agent-task statusline
agent-task list
agent-task status TASK_ID
agent-task inbox
agent-task handoff EVENT_ID
agent-task publish
agent-task publish ATTACHMENT_TASK_ID
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

## Active checkpoint publishing

`agent-task publish` validates and publishes the current task's clean committed
`HEAD` to its integration target without ending the managed session or removing
its worktree. The agent runs it after completing and validating requested work,
so the canonical checkout is immediately available for an operator's Terraform,
deployment, or manual shell verification. Later commits remain on the same task
branch and can be published again. Pass an attached task ID to publish a
secondary repository owned by the current session.

Publishing serializes the target ref and reserves its checkout while allowing
other independent managed worktrees to continue. It rechecks the source and
target commits, checkout topology, and cleanliness after validation. It updates
only the local integration target: it does not fetch, push, deploy, or run
Terraform on its own.

A result that directly descends from the target fast-forwards it without adding
a synthetic merge commit. If the combined result tree is already present, the
target does not move. Only genuinely divergent histories create a merge commit;
its title comes from the task's primary commit, and its body records the task ID,
task-to-target path, and included commit hashes and subjects.

## Agent status display

`agent-task statusline` reads the local task registry and prints only managed
worktrees whose recorded process identity is still alive. The compact format
shows the task count, current task (`*`), agent, repository, start time, attached
secondary repositories (`+`), and an owning Jira issue when one is known:

```text
WT 3 | *codex/backend@21:31[CAPE-123] | claude/web@21:18 | codex/infra@20:54+
```

The current entry stays pinned. If the remaining entries do not fit the
terminal width, they move by one character per second in a repeating marquee.
Claude runs the lightweight `agent_statusline.py --claude` renderer through its
native status-line API. The command also recognizes Claude's current built-in
Git worktree from the JSON payload. Managed Codex sessions enable the native
footer with a compact managed-worktree identity, model/reasoning/fast mode, and
active child-task progress. A typical first item is
`WT#17 · ai/codex/20260828-150920-7fb1e6→main · .../projects/environments/arch-desktop · CAPE-123`.
The number is a stable, global harness worktree number; the path is the last
three components of the logical project directory with a 48-character cap; and
the arrow names the integration target. Jira appears only when known. Context
remaining, hostname, and a redundant project name are intentionally omitted.

The App Server bridge immediately names an unnamed thread so Codex never shows
its internal UUID as the `thread-title` fallback. Existing generated names and
later `/rename` values are retained after ` :: `. When a session owns attached
secondary repositories, the managed identity rotates through their actual task
branches and logical paths every five seconds. The compact `1/3*`, `2/3`, ...
field identifies the carousel position, with `*` marking the primary task. The
bridge supplies these values because a managed Codex chat keeps the canonical
checkout as its logical cwd while editing assigned worktrees, so native
`git-branch` and `current-dir` can describe the wrong checkout. Neither
integration writes to Kitty's status line.

A Jira-shaped key in the task's launch description is detected automatically.
When an agent selects or creates the issue later, it records display-only local
context without touching Jira:

```sh
agent-task context --jira CAPE-123
agent-task context --clear-jira
```

The context command defaults to `AI_TASK_ID` and writes a separate local context
record, so it does not contend with the lifecycle lock held by the running task.
The status renderer never polls Jira; normal Jira assignment, transitions,
comments, and completion remain owned by the Jira workflow.

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

- Managed Codex sessions keep the original checkout as their logical cwd for
  stable history and receive the assigned worktree through `--add-dir`; their
  instructions require all repository work under `AI_TASK_WORKDIR`. Claude and
  custom agents start in the assigned worktree. All agents run with normal
  filesystem access; there is no Bubblewrap mount namespace, path allowlist, or
  Git command wrapper.
- The harness owns only the assigned repository's temporary branch, worktree,
  integration, and cleanup lifecycle. It does not restrict filesystem paths,
  network access, remote status inspection, other repositories, or otherwise
  authorized operational tools.
- Coding remains parallel. Final integration takes an exclusive repository
  activity lease and queues while any harness agent is active, then reserves
  every known checkout for the ref update and working-tree synchronization.
  Active checkpoint publishing instead holds the per-target integration lock
  and reserves only the target checkout, so unrelated managed worktrees keep
  running.
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
- Managed worktree creation disables repository hooks. Direct descendants
  fast-forward without an integration commit, equivalent trees do not advance
  the target, and genuine divergent merges use the configured Git signing
  policy with a conventional title and a body listing the task and commits.
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

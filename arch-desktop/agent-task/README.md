# agent-task

`agent-task` runs every ordinary repository session in a managed task. Every
interactive Codex prompt provisions its semantic branch and isolated worktree
before the model turn starts. Stable checkout locks and separate session
metadata live under
`~/.local/state/agent-task`; no file inside the working tree is the source of
lock ownership. A small supervisor holds the descriptor while the foreground
CLI is alive and while it terminates and reaps every remaining descendant; the
agent itself does not inherit the descriptor. A dead shell launcher therefore
cannot release a checkout while its agent is still alive, and a daemonized child
cannot keep editing after the checkout has been handed to another session. The agent owns
file edits and commits, while the harness owns integration and cleanup for its
one assigned repository.

```text
interactive Codex -> reserved path -> first prompt -> semantic worktree
Claude/custom -------------------------------------> managed worktree
                                                           |
                                                           `-> clean commit
                                                               |-- publish -> target; session continues
                                                               `-- exit -> integrate -> cleanup/recovery
```

Managed task state is keyed by repository and agent. An interrupted task with
no repository changes is completed and cleaned automatically. One meaningful
task resumes directly; several produce a picker led by semantic title, branch
route, changed-file or commit count, update time, and only a short diagnostic
ID. Pressing Enter resumes the entire list sequentially in one launcher run;
selecting a number resumes just that item. Generic `interactive agent task`
placeholders are neither stored for new untitled launches nor shown. A managed Codex process
uses the stable original repository-relative path as its session cwd while
`AI_TASK_WORKTREE` and `AI_TASK_WORKDIR` identify the isolated repository and
starting directory it must edit. The worktree is also passed through Codex's
`--add-dir`. Claude and custom tasks run directly in their assigned worktree.
Launcher interrupts record their exception type and preserve any dirty or
committed result as recovery work; legacy interrupted tasks that were marked
`FAILED` are migrated back into the same recovery path.
For a new interactive Codex task, the harness starts the TUI with an empty
reserved path and no task branch. Its trusted `UserPromptSubmit` hook asks an
ephemeral, read-only Luna turn only for a short semantic slug, then creates the
branch and worktree before releasing that prompt to the model. Inspection-only
prompts use the same isolated lifecycle; command-name allowlists and partial
`PreToolUse` coverage are not used as a write-safety boundary.

The first branch uses the semantic slug directly, such as
`skip-read-worktree`. Only a real local branch collision adds `-2`, `-3`, and so
on. Secondary repositories reuse the same slug and resolve collisions within
their own repositories. If naming fails, a deterministic whole-word fallback
still provisions the worktree. Before the first prompt, App Server gives the
zero-turn thread an invisible placeholder name so the raw UUID does not flash
as its title; the supervisor deletes that exact thread if the TUI exits before
it receives a turn. The Codex thread name then shows `<branch> -> <target>`.
Codex recovery asks App Server for the newest chat whose cwd exactly
matches the preserved task's session cwd and resumes it by ID; if no matching
chat was saved, it opens a fresh chat over the preserved files. Claude recovery
runs `claude --continue`.

Codex's built-in `/resume` picker is scoped to the current working directory.
New managed chats therefore stay grouped under the original repository path
instead of disposable worktree paths. `o resume` offers preserved tasks first
and can use the all-directory picker for saved chats. Saved chats also resume in
a managed worktree.

## Session handoff

When a completed managed task cannot integrate because another harness session
still owns a repository lease, `agent-task` writes a deduplicated event to that
session's private inbox under `~/.local/state/agent-task/inboxes/` and rings its
supervisor with `SIGUSR1`. The signal is only a doorbell; the durable JSON event
is the source of truth.

For Codex, every new interactive harness session gets its own `codex app-server`
Unix socket. The supervisor uses the supported JSON-RPC interface to
`turn/steer` the current turn or `turn/start` an idle one. Delivery failures stay
in the durable inbox and retry without writing raw output into Codex's
full-screen TUI. The App Server and foreground TUI inherit the same durable
session identity, so tool subprocesses can accept the delivered handoff command
without reconstructing private state paths. The pending-task first-prompt hook
is installed only on this private App Server, avoiding duplicate client/server
hook execution. User-selected Codex config, model, profile, feature, and
permission options are inherited by the App Server instead of being reset at
the remote-TUI boundary. For a pre-created or recovered thread, the App Server's
resolved reasoning effort is also passed explicitly to the remote TUI; this
preserves any user-selected value instead of displaying and applying `default`.
Before creating the pending thread, a short-lived App Server reports the exact
harness hook hash. Only that hash is reflected into the final App Server's
session-local trust state, avoiding both a hook-review screen and a persistent
global trust change. Each hook command points at a content-addressed runtime
snapshot, so updating the installed launcher cannot remove code still needed by
an open session. For Claude, `Stop` and
`UserPromptSubmit` hooks inject the same
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
`SIGTERM` only if Codex does not exit promptly. After either a handoff or an
ordinary exit, the supervisor gives the private control bridge two seconds to
stop before forcing it. Before closing the receiver, `handoff` rechecks whether
the queued result is already on its target. A stale notice is resolved in place
and the current session stays open. A graceful ordinary exit
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
parallel investigation, but their count is not included in the configured
footer.

Top-level `o` tasks intentionally keep separate App Server sockets so an inbox
event can steer or wake one exact harness session. Use `o --new` when parallel
work needs an independently integrated checkout, and use Codex task references
for context or messages among tasks already operating inside a safe checkout
lifecycle. The shared Codex task browser is not a replacement for the harness
when a task can mutate a repository.

## Use

Both launchers use the managed task lifecycle for ordinary repository sessions;
interactive Codex names and creates its worktree on the first prompt:

```sh
o                                   # managed; worktree on the first prompt
o implement the login timeout       # managed worktree with initial prompt
o resume                            # preserved task, or all saved Codex chats
o resume SESSION_ID                 # saved chat in a managed worktree
o resume --last -m MODEL PROMPT     # Codex resume flags pass through unchanged
o -C ../another-repo PROMPT         # reserve the repository selected by -C
o review --uncommitted              # requires this exact checkout to be free
o --local                           # bypass locking and run here explicitly
o --new                             # force a new managed worktree

c implement the login timeout       # managed worktree
c --local                            # bypass locking and run here explicitly
c --new implement a parallel task   # new managed Claude worktree
c --bg investigate a flaky test     # Claude-managed background worktree
c agents                            # manage Claude background sessions directly
c -w feature-auth                   # Claude-managed explicit worktree
```

Outside Git, inside an already managed task, with `o --local`/`c --local`, or
for administrative subcommands such as `doctor`, `login`, and `mcp`, the shell
launchers run the CLI directly. Ordinary repository sessions use
`agent-task open`, which always creates or resumes a managed task. Interactive
Codex creates its semantic worktree on the first prompt; other managed commands
create the worktree immediately. `agent-task open --local` is the explicit
native-checkout bypass.

Codex `review` and Claude `ultrareview` are tied to the exact current checkout;
they fail if it is busy instead of silently reviewing a different worktree.
Codex `apply`, `exec`, `fork`, `cloud`, and `sandbox` use fresh managed
worktrees because they can create or apply local changes. Codex `-C`/`--cd` is
resolved before worktree creation. Claude background, tmux, agent-view management,
and built-in worktree modes pass directly to Claude because they own a separate
worktree/session lifecycle; the shell wrapper does not wrap or integrate them as
`agent-task` tasks. For ordinary sessions, foreground exit causes the harness
supervisor to terminate and reap adopted background descendants before it
releases the checkout lease.

The personal `o` and `c` launchers intentionally retain their configured
permission-bypass modes. That is an operator policy, not a guarantee supplied by
this harness: `agent-task` coordinates Git lifecycle but does not turn those
modes into an external security sandbox. `--local` changes checkout locking,
not that configured permission policy.

Operator commands are available directly:

```sh
agent-task open "implement feature X" --agent codex
agent-task open --local "inspect here" --agent codex
agent-task open --new "parallel feature" --agent codex
agent-task resume --agent codex
agent-task start "implement feature X" --agent codex
agent-task start "implement feature X" --agent claude --target develop
agent-task start --agent custom --task "custom run" -- ./runner

agent-task context --jira CAPE-123
agent-task context --clear-jira
agent-task context --pr 321
agent-task context --clear-pr
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
Terraform on its own. When the publishing task later exits, a target that
already contains its result is recognized under the target integration lock and
completed without requesting exclusive repository activity or evicting another
active session.

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
Git worktree from the JSON payload. Managed Codex sessions use native footer
items for the logical current directory, thread title, and model/reasoning
state. The harness sets the thread title to the task-branch/base-branch route
and deliberately omits native `task-progress`, so the low-value `Tasks #/#`
counter is not shown. Because these launchers already use YOLO permissions,
they mark only the selected project paths trusted for the process and set
`tui.show_tooltips=false`; Codex therefore skips both its first-project command
list and rotating tips. The current Codex TUI owns that same bottom row while
the composer is active and temporarily replaces configured footer items with
its queue/context hint; it does not expose a setting that keeps the footer
pinned while typing. Neither integration writes to Kitty's status line.

A Jira-shaped key, explicit `PR #321`, or a GitHub pull-request URL in the task's
launch description is detected automatically. When an agent learns either value
later, it records display-only local context without touching Jira or GitHub:

```sh
agent-task context --jira CAPE-123
agent-task context --clear-jira
agent-task context --pr 321
agent-task context --clear-pr
```

The context command selects the managed scope containing the current working
directory, then falls back to `AI_TASK_ID`; `--task TASK_ID` selects one
explicitly. This lets an attached repository carry its own PR while inheriting
the primary Jira issue when it has no separate one. Context is a separate local
record, so it does not contend with the lifecycle lock held by the running task.
The Claude status renderer never polls Jira or GitHub; normal Jira and
pull-request workflows remain authoritative.

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
under `memory-proposals/` without blocking code integration. `.ai-memory` is
rejected if it appears in any newly introduced commit, even when a later commit
deletes it. A valid proposal is
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
- Every managed task starts from the integration target's committed `HEAD`,
  never from an arbitrary current feature branch. Dirty checkout files and
  branch-only commits are left untouched and are never inherited by a task.
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
  inspection. A path recorded as ready but no longer registered with Git is
  moved intact into `~/.local/state/agent-task/quarantine/` before repair or
  cleanup; stale session metadata is removed only after its external checkout
  lock is confirmed free. A transient integration record with no owner metadata
  is closed
  automatically only when its exact result is already present on the target;
  otherwise it is preserved for an explicit
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

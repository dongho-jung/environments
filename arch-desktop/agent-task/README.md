# agent-task

`agent-task` is a deliberately small lifecycle wrapper for Codex and Claude
Code. One run gets one temporary branch and one temporary Git worktree. The
agent may edit and commit; the parent process owns integration and cleanup.

```text
start -> agent -> clean commit -> integrate -> cleanup
                  |                |
                  +-- dirty -------+-- conflict/check failure
                                   |
                                   v
                           RECOVERY_REQUIRED
```

The durable output is a commit. A dirty or ambiguous worktree is always kept.

## Use

The installed shell functions preserve the familiar launchers:

```sh
o implement the login timeout
c implement the login timeout
```

The direct interface is:

```sh
agent-task start "implement feature X" --agent codex
agent-task start "implement feature X" --agent claude --target develop
agent-task start --agent custom --task "custom run" -- ./runner

agent-task list
agent-task status TASK_ID
agent-task integrate TASK_ID
agent-task recover TASK_ID
agent-task cleanup TASK_ID
agent-task reconcile
```

Add repeated `--check 'command'` options for checks that must pass on the
merged candidate. Changed Terraform files also get `terraform fmt -check` when
Terraform is installed. There is intentionally no general language/build
command guessing in v1.

## Safety boundary

Bubblewrap makes the host filesystem read-only except for the assigned
worktree, shared Git metadata, and the selected agent's state directory. It
also hides system runtime sockets. A command wrapper blocks normal attempts to
switch branches, manage worktrees, merge/rebase, rewrite refs/config, fetch,
push, or run Terraform/OpenTofu mutation commands.

This protects against accidental lifecycle mistakes; it is not a hostile-code
sandbox. A determined process could call an alternate binary or a remote API.
The global agent instructions therefore also forbid bypasses and all deployment
or shared-state mutation from coding sessions.

## Lifecycle rules

- Integration is serialized per repository and target branch; coding is not.
- Integration uses a separate detached worktree and only fast-forwards the
  local target after the merge and checks succeed.
- The harness does not fetch, push, deploy, or mutate infrastructure.
- A dirty target queues the result instead of touching the checkout.
- Dirty, conflicted, and validation-failed task worktrees are preserved for
  `recover`.
- Cleanup never removes uncommitted or ignored files. Ignored artifacts require
  an explicit `cleanup --discard-ignored` after inspection.
- Task metadata lives in `${XDG_STATE_HOME:-~/.local/state}/agent-task`.
- The hourly reconciler resumes known clean tasks, prunes stale Git metadata,
  and registers unknown worktrees under its own managed directory as recovery
  items. It does not guess how to merge or delete an unknown orphan.

That conservative stop-and-preserve behavior is intentional. Smarter build
discovery, remote synchronization, deployment serialization, and automatic
conflict solving are outside v1.

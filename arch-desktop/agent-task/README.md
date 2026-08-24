# agent-task

`agent-task` runs each Codex or Claude coding session in a temporary branch and
worktree. The agent owns file edits and commits; the harness owns integration
and cleanup.

```text
start -> agent -> dirty files --------------------> RECOVERY_REQUIRED (keep worktree)
               -> clean, no commit --------------> FAILED (remove worktree + branch)
               -> clean commit -> remove worktree -> integrate
                                                   |-- success -> remove branch
                                                   `-- conflict/check failure
                                                       -> RECOVERY_REQUIRED (keep commit)
```

A clean committed result never needs an idle worktree. `recover` recreates one
from the retained branch only when more work is necessary.

## Use

The installed shell functions launch managed sessions:

```sh
o implement the login timeout
c implement the login timeout
```

Operator commands are available directly:

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

Repeat `--check 'command'` to validate the merged candidate. Changed Terraform
files also run `terraform fmt -check` when Terraform is installed. v1 does not
guess application-specific build or test commands.

## Repository memory

The globally ignored `.ai-metadata` JSON file records stable local knowledge
such as the target branch, deployment strategy, environments, and required MCP
tool names. The harness creates it on first use and gives each task a private
copy.

```json
{
  "schema_version": 1,
  "branching": {"target_branch": "main", "strategy": null},
  "deployment": {
    "strategy": null,
    "environments": {},
    "required_mcp_tools": [],
    "notes": []
  },
  "repository_notes": []
}
```

Independent field changes merge automatically. For a same-field race, the last
completed task wins and the overwritten field names remain visible in
`agent-task status`; metadata never blocks code integration or retains a
worktree. `.ai-metadata` is rejected if it appears in a result commit.

Metadata is context, not authority. It must not contain secrets or task progress,
and recorded deployment tools never authorize external mutation.

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
- Uncommitted tracked or untracked work keeps its worktree. After a clean commit,
  ignored build artifacts are disposable and are recorded by path before removal.
- Per-task locks keep foreground commands and the hourly reconciler from
  changing the same registry entry concurrently.
- Reconciliation retries ready work, removes safe terminal worktrees, prunes
  stale Git metadata, registers unknown managed worktrees for recovery, and
  exits nonzero when operator recovery is required.

Task metadata lives in `~/.local/state/agent-task` by default. Conflict resolution,
remote synchronization, deployment, and repository-specific build discovery
remain explicit operator concerns.

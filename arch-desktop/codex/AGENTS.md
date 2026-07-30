# Global Codex instructions

## Branch and worktree isolation

- When a task requires creating or checking out a task branch, create a dedicated Git worktree for the current Codex session and do all branch-related work there. Do not switch a shared checkout to the task branch.
- Give every concurrently running Codex session or agent its own worktree and branch. Never reuse or modify a worktree owned by another session, even if it appears idle.
- Before creating a worktree, inspect `git status` and `git worktree list`. Preserve all existing work and choose a unique worktree path and branch name. If the current session is already running in a dedicated worktree, use it instead of creating another.
- Follow an explicit user request to use a particular checkout, branch, or worktree.

# Global Codex instructions

## Branch and worktree isolation

### Location and naming

- By default, before a task writes, modifies, generates, moves, or deletes files anywhere inside a Git repository, create a dedicated Git worktree and task branch for the current Codex session and perform all repository writes there. Treat the canonical checkout as read-only unless the user explicitly directs otherwise.
- Use `~/.worktrees` as the single root for all agent-created temporary worktrees. Do not create them inside the repository, beside the repository, under `/tmp`, or in another ad hoc location.
- Name each path `~/.worktrees/<repo>-<task-slug>`, where `<repo>` is the repository root directory name and `<task-slug>` is a concise kebab-case task name. Add a short owner or numeric suffix only when the intended path already exists.
- Follow an explicit user request to use a particular checkout, branch, worktree, or location instead of these defaults.

### Creation and ownership

- Give every concurrently running Codex session or agent its own worktree and branch. Never reuse or modify a worktree owned by another session, even if it appears idle.
- Before creating one, inspect `git status --short --branch` and `git worktree list --porcelain`, then verify the exact target path and branch are unused. Preserve every existing dirty or untracked change.
- If the current session is already in its own dedicated worktree, reuse it instead of creating another. Otherwise create the worktree from the intended base branch in `~/.worktrees` before making any repository write.
- Immediately mark a newly created or resumed worktree as active with `git worktree lock --reason "Codex active: <branch>" <path>`. A lock is an ownership signal: never unlock, move, remove, or write in a worktree locked by another session.
- Do not relocate a legacy worktree outside `~/.worktrees` merely for consistency while it may be in use. Its owner may move it after confirming that it is inactive and clean; otherwise let the lifecycle rules below retire it after merge.

### Lifecycle and cleanup

- Inspect registered worktrees for housekeeping before creating a new one and again before the final handoff. An active session must unlock its own worktree as its final lifecycle action so a later session can recognize it as inactive.
- Automatically remove a worktree only when every condition below is true:
  - It is not the canonical checkout or the current worktree, and it is not locked.
  - `git -C <path> status --porcelain --untracked-files=all` is empty.
  - Its branch is confirmed merged into the intended integration branch, either by Git ancestry or by an authoritative merged PR/MR status for squash or rebase merges. Refresh remote refs first when that is available; never infer merge status from a stale or missing ref.
  - The exact path and branch have been rechecked immediately before removal.
- Run cleanup from the canonical checkout or another retained worktree. Use `git worktree remove <exact-path>` without `--force`, then use `git branch -d <branch>` only if Git accepts the safe deletion. If branch deletion is refused, leave the branch and report it rather than forcing it.
- Use `git worktree prune --dry-run` first. Run `git worktree prune` only when every reported entry has been confirmed stale; otherwise leave the metadata intact and report it.
- Never use `rm -rf`, a glob, `git worktree remove --force`, or `git branch -D` for routine cleanup. Never delete a dirty, locked, unmerged, or ambiguous worktree. Leave it in place and report its path, branch, and blocking condition.
- If the current task is already merged at handoff, clean up its worktree using these checks. If it is not merged, preserve the worktree and branch, unlock it at handoff, and report their exact names for later cleanup.

## Commit conventions

Follow these whenever you create a commit — not only when asked to "commit properly". `/c` runs the full interactive version of this (gather state, propose a plan, confirm, split branches, optionally open PRs); this section is the always-on baseline those conventions distill to.

### One commit = one intent

- Split changes into separate commits by intent; never mix unrelated purposes in one commit.
- Always split when the changes combine: feature + bug fix, refactor + behavior change, config/build + product code, docs-only + code, independent modules, or multiple unrelated bugs.
- A single commit is fine only when it has one clear purpose, bundles files that must ship together for one feature/fix, is a trivial typo/format/mechanical change, or touches one file whose intertwined changes cannot be cleanly separated.

### Conventional type

Decide the type in this order; when in doubt prefer `fix`/`refactor`/`chore` over `feat`:

- `fix` — corrects broken behavior or wrong logic.
- `feat` — adds a new capability, option, or flow.
- `refactor` — same behavior, structure only.
- `chore` — config, build, CI, deps, tooling.
- `docs` — documentation only.
- `test` — tests only, product behavior unchanged.
- `style` — formatting or lint only.

Mark breaking changes: append `!` to the type (`feat!: …`) or add a `BREAKING CHANGE:` line in the body. Treat API signature changes, removed/changed behavior, config/env format changes, and required-dependency changes as breaking.

### Message format

- Title: English, imperative, ≤ 50 chars, `type: summary` (scope optional: `type(scope): summary`; use `type!:` for breaking).
- Body: Korean, 2-depth bullet list. Keep trivial changes short — no filler just to fill the format.

```
type: concise english title

- 주요 변경사항
  - 세부 내용 1
  - 세부 내용 2
```

### Branch targets

- Default to the current branch; branch splitting is conservative.
- Split onto a new branch only when the work is a clearly independent domain, warrants its own PR (different reviewers or merge timing), or mixes a hotfix with normal work — and only if the commit groups do not touch the same files. If they overlap on files, keep them together and say why.
- On a shared branch (`main`/`master`/`develop`), prefer moving the work to a new `type/kebab-name` branch instead of committing directly.

### Safety

- Never run destructive git commands (`git reset --hard`, `git checkout -f`, force push) or `--no-verify` unless the user explicitly asks.
- If a commit hook, checkout, or push fails, stop and show `git status`; do not auto-recover, roll back, or force.

# Global Codex instructions

## Branch and worktree isolation

- By default, before a task writes, modifies, generates, moves, or deletes files anywhere inside a Git repository, create a dedicated Git worktree and task branch for the current Codex session and perform all repository writes there. Treat an existing checkout as read-only unless it is already a dedicated worktree owned by this session or the user explicitly directs otherwise.
- Give every concurrently running Codex session or agent its own worktree and branch. Never reuse or modify a worktree owned by another session, even if it appears idle.
- Before creating a worktree, inspect `git status` and `git worktree list`. Preserve all existing work and choose a unique worktree path and branch name. If the current session is already running in a dedicated worktree, use it instead of creating another.
- Follow an explicit user request to use a particular checkout, branch, or worktree.

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

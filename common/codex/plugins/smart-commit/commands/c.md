---
description: Smart commit workflow. Analyze git changes, propose split conventional commits, confirm with the user, commit, and optionally push/create PRs with `/c pr`.
---

# Smart Commit

Use this command to turn the current repository changes into intentional commits.

Arguments: `$ARGUMENTS`

If the arguments include `pr`, `PR`, or `--pr`, run in **PR mode**: after confirmed commits are created, push the target branch or branches and create/update PRs. Otherwise, stop after committing.

## Preflight

Gather repository context before proposing anything:

```bash
git branch --show-current 2>/dev/null || echo "detached HEAD or no branch"
git status --short
git diff --cached --stat
git diff --stat
git diff HEAD
git log --oneline -5 2>/dev/null || echo "No commits yet"
git branch 2>/dev/null | head -20 || echo "no branches"
git remote -v 2>/dev/null | head -4 || echo "no remote"
git rev-parse --abbrev-ref origin/HEAD 2>/dev/null || echo "unknown"
```

For PR mode, also check:

```bash
gh auth status 2>&1 | head -5 || echo "gh not available"
git log --oneline @{upstream}..HEAD 2>/dev/null | head -20 || echo "no upstream or unable to compare"
```

If not in a git repository, stop and say so. If the working tree is clean and this is not PR mode, stop and say there is nothing to commit.

PR mode special case:
- If the working tree is clean, skip commit planning and use the current branch's unpushed/ahead commits as the PR candidate.
- If there are no unpushed/ahead commits either, stop and say there is nothing to commit or push.

## Plan

Core rules:

- One commit should represent one clear intent.
- Split commits by intent by default.
- Keep branch splitting conservative.
- PR creation is opt-in and only happens in PR mode.
- Never use destructive git commands such as `git reset --hard`, `git checkout -f`, or force push unless the user explicitly asks.
- Do not use `--no-verify` automatically.

Workflow:

1. Analyze staged and unstaged changes.
2. Split changes into commit groups by intent.
3. Decide whether all groups stay on the current branch or some should move to new branches.
4. Propose commit messages, branch targets, and, in PR mode, PR title/body drafts.
5. Ask the user for confirmation before staging or committing.
6. Commit the approved groups sequentially.
7. In PR mode only, push and create/update PRs after commits succeed.

## Commands

### 1. Split Changes By Intent

Split when changes include clearly different purposes:

- Feature work plus bug fixes.
- Refactoring plus behavior changes.
- Configuration/build changes plus product code.
- Documentation-only changes mixed with code changes.
- Independent modules or components.
- Multiple unrelated bugs.

A single commit is acceptable only when:

- The change has one clear purpose.
- The files must ship together for one feature/fix.
- The work is a small typo, formatting, or mechanical update.
- The same file has intertwined changes that cannot be safely separated.

Use conventional commit types:

- `feat`: new user-visible functionality or expanded capability.
- `fix`: correction of broken behavior or incorrect logic.
- `refactor`: structural change without intended behavior change.
- `style`: formatting or lint-only style changes.
- `docs`: documentation-only changes.
- `chore`: config, build, dependency, tooling, or repository maintenance.
- `test`: test-only changes.

When uncertain, prefer `fix`, `refactor`, or `chore` over `feat`.

Mark breaking changes when required:

- Use `type!:` in the title, or include `BREAKING CHANGE:` in the body.
- Treat API signature changes, removed behavior, config/env format changes, or required runtime/dependency changes as breaking.

### 2. Decide Branch Targets

Default: keep all commits on the current branch.

Suggest separate branches only when this is clearly safer or more natural:

- The work belongs to unrelated domains.
- Separate PRs are likely because review owners or merge timing differ.
- A hotfix is mixed with normal feature work.
- The changes are independent and do not share files.

Keep the same branch when:

- Changes are part of the same feature/fix/refactor.
- Later work depends on earlier work.
- File-level separation is unsafe.
- The current branch already has an appropriate name.

Before proposing branch splits, check whether target groups touch the same files. If groups overlap on files, keep them on the same branch and tell the user that file overlap made branch splitting unsafe.

Branch naming:

- Use conventional prefixes such as `feat/`, `fix/`, `refactor/`, `chore/`, `docs/`, or `test/`.
- Use short kebab-case names.
- If currently on `main`, `master`, or `develop`, consider proposing a new branch for all commits.

### 3. Propose Commit Plan

For each commit, present:

```text
Commit N:
- Target branch: <branch>
- Files: <paths>
- Intent: <feat/fix/refactor/docs/chore/test/style>
- Breaking change: yes/no
- Title: <English conventional commit title, <= 50 chars>
- Body:
  - Key changes
    - <detail>
    - <detail>
- Verification:
  - <tests/checks to run or why skipped>
```

Commit message format:

```text
type: concise English title

- Key changes
  - Detail 1
  - Detail 2
```

Keep commit titles in English. Body can be English or Korean, but prefer concise technical language.

If multiple branches are proposed, add a branch summary:

```text
Branch <current-branch>:
- Commit 1: <title>

Branch <new-branch>:
- Commit 2: <title>
```

### 4. PR Mode Drafts

In PR mode, draft one PR per target branch that is not `main`, `master`, or `develop`.

PR title:

- English.
- About 70 characters or less.
- For a single-commit branch, use the commit title when suitable.
- For a multi-commit branch, summarize the branch's main outcome.

PR body should be mostly Korean and include:

```markdown
## 변경 요약
<1-2줄 요약>

## 무엇이 / 어떻게 바뀌었나
- <변경 포인트>
  - <구현/파일/함수>

## 왜 바뀌었나
<배경과 해결하려는 문제>

## 주의할 점
- <호환성 영향, breaking change, 마이그레이션, 한계, 후속 작업>

## 테스트 / 검증
- [ ] <확인 항목>
```

Do not create PRs until commits succeed.

### 5. Confirm Before Mutating

Before staging, committing, switching branches, pushing, or creating PRs, ask the user to confirm:

- Commit grouping.
- Branch targets and any new branch names.
- Commit messages.
- In PR mode: PR titles/bodies, draft vs normal PR, and base branch if it should differ from the default.

If the user cancels, stop without committing.

If the user asks for edits, update the plan and ask again.

### 6. Commit Execution

Single branch:

1. Stage only the files for the current commit.
2. Commit with the approved message.
3. Repeat for each commit.
4. After all commits, run `git status --short` and `git log --oneline -5`.

Branch split:

1. Save the original branch:

   ```bash
   ORIG_BRANCH=$(git branch --show-current)
   ```

2. Commit groups that stay on the original branch first.
3. For each new branch:
   - Verify it does not already exist:

     ```bash
     git show-ref --verify --quiet refs/heads/<branch>
     ```

   - Create it from the original branch:

     ```bash
     git checkout -b <branch>
     ```

   - Stage and commit only the approved files for that branch.
   - Return to the original branch:

     ```bash
     git checkout "$ORIG_BRANCH"
     ```

4. Stop immediately if checkout, staging, commit hooks, or branch creation fails. Show `git status --short` and explain the issue.

### 7. PR Mode Execution

Only run this after all approved commits succeed.

Preflight:

- `gh auth status` must show a logged-in GitHub account.
- `origin` must be a GitHub remote.
- At least one non-default target branch must have commits ahead of its base/upstream.

For each PR branch:

1. Check out the branch.
2. Push:
   - If no upstream: `git push -u origin <branch>`.
   - If upstream exists: `git push`.
3. Check for an existing open PR:

   ```bash
   gh pr view <branch> --json url,state,number 2>/dev/null
   ```

4. If an open PR exists, ask whether to update title/body with `gh pr edit`.
5. If no PR exists, create one:

   ```bash
   gh pr create \
     --head <branch> \
     --title "<title>" \
     --body "$(cat <<'EOF'
<approved PR body>
EOF
)"
   ```

6. Add `--base <branch>` only if the user explicitly chose a base.
7. Add `--draft` only if the user chose draft.

Never force push automatically. If push fails because of non-fast-forward or remote conflicts, stop and explain the state.

## Verification

After commit mode:

```bash
git status --short
git log --oneline -5
```

After branch split:

- Confirm current branch.
- Show `git log --oneline -5` for each affected branch.
- Confirm no unintended staged changes remain.

After PR mode:

- Show branch name, PR URL, and PR state for each created or updated PR.
- Return to the original branch when possible.

## Summary

Report concisely:

- Commits created, with hashes and titles.
- Branches created or updated.
- PR URLs if PR mode ran.
- Any checks run and their result.
- Any skipped step, with the reason.

## Next Steps

Suggest only concrete follow-ups that fit the result, such as:

- Run a specific test command if it was skipped.
- Review a created PR URL.
- Resolve a push/auth failure before rerunning `/c pr`.

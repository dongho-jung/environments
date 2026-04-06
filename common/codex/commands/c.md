---
description: Smart commit - analyze diffs, propose commit messages, get confirmation, then commit (Codex, English-only)
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(git add:*), Bash(git commit:*), Bash(git log:*), AskUserQuestion
---

## Current Git State

**Git Status:**
!`git status --short`

**Staged Changes:**
!`git diff --cached --stat`

**Unstaged Changes:**
!`git diff --stat`

**Full Diff (staged + unstaged):**
!`git diff HEAD`

**Recent Commit Style Reference:**
!`git log --oneline -5 2>/dev/null || echo "No commits yet"`

## Workflow Instructions

### Core Principle: one commit = one intent

**Splitting is the default.** If multiple intents are mixed, split them into separate commits. Use a single commit only in strict exception cases.

### Step 1: Analyze diffs and split commit units

Analyze the changes above and identify groups with **different intents/purposes**.

**You must split when:**
- Different features are added/modified together (for example, feature A + feature B)
- Bug fixes and feature additions are mixed
- Refactoring and behavior changes are mixed
- Configuration changes and code changes are mixed
- Independent modules/components are changed for different reasons
- Multiple independent bugs are fixed together

**A single commit is allowed only when (strictly):**
- Only 1-2 files changed with one clear purpose
- Multiple files are required for one feature (for example, component + style + test)
- The change is minor (for example, typo fixes, formatting only)

**Intent type examples + selection rules:**
- `feat`: add new functionality
- `fix`: fix broken behavior/logic
- `refactor`: improve structure without behavior changes
- `style`: formatting, semicolons, lint-only stylistic changes
- `docs`: documentation-only changes
- `chore`: config/build/dependency/tooling maintenance
- `test`: test-only additions or modifications

**Breaking Change marking (required when applicable):**
Mark breaking changes when backward compatibility is broken:
- API signature changes (parameter add/remove/type change)
- Removal of existing behavior or behavior contract changes
- Config/environment variable format changes
- Required dependency/runtime changes

Use one of these formats:
- Add `!` after type in title: `feat!: remove deprecated login API`
- Add a `BREAKING CHANGE:` line in the body:
  ```
  BREAKING CHANGE: login() parameter contract changed
  ```

**If intent differs, always split.**

`feat` vs `fix` decision checklist (in this order):
- Does it correct broken behavior or incorrect logic? -> `fix`
- Does it add new capability, option, or flow? -> `feat`
- Does behavior stay the same and only structure improve? -> `refactor`
- Is it only config/CI/build/dependency work? -> `chore`
- Is it docs-only with no code behavior change? -> `docs`
- Is it test-only while product behavior stays unchanged? -> `test`
- If still ambiguous, ask the user via AskUserQuestion and decide type based on intent. Prefer `fix`/`refactor`/`chore` over `feat` when uncertain.

### Step 2: Propose commit messages

For each commit, propose using this format:

**Commit N:**
- Files to include: `file1.ts`, `file2.ts`
- Intent: (`feat`/`fix`/`refactor`/...)
- Breaking change: yes/no (if yes, specify what breaks)
- Title (English, <= 50 chars): `feat: add user authentication flow` (use `feat!:` when breaking)
- Body (English, 2-depth bullet list):
  - Key changes
    - Detail 1
    - Detail 2
  - If breaking, add `BREAKING CHANGE: ...`

(Repeat for all proposed commits)

Even for a single commit, follow the same format and propose only **Commit 1**.

Self-validate commit type before finalizing proposal:
- Recheck whether the selected type matches the checklist
- If it is bug fixing, do not label as `feat`
- Include whether tests/docs were updated or intentionally skipped

### Step 3: User confirmation

Use AskUserQuestion to confirm:
- Whether to proceed with the proposed split
- Whether any commit message should be edited
- Whether commits should be merged or split further
- Whether to cancel

### Step 4: Execute commits

Execute commits sequentially:
1. Stage only files for that commit (`git add <files>`)
2. Commit with the approved message
3. Move to the next commit
4. Repeat until all commits are done

Commit message format:
```
Title

- Key changes
  - Detail 1
  - Detail 2
```

**Important:**
- If the user cancels, do not commit.
- If message edits are requested, commit with the edited message.
- If any error occurs during a multi-commit sequence, stop immediately and report it.
- Show final results after all commits complete.

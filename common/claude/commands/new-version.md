---
description: 마지막 태그부터 변경사항 분석 후 semantic versioning에 따라 새 태그 생성 및 push
allowed-tools: Bash(git tag:*), Bash(git log:*), Bash(git describe:*), Bash(git push:*), AskUserQuestion
---

## 현재 버전 정보

**마지막 태그:**
!`git describe --tags --abbrev=0 2>/dev/null || echo "No tags yet"`

**마지막 태그 이후 커밋 수:**
!`git rev-list $(git describe --tags --abbrev=0 2>/dev/null || echo "HEAD~10")..HEAD --count 2>/dev/null || echo "N/A"`

**마지막 태그 이후 변경 내역:**
!`git log $(git describe --tags --abbrev=0 2>/dev/null)..HEAD --oneline 2>/dev/null || git log --oneline -10`

**변경된 파일 목록:**
!`git diff --stat $(git describe --tags --abbrev=0 2>/dev/null)..HEAD 2>/dev/null || git diff --stat HEAD~10..HEAD`

## 작업 지침

### 1단계: 변경사항 분석

위의 커밋 내역을 분석하여 다음을 파악해라:

1. **Breaking Changes (MAJOR):**
   - API 시그니처 변경
   - 기존 기능 제거
   - 호환성 깨는 동작 변경
   - 커밋 메시지에 `BREAKING CHANGE:` 또는 타입 뒤 느낌표(예: `feat!:`) 포함

2. **New Features (MINOR):**
   - `feat:` 타입의 커밋
   - 새로운 기능 추가
   - 새로운 옵션/설정 추가

3. **Bug Fixes & Others (PATCH):**
   - `fix:` 타입의 커밋
   - `refactor:`, `style:`, `docs:`, `chore:`, `test:` 등
   - 기존 기능의 버그 수정
   - 성능 개선

### 2단계: 버전 결정

**Semantic Versioning 규칙 (MAJOR.MINOR.PATCH):**

- **MAJOR** 증가: Breaking change가 있을 때 (예: 1.2.3 → 2.0.0)
- **MINOR** 증가: 새 기능이 추가되었을 때 (예: 1.2.3 → 1.3.0)
- **PATCH** 증가: 버그 수정만 있을 때 (예: 1.2.3 → 1.2.4)

**태그가 없는 경우:**
- 첫 번째 버전으로 `v0.1.0` 또는 `v1.0.0` 제안

**분석 결과를 바탕으로 제안:**
- 현재 버전: `vX.Y.Z`
- 제안 버전: `vA.B.C`
- 버전 증가 이유: (어떤 종류의 변경이 있었는지 설명)

### 3단계: 유저 컨펌

AskUserQuestion 도구를 사용해서 유저에게 다음을 물어봐:
- 제안한 버전으로 태그를 생성할지
- 다른 버전을 원하는지 (직접 입력)
- 취소할지

### 4단계: 태그 생성 및 Push

유저가 승인하면:

1. **태그 생성:**
   ```bash
   git tag -a <version> -m "Release <version>"
   ```

2. **태그 Push:**
   ```bash
   git push origin <version>
   ```

3. **결과 확인:**
   ```bash
   git tag -l --sort=-version:refname | head -5
   ```

**중요:**
- 유저가 취소하면 아무것도 하지 마.
- 유저가 다른 버전을 원하면 해당 버전으로 태그해.
- 태그 생성 전에 같은 태그가 이미 있는지 확인해.
- Push 실패 시 원인을 알려주고 해결 방법을 제안해.

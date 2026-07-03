# 집핀(Jippin) 기여 가이드 — GitHub Flow + gitmoji

본 문서는 **집핀 모노레포(`J511Y/Jippin`)에서 코드를 변경하는 모든 기여자(사람·Paperclip 에이전트)** 가 따라야 하는 브랜치·커밋·PR 정책을 정한다.

근거:
- `AGENTS.md` §4.1 (gitmoji prefix), §4.2 (GitHub Flow), §4.3 (PR 체크리스트), §4.4 (시크릿)
- `AGENTS.md` §5.7 (Paperclip 병렬 에이전트 git worktree 격리)
- `docs/brief/CEO_PROJECT_BRIEF.md` §5 (정책)
- `docs/adr/0001-stack-reevaluation.md` §9.1 (패키지 매니저 봉인)
- CMP-531 (`.gitignore`, `.env.example`, CI 스켈레톤, 본 문서)

본 정책 위반은 CI(`.github/workflows/ci.yml`)에서 자동 실패한다.

---

## 1. 브랜치 전략 — GitHub Flow

- `main` 은 **보호 브랜치**. 직접 푸시 금지. 머지는 PR 경유.
- 새 작업은 **feature 브랜치** 에서 진행한다.
- Paperclip 병렬 에이전트와 여러 사람이 동시에 작업할 때는 **브랜치별 git worktree** 에서만 변경한다.
- 머지 방식: **Squash and merge** 단일 옵션. (gitmoji prefix 가 머지 커밋 메시지에 남는다)

### 1.1 브랜치 이름 규칙

```
<type>/<scope>-<short>
```

| 부분    | 설명                                                                | 예                              |
| ------- | ------------------------------------------------------------------- | ------------------------------- |
| `type`  | 커밋 prefix 와 동일(§2 표). `feat`/`fix`/`docs`/`refactor`/... 9종. | `feat`                          |
| `scope` | 영향 모듈 또는 이슈 키. 영문 소문자 + 숫자 + `-`.                   | `auth` / `cmp-531` / `contracts` |
| `short` | 6~30자 이내 영문 케밥 설명. 한글·공백 금지.                          | `kakao-callback`                |

**예시**

- `feat/auth-kakao-callback`
- `fix/overlay-canvas-flicker`
- `chore/cmp-531-github-flow`
- `docs/adr-0002-cloud-target`
- `refactor/contracts-completion-decision`

**금지**

- `dev`, `develop`, `master`, `release/*` (GitHub Flow 미사용)
- 공백·한글·대문자·`/`가 3개 이상

### 1.2 작업 흐름

1. 루트 체크아웃에서 최신 main 을 확인한다: `git fetch origin`
2. 이슈별 worktree 를 만든다: `git worktree add -b <type>/<scope>-<short> C:\Users\jhyou\2026\jippin-worktrees\<CMP-ID>-<slug> origin/main`
3. worktree 로 이동한다: `cd C:\Users\jhyou\2026\jippin-worktrees\<CMP-ID>-<slug>`
4. 작업 → 작은 단위로 자주 커밋 (`gitmoji` prefix 준수, §2)
5. `git push -u origin <branch>` → GitHub 에서 PR 생성
6. 리뷰 통과 + CI 그린 → **Squash and merge**
7. 머지 후 worktree 와 브랜치 삭제 (`git worktree remove <path>`, `git push origin --delete <branch>`)

### 1.3 병렬 작업 격리 — git worktree 필수

Paperclip 에이전트는 루트 체크아웃(`C:\Users\jhyou\2026\jippin`)에서 직접 브랜치를 바꿔가며 작업하지 않는다. 루트 체크아웃은 coordination/read-only 용도로 두고, 실제 변경·커밋·푸시는 이슈별 worktree 에서 수행한다.

표준 PowerShell 절차:

```powershell
$issue = "CMP-531"
$branch = "chore/cmp-531-github-flow"
$worktree = "C:\Users\jhyou\2026\jippin-worktrees\$issue-github-flow"

New-Item -ItemType Directory -Force -Path C:\Users\jhyou\2026\jippin-worktrees | Out-Null
git fetch origin
git worktree add -b $branch $worktree origin/main
Set-Location $worktree
git status --short --branch
```

기존 브랜치가 원격에만 있으면 원격 브랜치에서 로컬 브랜치를 만들어 worktree 에 붙인다.

```powershell
New-Item -ItemType Directory -Force -Path C:\Users\jhyou\2026\jippin-worktrees | Out-Null
git fetch origin
git worktree add -b chore/cmp-531-github-flow C:\Users\jhyou\2026\jippin-worktrees\CMP-531-github-flow origin/chore/cmp-531-github-flow
```

기존 브랜치가 로컬에 있으면 `-b` 를 쓰지 않는다: `git worktree add <path> <branch>`.

필수 규칙:

- **1 Paperclip 이슈 = 1 브랜치 = 1 worktree.**
- 서로 다른 에이전트가 같은 worktree 를 공유하지 않는다.
- 자식 이슈는 별도 브랜치와 별도 worktree 로 처리한다.
- push/PR 전 `git status --short --branch` 와 `git worktree list` 로 현재 브랜치·경로를 확인한다.
- dirty worktree 는 삭제하지 않는다. 먼저 변경 소유자와 상태를 확인한다.

---

## 2. 커밋 메시지 — gitmoji 컨벤션

AGENTS.md §4.1 의 10개 prefix 만 허용한다. **이 외의 이모지/prefix 는 CI 실패**.

| 이모지 | prefix       | 용도                              |
| ------ | ------------ | --------------------------------- |
| ✨     | `feat:`      | 새 기능                           |
| 🐛     | `fix:`       | 버그 수정                         |
| 📝     | `docs:`      | 문서 (코드 변경 없음)             |
| ♻️     | `refactor:`  | 동작 변화 없는 리팩터             |
| ✅     | `test:`      | 테스트 추가/수정                  |
| 🔧     | `chore:`     | 빌드·설정·도구·CI                |
| 🚀     | `perf:`      | 성능 개선                         |
| 🔒     | `security:`  | 보안 패치 (시크릿 회전 포함)      |
| 🚧     | `wip:`       | 임시 (PR 머지 전 반드시 squash) |
| 🔖     | `release:`   | 릴리스 컷 / `dev`→`main` 승급·백머지 |

### 2.1 형식 — 정규식

CI(`gitmoji-validate` job)와 로컬 git hook(`commit-msg`)은 다음 정규식을 강제한다.

```
^(✨|🐛|📝|♻️|✅|🔧|🚀|🔒|🚧|🔖) (feat|fix|docs|refactor|test|chore|perf|security|wip|release)\(([a-z0-9][a-z0-9-]*)\): .+
```

- 이모지와 prefix 는 **반드시 공백 1개**로 분리.
- `(scope)` 는 영문 소문자/숫자/하이픈. (브랜치 `scope` 와 일치 권장)
- 본문 짧은 설명은 70자 이내 권장. 한글 OK.

### 2.2 예시

✅ 통과
```
✨ feat(auth): 카카오 OAuth 콜백 핸들러 추가
🐛 fix(overlay): SAM2 마스크 경계 깜빡임 수정
📝 docs(adr): ADR-0001 §7 T6 VLM 라우팅 표 보강
♻️ refactor(contracts): CompletionDecision 직렬화 분리
🔒 security(cmp-531): gitleaks 워크플로 추가 (Refs: CMP-531)
🚧 wip(rule): 룰 결정성 회귀 테스트 작성 중
```

❌ 실패 (CI 실패)
```
feat: kakao oauth                       # 이모지 누락
✨feat(auth): ...                       # 이모지·prefix 사이 공백 누락
✨ feature(auth): ...                   # prefix 화이트리스트 위반
🎉 feat(auth): ...                      # 이모지 화이트리스트 위반
✨ feat: 카카오                          # scope 누락
✨ feat(Auth): 카카오                    # scope 대문자
```

### 2.3 본문(body) 권장

- 첫 줄(요약)과 본문 사이에 빈 줄 1줄.
- 본문에는 **WHY**(왜 변경) 만 적는다. WHAT 은 diff 가 말한다.
- 관련 이슈는 본문 끝에 `Refs: CMP-XXX` 또는 `Closes: CMP-XXX`.

---

## 3. PR 체크리스트

PR 본문은 `.github/PULL_REQUEST_TEMPLATE.md` 가 자동으로 채워준다. 머지 전에 모두 체크되어야 한다.

- [ ] (선택) 관련 이슈가 있으면 본문에 식별자 표기 — Paperclip 보드 운용을 중단해 더 이상 필수가 아니다(CI 미강제)
- [ ] 영향 모듈 명시 (`AUTH` / `INPUT` / `MASK` / `AI` / `OVERLAY` / `CHAT` / `FLOW_GUARD` / `RULE` / `REPORT` / `CONTRACTS` / `INFRA` / `DEVOPS` / `SECURITY` / `QA`)
- [ ] 공통 컨트랙트(`packages/contracts/schemas/*.schema.json`) 변경 시 `schema_version` bump 및 TS/Python 바인딩 재생성
- [ ] 비밀번호·키·도면 원본 등 민감 자료 미포함 (시크릿 스캔 CI 통과)
- [ ] 모듈별 dev 명령(`pnpm dev`, `uv run uvicorn ...`) 또는 `docker compose up` 정상 동작
- [ ] (해당 시) `README.md` / `AGENTS.md` / 모듈 README 갱신
- [ ] gitmoji 커밋 메시지 정규식 통과 (`.github/workflows/ci.yml` 의 `gitmoji-validate` job)
- [ ] PR 제목이 `<이모지> <prefix>(<scope>): <설명>` 형식 — `.github/workflows/pr-title-lint.yml` 검증

---

## 4. 시크릿 정책 (AGENTS.md §4.4)

- **실제 값**(Neon 비밀번호, OAuth 시크릿, OpenAI 키 등)은 절대 커밋하지 않는다.
- `.env` 는 `.gitignore` 가 차단한다. **커밋 가능한 파일은 `.env.example` 뿐**.
- `.env.example` 에는 값 자리에 `REPLACE_ME` 또는 형식(예: `sk-REPLACE_ME`)만 둔다.
- 시크릿이 누출되면 **즉시 회전**. PR 본문에 회전 사실 명시.
- `.github/workflows/secret-scan.yml` 가 PR 마다 다음 패턴을 검사한다:
  - Neon: `npg_...`
  - OpenAI: `sk-...`
  - AWS: `AKIA...`
  - Slack: `xoxb-...` `xoxp-...`
  - 일반: 32+ 글자 base64/hex 의심 토큰

---

## 5. 개발 환경 — 패키지 매니저 봉인

ADR-0001 §9.1 봉인. **다른 매니저 사용 금지**.

| 영역                   | 매니저 / 버전     | 명령 예                                  |
| ---------------------- | ----------------- | ---------------------------------------- |
| `apps/web`             | **pnpm 9.x**      | `pnpm install` / `pnpm dev` / `pnpm build` |
| `apps/api`             | **uv ≥ 0.5**      | `uv sync` / `uv run uvicorn ...`          |
| `packages/contracts`   | pnpm 9.x (TS 부분) | `pnpm --filter @jippin/contracts generate` |
| 루트                   | (메타만)          | —                                        |

- Node 버전: `.nvmrc` = `22` (Node 22 LTS).
- Python 버전: `.python-version` = `3.13`.
- 추가 글로벌 패키지 설치 금지. 의존성은 각 앱의 `package.json` / `pyproject.toml` 에 추가.

---

## 6. 신규 기여자 — 첫 PR 5분 가이드

```powershell
# 1) 의존성 (각 앱)
cd apps/web && pnpm install && cd -
cd apps/api && uv sync && cd -

# 2) 정책 위반 자동 차단 (옵션, 의존성 없이 동작하는 git hook)
git config core.hooksPath .githooks
#   → commit-msg 단계에서 tooling/validate_commit_msg.py 가 자동 실행됨.
#   → Python 3.13 만 PATH 에 있으면 됨. Node 의존성 없음.

# 2-1) 커밋 메시지 템플릿 (옵션, 에디터에 gitmoji prefix 힌트 자동 노출)
git config commit.template .gitmessage
#   → 이후 `git commit` (-m 인자 없이) 호출 시 .gitmessage 의 안내가 에디터에 뜸.

# 3) 환경 변수
cp .env.example .env
#   → 실제 값을 채운다. .env 는 절대 커밋되지 않는다.

# 4) 새 브랜치 + 독립 worktree
$issue = "CMP-000"
$branch = "feat/<scope>-<short>"
$worktree = "C:\Users\jhyou\2026\jippin-worktrees\$issue-<short>"
New-Item -ItemType Directory -Force -Path C:\Users\jhyou\2026\jippin-worktrees | Out-Null
git fetch origin
git worktree add -b $branch $worktree origin/main
cd $worktree

# 5) 커밋 (gitmoji prefix 필수)
git add <files>
git commit -m "✨ feat(<scope>): 한 줄 요약"

# 6) push & PR
git push -u origin HEAD
gh pr create --fill
```

---

## 7. 본 문서의 변경 절차

- 본 문서의 §1·§2 (gitmoji prefix·브랜치/worktree 규칙)는 AGENTS.md §4·§5.7 과 **반드시 일치** 한다. 변경은 AGENTS.md 와 동기 PR 로 진행.
- 그 외 절차는 DevOps Lead 가 PR 로 갱신한다.
- 갱신 시 본 PR 도 본 문서의 §2.1 정규식을 통과해야 한다. (자기-적용)

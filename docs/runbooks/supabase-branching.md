# Runbook — Supabase GitHub integration + 브랜치 운영 (CMP-574 인도물)

- 정본 책임자: **DevOps Lead** · **SRE** 리뷰
- 관련: CMP-572 (Supabase 트랙 총괄), CMP-573 (Supabase 전환 ADR — Pending), CMP-574 (본 런북), CMP-575 (DB migration), CMP-576 (Auth), CMP-577 (Web)
- 대체 대상: `docs/runbooks/neon-branches.md` §1~§3 (Neon branch 트리/운영). Neon 런북은 §5 시크릿 회전 패턴만 참조 자료로 유지된다.
- 정책 정본: `docs/adr/0004-supabase-transition.md` (CMP-573, Pending). 본 런북은 정책이 정해진 뒤 운영 절차만 담는다.
- 봉인 범위: 본 런북은 **GitHub branching ↔ Supabase branch 매핑·preview 정책·CI 대체 순서** 만 봉인한다. Auth/DB/Web 트랙의 실제 마이그레이션 절차는 각 트랙 런북에 위임한다.

---

## 0. TL;DR (CMP-574 결정 요약)

| 항목 | 결정 |
|---|---|
| Supabase 채택 범위 (본 런북 기준) | **DB + Auth**. Storage/Realtime/Edge Functions 는 본 PR 비활성. |
| Supabase project ref 입력 시점 | **사용자가 콘솔에서 발급한 뒤 별도 PR / GitHub Secret 으로 주입**. 본 PR 의 `supabase/config.toml` 은 placeholder. |
| Persistent (long-lived) Supabase branch | **`production`** (default), **`staging`**, **`development`** 3개. |
| GitHub branch ↔ Supabase branch 매핑 | `main` → `production`, `dev` → `development`. `staging` 은 Supabase 콘솔에서 수동 promote (GitHub 측 트리거 없음). |
| PR preview Supabase branch | `feature/*`, `docs/*`, `chore/*`, `fix/*`, `refactor/*` PR → Supabase Automatic Branching 이 ephemeral preview branch 생성. **PR base 가 `dev` 또는 `main` 일 때만**. |
| Automatic branching 트리거 범위 | **"Supabase changes only"** — `supabase/**` 또는 `supabase/migrations/**` 변경이 있는 PR 에만 preview branch 생성. (콘솔 토글 1회 설정) |
| Preview branch 정리 | PR closed → Supabase integration 이 자동 삭제. 14일 이상 머지/닫힘 없는 PR 은 콘솔 정책으로 만료 (§5). |
| 기존 Neon workflow 처리 | **단계 0~3 의 단계적 deprecation**. 본 PR(단계 0)은 Neon workflow 를 **유지·격리**만 한다. |
| GitHub required check | 전환 완료 시점에 **`ci-status`** (CMP-574 변경 없음) + Supabase integration 의 preview check (콘솔/실행 후 실제 context 이름을 확인해 등록 — Supabase 공식 예시는 **`Supabase Preview`**, 콘솔 옵션·버전에 따라 달라질 수 있음). path-filter deadlock 회피 패턴은 §6.3. 본 PR 에서는 변경 없음. |
| Identity linking 정책 (CEO 결정 CMP-572) | **Automatic linking 영구 금지** (§7.1.1 콘솔 토글 + DB 트리거 가드 봉인). **Manual linking 우선** — `enable_manual_linking = true` 봉인 (§7.1.2). Anonymous → OAuth upgrade 는 manual linking 흐름으로만 (§7.1.3). |
| 시크릿 추가 (사용자 작업) | `SUPABASE_ACCESS_TOKEN` (org/personal), `SUPABASE_PROJECT_REF_PROD`, `SUPABASE_PROJECT_REF_DEV`, `SUPABASE_DB_PASSWORD_*` — §3.2 참조. |

본 런북은 **사용자가 콘솔 작업을 수행하면 그 뒤 곧바로 따라할 수 있는 체크리스트** 를 §3 에 둔다.

---

## 1. Supabase 브랜치 모델 (기대 상태)

```
supabase project (jippin)
└── production            ← default branch, GitHub `main` 과 동기화
    ├── staging           ← persistent, parent: production (사람만 수동 promote)
    └── development       ← persistent, parent: production, GitHub `dev` 과 동기화
        ├── preview/pr-1234   (ephemeral, parent: development, PR base=dev)
        ├── preview/pr-1235   (ephemeral, parent: development)
        └── preview/pr-1236   (ephemeral, parent: production, PR base=main)  # hotfix PR
```

운영 원칙:

- **Persistent branch 3개로 봉인**. 임의로 4번째 persistent branch 를 만들지 않는다 (비용·동기화 사고 방지). 작업자별 격리 DB 가 필요하면 **Supabase CLI 로컬 (`supabase start`)** 또는 작업자별 personal preview project 를 사용한다.
- `staging` 은 Supabase 측에서만 promote 한다. GitHub `staging` 브랜치를 만들지 않는다 (CMP-573 ADR 봉인 시 재확인).
- Preview branch parent 는 PR base 와 일치한다 — `dev` PR → `development` 의 자식, `main` PR (hotfix) → `production` 의 자식. Supabase Automatic Branching 의 기본 동작과 같다.
- 거꾸로 흐르는 데이터 복제 (e.g. production → development 시드 갱신) 는 본 런북 비범위. Supabase 콘솔 `Restore` 기능 또는 별도 DB 트랙이 다룬다.

---

## 2. GitHub ↔ Supabase 매핑 봉인

| GitHub branch | Supabase branch | APP_ENV | 비고 |
|---|---|---|---|
| `main` | `production` | `production` | release-migrate 가 `main` push 에서 production migration 적용 (Supabase integration 이 처리) |
| `dev` | `development` | `development` | `dev` push 에서 development migration 적용 |
| `feature/*`, `fix/*`, `refactor/*`, `chore/*`, `docs/*` (PR base=`dev`) | `preview/pr-N` (parent=`development`) | `test` (CI) / `development` (preview app) | Automatic Branching, PR closed 시 삭제 |
| `hotfix/*`, anything (PR base=`main`) | `preview/pr-N` (parent=`production`) | `test` | 운영 hotfix 경로. **드물게만 사용**. |
| (없음) | `staging` | `staging` | Supabase 콘솔에서 수동 promote 만. GitHub 측 트리거 없음. |

**코드 분기는 만들지 않는다** — 매핑은 환경별 시크릿(`SUPABASE_URL_*`, `SUPABASE_DB_URL_*`) 값으로만 한다 (12-factor). `apps/api/src/config.py::ALLOWED_APP_ENVS = {"development","test","staging","production"}` 는 CMP-538 봉인 유지.

본 매핑은 봉인이다. 변경하려면 ADR 을 새로 발행하고 본 런북·`AGENTS.md`·`apps/api/.env.example`·`apps/web/.env.example` 를 같은 PR 에서 갱신한다.

---

## 3. 사용자 콘솔 작업 + 에이전트 후속 작업 체크리스트

본 절은 **사용자가 직접 수행할 항목** 과 **그 뒤 에이전트(또는 사용자) 가 자동으로 처리할 수 있는 항목** 을 분리한다. 에이전트는 절대 사용자 항목을 대행하지 않는다.

### 3.1 사용자 콘솔 작업 (Supabase Console + GitHub Settings)

순서가 중요하다. 4 → 5 사이에는 본 PR(CMP-574) 머지가 끼어야 한다 (integration 이 `supabase/config.toml` 을 보고 동작).

- [ ] **U1.** https://supabase.com/dashboard 에서 org `jippin` (또는 기존) 선택, `New project` → name `jippin`, region `Northeast Asia (Seoul, ap-northeast-2)`, plan `Pro` (branching 사용을 위해 Free 가 아닌 plan 필요), DB password 발급.
- [ ] **U2.** 발급된 값들을 1Password vault `집핀 / Supabase` 에 저장:
  - `SUPABASE_URL` (project API URL — `https://<ref>.supabase.co`)
  - `SUPABASE_ANON_KEY` (public anon key)
  - `SUPABASE_SERVICE_ROLE_KEY` (서버 전용)
  - `SUPABASE_DB_PASSWORD` (DB password)
  - `SUPABASE_DB_URL_DIRECT` (Connection Settings → Direct connection)
  - `SUPABASE_DB_URL_POOLER` (Transaction pooler)
  - `SUPABASE_PROJECT_REF` (project ref, 20자 lowercase)
- [ ] **U3.** Supabase Console → Project → `Branching` 탭에서 **Enable branching** 토글 ON. Persistent branch 추가:
  - `staging` (parent: `production`, persistent)
  - `development` (parent: `production`, persistent)
- [ ] **U4.** Supabase Console → Branching → **GitHub Integration** → `Connect repository` → `J511Y/Jippin` 선택. 옵션 설정:
  - Production branch: `main`
  - Persistent branch mapping: `dev` ↔ `development`
  - **Working directory: `.`** — Supabase GitHub integration 의 working directory 는 **`supabase/` 폴더를 포함하는 부모 경로**다. 본 모노레포는 `supabase/` 가 repo root 에 있으므로 `.` 로 입력한다. (Supabase 공식 안내: https://supabase.com/docs/guides/deployment/branching/github-integration#set-the-working-directory)
  - **Automatic branching: "Supabase changes only"** (Settings → Branching 의 토글; 이 옵션은 `supabase/**` 변경이 있는 PR 에만 preview branch 를 만든다)
  - **Automatic linking 가드 사전 확인** (§7.1.1) — Supabase 는 default 로 같은 verified email OAuth identity 를 자동 link 한다. CEO 결정 (CMP-572) 봉인은 **automatic linking 영구 금지**이므로, 본 단계에서 콘솔의 "Allow Same Email for Multiple Providers" 토글 위치를 확인 (실제 ON 작업은 CMP-576 머지 직전 §7.1.1 G1 게이트가 한다). 본 PR 은 토글을 켜지 않는다 — 콘솔 가드 작업 시점은 CMP-576 트랙.
- [ ] **U5.** GitHub Settings → Secrets and variables → Actions 에 다음 추가 (값은 1Password 에서 복붙):
  - Secret: `SUPABASE_ACCESS_TOKEN` (Personal Access Token; Supabase 콘솔 Account → Access Tokens)
  - Secret: `SUPABASE_DB_PASSWORD_PROD`
  - Secret: `SUPABASE_DB_PASSWORD_DEV` (development persistent branch 용 DB password — production 과 별도)
  - Variable: `SUPABASE_PROJECT_REF_PROD` (production project ref; `supabase projects list` 의 Reference ID)
  - Variable: `SUPABASE_PROJECT_REF_DEV` (**development persistent branch 의 BRANCH PROJECT ID — production ref 와 별도 값**. `supabase --experimental branches list` 의 `BRANCH PROJECT ID` 컬럼 값을 입력한다. Supabase 공식: https://supabase.com/docs/guides/deployment/branching/configuration#remote-specific-configuration)
- [ ] **U6.** GitHub Settings → Branches → `main` / `dev` 보호 규칙 확인. **본 PR 시점에는 required check 변경 없음** (`ci-status` 만 required). Supabase preview check 는 §6 단계 2 에서 wrapper (§6.3) 로 추가.

### 3.2 에이전트(또는 사용자) 후속 작업 — CMP-574 PR 머지 후

- [ ] **A1.** 사용자가 `SUPABASE_PROJECT_REF_PROD` 값을 별도 PR(또는 `chore/CMP-574-project-ref` 후속 브랜치)로 `supabase/config.toml` 의 `project_id` 에 채운다. **이 값은 비밀이 아니므로 커밋 가능.** 단 본 PR 에서는 placeholder.
- [ ] **A1.1** 같은 PR 에서 `[remotes.development].project_id` 를 `SUPABASE_PROJECT_REF_DEV` (development persistent branch 의 BRANCH PROJECT ID, U5 참고) 값으로 채운다. 본 절이 빠지면 `supabase --remote development db diff/push` 가 production 으로 잘못 흐른다. staging persistent branch 를 도입할 때 `[remotes.staging]` 도 같은 패턴으로 추가.
- [ ] **A2.** CMP-575 (DB 트랙) 가 Alembic → SQL migration 변환 결과를 `supabase/migrations/` 에 채운다.
- [ ] **A3.** CMP-576 (Auth 트랙) 이 `supabase/config.toml` 의 `[auth.external.*]` 를 켜고 **같은 PR 에서 `[auth].enable_signup` 글로벌 gate 를 `true` 로 함께 바꾼다** (글로벌 gate 가 false 면 OAuth signup 도 막힘). `[auth.email].enable_signup` 은 영구 false 유지. CMP-577 트랙이 `[auth].enable_anonymous_sign_ins=true` 로 전환하며 §7.1.3 PoC 절차 (A5) 를 함께 수행.
- [ ] **A4.** §6 단계 1~3 에 따라 Neon workflow 를 단계적으로 제거하고 Supabase integration 으로 대체한다. 단계 2 PR 은 §6.3 wrapper workflow (`.github/workflows/supabase-status.yml`) 를 추가하고 §6.3.1 의 컨텍스트 식별 절차로 polling 대상을 박는다.

---

## 4. Automatic Branching 동작 설명 (운영자 이해용)

Supabase GitHub integration 의 Automatic Branching 은 다음과 같이 동작한다 (CMP-574 시점 공식 문서 기준 요약 — Supabase 가 동작을 변경할 수 있으므로 §8 참고 링크로 정본 확인):

1. PR opened/reopened/synchronize 이벤트가 GitHub → Supabase 로 webhook.
2. PR base 가 persistent branch 매핑 안에 들어가는지 확인 (`main` 또는 `dev`).
3. PR 의 변경 파일 중 `supabase/**` 가 있는지 확인 (Automatic branching: "Supabase changes only" 모드).
4. 해당 PR 용 ephemeral branch `preview/pr-N-<slug>` 를 parent branch (`production` 또는 `development`) 에서 fork.
5. `supabase/migrations/*.sql` 을 timestamp 순으로 preview branch 에 적용.
6. PR 코멘트로 preview branch 의 connection 정보를 게시 (anon key, DB URL).
7. PR closed → preview branch 자동 삭제.

집핀에서 의도적으로 활성화하지 않는 옵션:

- **"Branch all PRs"** — 모든 PR 에 preview 생성. 비용/quota 폭증 위험. "Supabase changes only" 로 제한.
- **Persistent preview branch (수동)** — staging/development 외 4번째 persistent 를 만들지 않는다 (§1 원칙).

---

## 5. 비용/Quota/정리 정책

- **Pro plan branching quota**: 동시 활성 branch 수 ≤ 50 (2026-05 기준 — 변경될 수 있음, §8 링크 확인). Persistent 3개 + ephemeral preview ≤ 47.
- **Idle preview 자동 정리**: Supabase 가 PR closed/merged 시 자동 삭제. **에이전트나 운영자가 직접 SQL 로 삭제하지 않는다.**
- **만료 PR**: 14일 이상 활동 없는 PR 의 preview branch 는 분기별로 운영자가 수동 정리. Supabase 콘솔 → Branches → Filter `Inactive > 14d` → 일괄 삭제. **closed/merged 가 아닌 stale PR 만 대상**. (Supabase 콘솔 UI 가 변경되면 §8 링크 확인.)
- **비용 모니터링**: Supabase Console → Settings → Billing → Branching usage 를 월말 운영 리뷰에 포함. spike 발견 시 Automatic branching 토글을 일시 OFF 후 원인 PR 확인.
- **Production migration 적용 시 다운타임**: Supabase integration 의 `main` push 트리거는 production DB 에 직접 migration 을 적용한다. **breaking schema change 는 §7 의 운영 가드 참고.**

---

## 6. Neon workflow 단계적 deprecation 순서 (봉인)

본 PR(CMP-574) 시점에 Neon workflow 를 **즉시 제거하지 않는다**. ADR-0004 (CMP-573) 가 Accepted 되기 전에 신호를 끊으면 회복 경로가 사라지기 때문이다. 다음 4단계로 분리한다.

| 단계 | 트리거 | 작업 범위 | 책임 이슈 |
|---|---|---|---|
| **단계 0 (본 PR — CMP-574)** | 본 PR 머지 | `supabase/` 스캐폴드 + 본 런북 추가. **Neon workflow 무변경.** | CMP-574 |
| **단계 1** | CMP-573 ADR-0004 Accepted | Neon workflow 에 `if: vars.SUPABASE_BRANCHING_LIVE != 'true'` 게이트 추가. GitHub variable 토글 1개로 Neon ↔ Supabase 흐름 전환 가능. 사용자가 §3.1 의 U1~U5 완료 후 토글 ON. | CMP-574 후속 또는 CMP-573 머지 PR |
| **단계 2** | 단계 1 토글 ON + Supabase production 머지 1회 성공 | `.github/workflows/supabase-status.yml` wrapper workflow 를 추가 (§6.3) — Supabase integration 의 실제 check context (§6.3.1 식별 절차로 확정) 를 polling 하고 `supabase/**` 무관 PR 에서는 succeed. GitHub 브랜치 보호 required check 에 **`supabase-status`** wrapper 만 추가 (`ci-status` 유지). `.github/workflows/ci.yml::migrate-check` job 의 `NEON_TEST_DATABASE_URL` 의존을 제거하고 본 job 을 skip 처리 (또는 Supabase preview branch URL 로 전환). | CMP-574 후속 또는 CMP-575 머지 PR |
| **단계 3** | 단계 2 후 2주간 사고 없음 | `.github/workflows/neon-pr-branch.yml` 삭제. `.github/workflows/deploy.yml::release-migrate` 의 Neon DATABASE_URL 의존 삭제. `docs/runbooks/neon-branches.md` 를 archive 폴더로 이동 (`docs/runbooks/_archive/`). | 별도 후속 이슈 (CMP-574 가 만들거나 DevOps Lead 가 발주) |

**규칙**: 단계 N 의 작업은 단계 N-1 이 운영적으로 통과한 뒤에만 시작한다. 단계 1~3 의 PR 본문 머리에 **단계 N: Neon→Supabase deprecation** 라벨을 명시한다.

### 6.1 단계 1 게이트 (참고 스니펫 — 본 PR 적용 대상 아님)

단계 1 PR 에서 `.github/workflows/neon-pr-branch.yml` 의 `create_neon_branch` / `delete_neon_branch` job `if:` 절에 다음을 추가한다 (예시):

```yaml
if: |
  vars.SUPABASE_BRANCHING_LIVE != 'true' &&
  github.event.pull_request.head.repo.full_name == github.repository &&
  github.event_name == 'pull_request' && (
    github.event.action == 'synchronize' ||
    github.event.action == 'opened' ||
    github.event.action == 'reopened'
  )
```

같은 PR 에서 `.github/workflows/ci.yml::migrate-check` 의 detect 단계에 `vars.SUPABASE_BRANCHING_LIVE` 분기를 추가한다.

### 6.2 GitHub required check 운영 방식

본 PR 시점에는 **required check 변경 없음** — `ci-status` (집계 메타 게이트) 만 유지.

| 단계 | 필수 check 목록 | 비고 |
|---|---|---|
| 단계 0~1 | `ci-status` | 현재 상태. |
| 단계 2 | `ci-status`, `supabase-status` (wrapper) | wrapper 이름은 §6.3 가 정의. 실제 Supabase integration check 이름은 §6.3.1 의 컨텍스트 식별 절차로 확정. |
| 단계 3 | `ci-status`, `supabase-status` | Neon workflow 제거 후에도 동일. `ci-status` 안의 `migrate-check` job 은 빈 skeleton 으로 둘지 삭제할지 단계 3 PR 에서 결정. |

**왜 Supabase preview check 를 required 로 두는가**: production/development 매핑 PR 이 migration 깨진 채 머지되면 Supabase 가 `main`/`dev` push 에서 production/development DB 에 직접 적용하기 때문. preview branch 에서 미리 잡아야 운영 사고를 막는다.

### 6.3 path-filter deadlock 회피 (wrapper workflow 패턴)

**문제.** Automatic branching 을 "Supabase changes only" 로 제한하면 `supabase/**` 를 안 건드린 PR 에는 integration 이 만든 preview check 가 아예 나타나지 않는다. 이 상태에서 같은 context 를 GitHub branch protection 의 required check 로 등록하면 머지 deadlock 이 발생한다 (PR 이 미해결 required check 를 영원히 기다림).

**해결.** 단일 wrapper check (`supabase-status`) 를 항상 실행되는 workflow 로 두고, branch protection 은 wrapper 만 required 로 등록한다. wrapper 가 PR 안의 변경 파일을 보고 결정한다:

- `supabase/**` 변경 없음 → wrapper 자체로 succeed (skip 의미).
- `supabase/**` 변경 있음 → 실제 Supabase integration check 의 결과를 기다린 뒤 그 결과를 그대로 wrapper 결과로 반영. `gh api` 폴링 또는 `wait-on-check-action` 류 액션을 사용. timeout 발생 시 fail.

이는 본 PR 의 `ci-status` 메타 게이트와 동일한 패턴이다 (`ci-status` 가 하위 jobs 의 결과를 집계해 단일 required check 를 제공).

**적용 시점.** 단계 2 PR (CMP-575 후속 또는 별도 후속 이슈) 이 `.github/workflows/supabase-status.yml` skeleton 을 추가하고 branch protection 을 갱신한다. 본 PR (단계 0) 은 wrapper workflow 를 만들지 않는다.

#### 6.3.1 실제 Supabase integration check context 식별 절차

Supabase 가 integration check context 이름을 콘솔 옵션·버전에 따라 변경할 수 있으므로 단계 2 PR 머지 직전에 실제 이름을 확정한다.

1. 단계 1 토글 ON 후 `supabase/**` 를 변경하는 dummy PR 을 1개 연다.
2. PR check 목록에 나타나는 Supabase 측 check 의 context 이름을 기록한다 (예: `Supabase Preview`, `Supabase / Preview`, `Supabase Migrations` 등).
3. 그 이름을 §6.3 wrapper workflow 의 polling 대상으로 박는다.
4. branch protection 의 required check 는 wrapper (`supabase-status`) 만 등록한다 — Supabase 측 context 를 직접 required 로 등록하지 않는다 (path-filter deadlock 회피).

`Supabase Preview` 가 2026-05 기준 Supabase 공식 예시 context 이름이지만, 본 런북은 **wrapper 가 단계 2 PR 시점의 실제 이름을 polling 한다**는 운영 절차만 봉인한다.

---

## 7. 운영 가드 — breaking schema change

Supabase integration 은 `main` push 시 production DB 에 migration 을 직접 적용한다. 다음 가드를 운영에 적용한다 (CMP-575 DB 트랙이 정본화 예정).

- breaking change (drop column, rename, type narrow 등) 는 **반드시 2-step migration** 으로 PR 분리한다. 1단계: 새 컬럼 추가 + dual-write, 2단계: 구 컬럼 drop.
- 대규모 backfill SQL 은 migration 안에 넣지 않는다. 별도 job 또는 1회성 SQL 작업으로 분리.
- production migration 실패 시 회복: Supabase 콘솔 → Branches → `production` → Restore 또는 즉시 hotfix PR (`main` base) 발행.

세부 가드와 회복 절차는 CMP-575 가 정본화한다. 본 런북은 게이트만 명시.

### 7.1 Identity linking 가드 (CEO 결정 CMP-572 봉인)

> **Policy guard (영구 봉인).** Email-based automatic identity linking is disabled by policy (ADR-0003 영속화 + CEO CMP-572). Use `supabase.auth.linkIdentity()` only.

CEO 결정 (CMP-572, 2026-06-01): **MVP 는 Manual identity linking 우선, Automatic identity linking 금지.** ADR-0003 의 자동 병합 금지 원칙은 유지된다.

집핀의 linking 정책은 두 흐름으로 분리한다.

| 정책 | 동작 | config.toml 봉인 값 | 가드 책임 |
|---|---|---|---|
| **Automatic linking** (Supabase default) | 같은 verified email 의 OAuth identity 를 한 user 로 자동 병합 | `config.toml` 토글 없음 — **§7.1.1 가드로 봉인** | 콘솔 + DB 트리거 |
| **Manual linking** (CEO 정책) | 사용자가 명시적으로 "계정 통합" 또는 "anonymous → OAuth upgrade" 를 요청한 경우 한 user 에 identity 추가 | `enable_manual_linking = true` (§7.1.2 사유) | 어플리케이션 흐름 + 감사 로그 |

두 정책은 토글 하나로 통제되지 않는다. **§7.1.1 의 자동 linking 가드를 통과하지 않은 상태로는 OAuth provider 를 `enabled = true` 로 켤 수 없다** (PR 머지 금지).

#### 7.1.1 Automatic linking 가드 (MUST — 영구 봉인)

Supabase Auth 는 default 로 같은 verified email 을 가진 서로 다른 OAuth identity 를 한 user 로 자동 link 한다 (`auth.identities` 의 email 매칭). 이 동작은 `supabase/config.toml` 토글로 끌 수 없다. 따라서 다음 2-layer 가드가 필요하다.

| 게이트 | 결정/검증 | 책임 | 본 PR 적용 |
|---|---|---|---|
| G1. Supabase 콘솔 → Authentication → Sign In/Up → **"Allow Same Email for Multiple Providers"** (혹은 동등 토글이 이름이 바뀐 옵션) 를 **ON** 으로 설정. ON 이면 같은 이메일을 다른 provider 가 가입해도 별개 user 로 둔다. 토글 위치는 Supabase 가 UI 를 변경할 수 있으므로 §8 의 공식 링크 확인. | 사용자 (콘솔 작업) — CMP-576 PR 머지 직전 | 본 PR 머지 후 |
| G2. **DB 트리거 fallback** — 콘솔 토글이 사라지거나 우회되어도 `auth.users` row 에 같은 verified email 이 두 번 생기면 두 번째 signup 을 reject 하는 BEFORE INSERT 트리거를 CMP-576 가 정본화. `supabase/migrations/<timestamp>_block_auto_email_linking.sql` 로 커밋. | CMP-576 (DB 트리거 SQL) | CMP-576 PR |
| G3. PoC — Google + Kakao 같은 verified email 로 두 번 가입했을 때 두 user row 가 분리되는지 staging branch 에서 확인. 결과를 CMP-576 PR 본문에 캡처/로그 첨부. | CMP-576 (PoC) | CMP-576 PR |

G1~G3 중 1개라도 빠진 상태에서 `[auth.external.*] enabled = true` 로 켜는 PR 은 **머지 금지** — Web/Auth required check (단계 2) 에서 명시적으로 막는다 (CMP-577/CMP-576 후속).

#### 7.1.2 Manual linking 활성화 (CEO 결정 봉인)

`supabase/config.toml` 의 `enable_manual_linking = true` 가 봉인 값이다. 사유:

- 본 토글이 false 이면 Supabase 의 `auth.linkIdentity()` API 가 작동하지 않아 anonymous → OAuth upgrade (§7.1.3) 가 막힌다.
- 본 토글은 **자동 linking 동작과 독립**이다. true 로 둬도 §7.1.1 의 자동 linking 가드와 충돌하지 않는다 (자동 linking 은 Supabase 내부 매칭, manual linking 은 명시적 API 호출).

운영 가드:

| 가드 | 내용 | 책임 |
|---|---|---|
| M1. `linkIdentity()` 호출은 **현재 세션 user 의 명시적 동의 UI** 뒤에서만 한다. 자동 호출 금지. | CMP-577 (Web) |
| M2. linking 성공 시 `audit_log` 또는 동등한 감사 테이블에 `kind=auth.identity_linked, actor=user_id, payload=provider+identity_id` 를 남긴다. | CMP-576/CMP-575 |
| M3. linking 취소 (`unlinkIdentity()`) 도 동일하게 감사 로그를 남기고 비활성 흐름을 차단할 수 있게 한다. | CMP-577 |

본 PR (CMP-574, 단계 0) 은 토글만 봉인하고, 위 M1~M3 의 실제 코드/감사 SQL 은 CMP-576/CMP-577 트랙이 정본화한다.

#### 7.1.3 Anonymous → OAuth upgrade 절차

집핀 비회원 사전검토는 Supabase anonymous user (`is_anonymous=true`) 로 식별된다 (AGENTS.md §4.7, ADR-0003 supersede 예정 정책). 사용자가 결제·요청 시점에 OAuth 로 전환하면 anonymous user 의 데이터를 잃지 않도록 manual linking 으로 identity 를 추가한다.

| 단계 | 동작 | 책임 |
|---|---|---|
| A1. anonymous sign-in (`supabase.auth.signInAnonymously()`) 으로 user row 생성, 비회원 사전검토 데이터를 본 user 에 귀속. | CMP-577 |
| A2. 사용자가 "로그인/가입" 누르면 OAuth provider 로 redirect — 단 anonymous session 을 유지한 채 `linkIdentity({ provider })` 호출. 새 user 가 만들어지면 안 된다 (`enable_manual_linking = true` 가 전제). | CMP-577 |
| A3. callback 에서 linked identity 가 성공적으로 추가됐는지, anonymous user 의 `is_anonymous` flag 가 false 로 전환됐는지 검증. 실패 시 anonymous session 유지 + 사용자 에러 표시. | CMP-577 |
| A4. **자동 병합 충돌 케이스** — anonymous user 의 OAuth identity 가 이미 다른 permanent user 의 verified email 과 같으면 §7.1.1 의 G1 가드에 의해 자동 link 가 일어나지 않는다. 본 케이스는 "기존 계정으로 로그인" 안내 UI 로 처리. 두 계정 병합은 별도 "계정 통합" 명시 흐름. | CMP-577 |
| A5. PoC — staging branch 에서 anonymous → Google upgrade, anonymous → Kakao upgrade, 동일 email 충돌 케이스 3가지 시나리오 검증 로그를 CMP-577 PR 본문에 첨부. | CMP-577 |

위 5단계 중 A1~A4 가 코드에 들어오는 PR (CMP-577) 머지 전까지 `enable_anonymous_sign_ins = true` 로 켜지 않는다. 본 PR 시점에는 `enable_anonymous_sign_ins = false` 유지.

---

## 8. 시크릿 회전 정책

본 런북은 정책만, 실제 회전 절차는 별도 런북(`supabase-credential-rotation.md`, 단계 1 또는 CMP-573 머지와 함께 발행 예정)을 참조한다.

| 시크릿 | 정기 회전 | compromise 의심 시 | 비고 |
|---|---|---|---|
| `SUPABASE_SERVICE_ROLE_KEY` | 90일 | **즉시** + audit | 서버 전용. 절대 클라이언트 노출 금지. |
| `SUPABASE_ACCESS_TOKEN` (PAT) | 180일 | 즉시 | GitHub Actions 가 Supabase API 호출용. CI 외 사용 금지. |
| `SUPABASE_DB_PASSWORD_*` | 90일 (prod), 180일 (dev) | 즉시 | Supabase 콘솔 → Settings → Database → Reset password. |
| `SUPABASE_ANON_KEY` | 회전 불필요 (public) | rotate only on JWT secret rotation | publishable. |
| OAuth client secret (Google/Kakao/Naver) | provider 권장 주기 | 즉시 | CMP-576 트랙. |

**필수 self-check**:

```powershell
# 본 레포 트리에서 Supabase 평문 비밀번호/키 패턴이 없는지 확인. 결과는 반드시 0건.
git grep -nE "supabase\.co.*password|sbp_[A-Za-z0-9]{40,}" -- ":(exclude)*/node_modules/*" ":(exclude)*/.venv/*"
git grep -nE "eyJhbGciOi[A-Za-z0-9._-]{40,}" -- ":(exclude)*/node_modules/*" ":(exclude)*/.venv/*"  # JWT-like
```

---

## 9. 검증 (본 PR 머지 전 self-check)

`AGENTS.md` 와 본 이슈의 "테스트/검증" 절을 만족하기 위한 self-check:

```powershell
# 1) supabase 스캐폴드가 들어왔다 (config.toml, .gitkeep 2개).
git ls-files supabase/

# 2) Neon 흔적은 본 PR 에서 건드리지 않았다.
git diff origin/dev...HEAD -- .github/workflows/neon-pr-branch.yml .github/workflows/ci.yml .github/workflows/deploy.yml docs/runbooks/neon-branches.md
# → 위 명령의 출력은 빈 줄이어야 한다 (단계 0 의 봉인 — Neon 무변경).

# 3) 평문 시크릿이 들어가지 않았다.
git grep -nE "sbp_[A-Za-z0-9]{40,}" supabase/ docs/
git grep -nE "supabase\.co.*[A-Za-z0-9]{40,}.*password" supabase/ docs/
# → 두 명령 모두 결과 0건.

# 4) 본 PR 의 placeholder 가 정확히 placeholder 다.
git grep -n "placeholder" supabase/config.toml
# → 2건: project_id (jippin-placeholder) + [remotes.development].project_id
#       (jippin-development-placeholder).

# 4.1) [remotes.development] 선언이 존재한다 (A1.1 후속에서 실제 BRANCH PROJECT ID
#      로 교체).
git grep -n "^\[remotes\.development\]" supabase/config.toml
# → 정확히 1건.

# 5) 가입 게이트 봉인 — 단계 0 시점 모두 false. CMP-576/CMP-577 이 글로벌만 true 로
#    바꾸고 `[auth.email]/[auth.sms]` 는 영구 false.
git grep -n "enable_signup" supabase/config.toml
# → [auth] / [auth.email] / [auth.sms] 3건, 본 PR 시점 모두 false.

# 6) Identity linking 봉인 (CEO 결정 CMP-572):
#     - `enable_manual_linking = true` (MVP manual linking 우선 — §7.1.2)
#     - `enable_anonymous_sign_ins = false` (CMP-577 PoC 후 활성화 — §7.1.3 A5)
#    Automatic linking 가드 (§7.1.1 G1/G2/G3) 는 본 토글로 통제되지 않는다 — 콘솔 + DB 트리거.
git grep -nE "enable_manual_linking|enable_anonymous_sign_ins" supabase/config.toml
# → enable_manual_linking=true, enable_anonymous_sign_ins=false.

# 7) disabled OAuth provider 의 client_id/secret 이 빈 문자열 (env() 미해석 fallback).
git grep -nE 'client_id = ""' supabase/config.toml
# → google, kakao 2건.
```

---

## 10. 비범위 (본 런북이 다루지 않는 것)

- Alembic → Supabase SQL migration 변환 — **CMP-575** 가 정본.
- Auth provider PoC (Anonymous, Google, Kakao, Naver custom OIDC) — **CMP-576** 가 정본.
- Next.js Supabase Auth client/session adapter — **CMP-577** 가 정본.
- Supabase Storage 전환 (R2 → Storage) — 별도 ADR.
- Supabase Realtime / Edge Functions 도입 — 별도 ADR.
- Supabase 시크릿 회전 자동화 — Security Lead 후속.

---

## 11. 참고

- Supabase Branching: https://supabase.com/docs/guides/deployment/branching
- Supabase GitHub Integration: https://supabase.com/docs/guides/deployment/branching#github-integration
- Supabase CLI config.toml: https://supabase.com/docs/guides/cli/config
- Supabase Identity Linking (CMP-576 참고): https://supabase.com/docs/guides/auth/auth-identity-linking
- `docs/adr/0001-stack-reevaluation.md` §4 (현재 Neon 결정 — CMP-573 ADR-0004 가 supersede 예정)
- `docs/adr/0003-anon-user-and-sso.md` (Anonymous + SSO 정책 — CMP-573 가 supersede 예정)
- `docs/runbooks/neon-branches.md` (현 Neon 운영 — 단계 3 에서 archive)
- `apps/api/src/config.py::ALLOWED_APP_ENVS` (APP_ENV 봉인, CMP-538)
- `AGENTS.md` §4.4 (APP_ENV ↔ DB branch 봉인 — 본 런북이 §2 에서 supersede)
- `AGENTS.md` §5.8 (UTF-8 인코딩 규칙)

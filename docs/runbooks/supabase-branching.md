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
  - **Deploy to production / production migrations 토글 ON** — Supabase GitHub integration 은 default 로 PR preview/migration 만 수행하고 `main` push 시 production branch 에 migration 을 적용하지 않을 수 있다. 콘솔에서 **production 배포(또는 production migrations) 토글**을 명시적으로 ON 으로 둔다. 라벨은 Supabase UI 버전에 따라 달라질 수 있으므로 단정하지 않으며, 실제 동작 검증은 **U7** (production deploy toggle 검증) 으로 봉인한다. **본 토글이 OFF 인 상태에서 §6 단계 3 (Neon `release-migrate` 제거) 을 진행하면 production migration 경로가 끊긴다.**
  - **Automatic linking 가드 사전 확인** (§7.1.1) — Supabase 는 default 로 같은 verified email OAuth identity 를 자동 link 한다. CEO 결정 (CMP-572) 봉인은 **automatic linking 영구 금지**. 본 단계에서는 **콘솔 라벨을 단정하지 않는다** — Authentication 패널에 같은-email-다중-provider 동작을 통제하는 옵션이 있는지만 위치 확인하고, 실제 ON/OFF 봉인은 §7.1.1 G3 PoC 결과로 한다 (검증 시나리오: Google + Kakao 같은 verified email 가입 시 두 user 가 분리). 본 PR 은 콘솔 설정을 변경하지 않는다 — 봉인 작업 시점은 CMP-576 트랙.
  - **Preview branch connection 정보 PR comment 노출 OFF** (§7.3) — Supabase GitHub integration 콘솔의 PR 코멘트 옵션 중 "Include connection details / database URL / anon key in PR comment" 류 토글이 있으면 OFF 로 둔다. 라벨은 콘솔 버전에 따라 달라질 수 있으므로 단정하지 않고, **검증은 §7.3 의 self-check (실 PR 1개에서 노출 0건 확인) 로 봉인**한다. 콘솔에 별도 토글이 없는 경우에도 §6.3 wrapper workflow 가 connection string 을 PR 코멘트에 출력하지 않도록 §7.3 가드를 적용한다.
- [ ] **U5.** GitHub Settings → Secrets and variables → Actions 에 다음 추가 (값은 1Password 에서 복붙):
  - Secret: `SUPABASE_ACCESS_TOKEN` (Personal Access Token; Supabase 콘솔 Account → Access Tokens)
  - Secret: `SUPABASE_DB_PASSWORD_PROD`
  - Secret: `SUPABASE_DB_PASSWORD_DEV` (development persistent branch 용 DB password — production 과 별도)
  - Secret: `SUPABASE_DB_PASSWORD_STAGING` (staging persistent branch 용 DB password — production/dev 와 별도)
  - Variable: `SUPABASE_PROJECT_REF_PROD` (production project ref; `supabase projects list` 의 Reference ID)
  - Variable: `SUPABASE_PROJECT_REF_DEV` (**development persistent branch 의 BRANCH PROJECT ID — production ref 와 별도 값**. `supabase --experimental branches list` 의 `BRANCH PROJECT ID` 컬럼 값을 입력한다. Supabase 공식: https://supabase.com/docs/guides/deployment/branching/configuration#remote-specific-configuration)
  - Variable: `SUPABASE_PROJECT_REF_STAGING` (**staging persistent branch 의 BRANCH PROJECT ID** — `supabase --experimental branches list` 의 `staging` 행 `BRANCH PROJECT ID`. §7.1.1 G3 / §7.1.3 A5 / §7.1.4 O3 PoC 가 staging 을 대상으로 실행되므로 본 ref 가 없으면 PoC 검증 자체가 불가능하다.)
- [ ] **U6.** GitHub Settings → Branches → `main` / `dev` 보호 규칙 확인. **본 PR 시점에는 required check 변경 없음** (`ci-status` 만 required). Supabase preview check 는 §6 단계 2 에서 wrapper (§6.3) 로 추가.
- [ ] **U7. Production deploy/migration toggle 확인 — §6 단계 3 진입 차단 게이트.** Supabase Console → Project → Branching 에서 "production branch 에 migration 을 적용하는" 토글 (현 시점 Supabase 공식 라벨은 변경 가능 — UI 라벨을 단정하지 않는다) 이 ON 인지 확인. **검증 방법 (main-promotion-guard 호환 경로 사용 — MUST).** 본 레포의 `.github/workflows/main-promotion-guard.yml` 은 `main` 으로의 PR 을 `dev` 또는 `hotfix|fix|security/*` 베이스에서만 허용한다. `staging` 은 Supabase-only branch 이므로 GitHub PR 소스가 될 수 없다. 따라서 검증은 다음 두 경로 중 하나만 사용한다 — 둘 다 main-promotion-guard 가 허용한다:<br/>① **권장 (운영 흐름과 동일).** `dev` 에 noop dummy migration (예: `supabase/migrations/<ts>_supabase_prod_toggle_check.sql` — `SELECT 1;` 1줄) PR 머지 → `dev → main` promotion PR 머지. Supabase production branch migration 이력에 본 row 가 생기는지 콘솔에서 확인.<br/>② **권장 X (게이트 검증 전용 hotfix).** `hotfix/CMP-574-supabase-prod-toggle-check` 브랜치 (`hotfix/*` 는 main-promotion-guard 허용 예외) 에서 같은 noop SQL 을 추가해 `main` 으로 직접 PR. 머지 후 같은 콘솔 확인. ① 가 가능하면 항상 ①.<br/>**noop migration 영구 보존 (MUST — drift 사고 방지).** ① / ② 어느 경로를 쓰든 **production 에 적용된 noop SQL 파일은 절대 revert 하지 않는다**. Supabase 의 `db push` / GitHub integration 은 local `supabase/migrations/*.sql` 목록과 remote production migration history 의 timestamp 행을 1:1 으로 비교한다 (정본: https://supabase.com/docs/reference/cli/supabase-migration-repair). 적용 후 SQL 파일을 repo 에서 삭제/revert 하면 `local migration files and remote migration history are out of sync` 상태가 되어 다음 integration 배포가 fail 하거나 `supabase migration repair --status reverted <version>` 수동 복구가 필요해진다. 본 noop SQL 은 `SELECT 1;` 한 줄이라 운영 영향 0 이므로 **영구히 유지**한다. 어쩔 수 없이 제거해야 하면 같은 PR 에서 `supabase migration repair --status reverted <timestamp>` 절차를 PR 본문에 명시적으로 실행하고 그 출력 캡처를 첨부한다.<br/>본 토글이 OFF 면 `main` push 시 Supabase 가 production DB 에 migration 을 적용하지 않아 Neon `.github/workflows/deploy.yml::release-migrate` 를 제거한 단계 3 PR 머지 직후 production migration 경로가 끊긴다. **본 항목 미통과 시 단계 3 PR 머지 금지** (§6 단계 3 게이트로 봉인).

### 3.2 에이전트(또는 사용자) 후속 작업 — CMP-574 PR 머지 후

- [ ] **A1.** 사용자가 `SUPABASE_PROJECT_REF_PROD` 값을 별도 PR(또는 `chore/CMP-574-project-ref` 후속 브랜치)로 `supabase/config.toml` 의 `project_id` 에 채운다. **이 값은 비밀이 아니므로 커밋 가능.** 단 본 PR 에서는 placeholder.
- [ ] **A1.1** 같은 PR 에서 `[remotes.development].project_id` 를 `SUPABASE_PROJECT_REF_DEV` (development persistent branch 의 BRANCH PROJECT ID, U5 참고) 값으로 채운다. 본 절이 빠지면 development branch 를 대상으로 한 CLI 명령이 production 으로 잘못 흐른다. CLI 명령 시퀀스는 다음 둘 중 하나를 쓴다 (Supabase CLI 는 `--remote <name>` 플래그를 지원하지 않는다 — 정본: https://supabase.com/docs/reference/cli/introduction):<br/>① 새 셸: `supabase link --project-ref <DEV_BRANCH_PROJECT_REF>` 후 `supabase db diff` / `supabase db push` 호출.<br/>② 또는 `supabase db push --db-url "postgres://...@<dev_branch_host>/postgres"` (DB connection string 직접 지정).
- [ ] **A1.2 staging deployment path (별도 봉인 — PoC 적용 채널).** staging persistent branch 는 §1 매핑에서 **GitHub 트리거 없음** (Supabase 콘솔에서만 수동 promote) 이므로 §7.1.1 G3 / §7.1.3 A5 / §7.1.4 O3 PoC 를 staging 에 적용할 GitHub Actions 자동화 경로가 존재하지 않는다. 대신 **로컬에서 Supabase CLI 로 직접 staging 에 적용하는 path** 를 정본화한다. 같은 PR (A1) 또는 별도 후속 PR 에서 다음을 수행:<br/>① `supabase/config.toml` 의 `[remotes.staging].project_id` 를 `SUPABASE_PROJECT_REF_STAGING` (U5 staging BRANCH PROJECT ID) 값으로 채운다. 본 PR (CMP-574) 시점에는 `jippin-staging-placeholder` 봉인.<br/>② **로컬 CLI 시퀀스 (PoC 적용 표준 절차).** 새 셸에서 다음을 차례로 실행한다:<br/>&nbsp;&nbsp;&nbsp;&nbsp;1. `supabase link --project-ref <STAGING_BRANCH_PROJECT_REF>`<br/>&nbsp;&nbsp;&nbsp;&nbsp;2. `supabase db push` (SQL 마이그레이션 적용 — `[auth.identities]` 트리거 SQL, `before-user-created` Hook 등이 staging 에 반영)<br/>&nbsp;&nbsp;&nbsp;&nbsp;3. `supabase config push` (가용 시 — `[auth.external.*]` 등 config 동기화. 미가용 시 Supabase 콘솔 staging project 에서 수동 동기)<br/>&nbsp;&nbsp;&nbsp;&nbsp;4. PoC 실행 후 `supabase link --project-ref <DEV_BRANCH_PROJECT_REF>` 로 셸 컨텍스트 복귀 (production ref 와 혼동 방지)<br/>③ **GitHub Actions 자동화 비범위.** 본 PR 시점에는 staging promote 를 GitHub Actions 로 자동화하지 않는다 (§1 봉인: GitHub 측 staging 트리거 없음). 자동화가 필요해지면 별도 ADR + workflow 추가 (예: `hotfix/*` 와 동일한 trigger 패턴으로 `staging-promote.yml` 도입) 가 정본.<br/>④ **PoC 결과 첨부 의무.** CMP-576/CMP-577 PR 본문에 위 ②.1~②.4 명령의 출력 캡처 (DB password / connection string redact 후) 와 PoC 결과 (사용자 분리 / Hook reject / linkIdentity 흐름) 를 첨부한다. 첨부 없는 PR 은 §7.1.4 O3 / O4 게이트로 머지 금지.
- [ ] **A2.** CMP-575 (DB 트랙) 가 Alembic → SQL migration 변환 결과를 `supabase/migrations/` 에 채운다.
- [ ] **A3.** CMP-576 (Auth 트랙) 이 `supabase/config.toml` 의 `[auth.external.*]` 를 켜고 **같은 PR 에서 `[auth].enable_signup` 글로벌 gate 를 `true` 로 함께 바꾼다** (글로벌 gate 가 false 면 OAuth signup 도 막힘). `[auth.email].enable_signup` 은 영구 false 유지. **OAuth signup gate (MUST — PR 머지 직전 봉인).** A3 PR 머지 직전에 §7.1.4 (OAuth signup activation gate) 의 O1~O5 게이트가 모두 통과 상태여야 한다 (provider 시크릿 secrets/variables 등록 + §7.4 W-A~W-D Supabase-visible env wiring 통과, redirect_uri 봉인 — Supabase Auth callback `https://<PROD_REF>.supabase.co/auth/v1/callback` 만, 콘솔 provider 활성화, §7.1.1 G1~G3 자동 linking 가드 완료, §4.7 sealed terms flow 보장 — `before-user-created` Auth Hook 이 SSOT, callback 라우트 가드는 보조). 미통과 시 PR 머지 금지. CMP-577 트랙이 `[auth].enable_anonymous_sign_ins=true` 로 전환하며 §7.1.3 PoC 절차 (A5) 를 함께 수행.
- [ ] **A4.** §6 단계 1~3 에 따라 Neon workflow 를 단계적으로 제거하고 Supabase integration 으로 대체한다. 단계 2 PR 은 §6.3 wrapper workflow (`.github/workflows/supabase-status.yml`) 를 추가하고 §6.3.1 의 컨텍스트 식별 절차로 polling 대상을 박는다 — wrapper 구현은 §7.3 C2 (connection-string redact + unit-test) 를 같은 PR 에서 봉인한다. 단계 3 PR 은 머지 직전 **§3.1 U7 (production deploy/migration toggle ON) 검증 결과 + §7.2 R5 (production Data API exposed schemas 에 `public` 미포함) 확인 결과 + §7.3 C3 (preview PR 의 코멘트/본문에서 connection string / key / JWT 패턴 0건) self-check 결과** 3종을 모두 PR 본문에 첨부해야 머지 금지 게이트가 해제된다.

---

## 4. Automatic Branching 동작 설명 (운영자 이해용)

Supabase GitHub integration 의 Automatic Branching 은 다음과 같이 동작한다 (CMP-574 시점 공식 문서 기준 요약 — Supabase 가 동작을 변경할 수 있으므로 §8 참고 링크로 정본 확인):

1. PR opened/reopened/synchronize 이벤트가 GitHub → Supabase 로 webhook.
2. PR base 가 persistent branch 매핑 안에 들어가는지 확인 (`main` 또는 `dev`).
3. PR 의 변경 파일 중 `supabase/**` 가 있는지 확인 (Automatic branching: "Supabase changes only" 모드).
4. 해당 PR 용 ephemeral branch `preview/pr-N-<slug>` 를 parent branch (`production` 또는 `development`) 에서 fork.
5. `supabase/migrations/*.sql` 을 timestamp 순으로 preview branch 에 적용.
6. PR 코멘트로 preview branch 의 **안전 메타데이터만** 게시 — 허용: Supabase branch ID, branch status, migration apply 결과/실패 사유, 콘솔 deep-link. **절대 게시 금지:** DB connection string (`postgresql://...@<host>/postgres`, password 포함), `SUPABASE_DB_URL_*`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY` 가 박힌 URL, JWT 토큰 (`eyJhbGciOi...`). connection 값은 Supabase 콘솔 + 1Password 만 사용한다 — 본 봉인은 §7.3 (Preview branch connection-string 노출 가드) 이 정본화한다.
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
| **단계 1** | CMP-573 ADR-0004 Accepted **+ §6.3 wrapper workflow PR 머지 완료** | Neon workflow 에 `if: vars.SUPABASE_BRANCHING_LIVE != 'true'` 게이트 추가. GitHub variable 토글 1개로 Neon ↔ Supabase 흐름 전환 가능. 사용자가 §3.1 의 U1~U5 완료 후 토글 ON. **봉인 가드: 토글 ON 시점에는 `.github/workflows/supabase-status.yml` wrapper 가 이미 required check 로 활성화돼 있어야 한다** (§6.3 + §6.2). wrapper 가 없는 상태로 토글 ON 하면 단계 1~2 사이 required DB check 공백이 생긴다. wrapper 머지 PR (CMP-575 또는 별도 후속) 이 먼저 머지된 뒤 토글 ON. | CMP-574 후속 또는 CMP-573 머지 PR |
| **단계 2** | 단계 1 토글 ON + Supabase production 머지 1회 성공 | `.github/workflows/ci.yml::migrate-check` job 의 `NEON_TEST_DATABASE_URL` 의존을 제거하고 본 job 을 **Supabase SQL migration 기준 drift guard 로 재정의** (§6.3.2). 모델/마이그레이션 drift 가드 (apps/api/src/models 변경 ↔ `supabase/migrations/*.sql` 동반 변경) 를 유지해 model-only PR 이 drift 상태로 머지되는 경로를 막는다. | CMP-574 후속 또는 CMP-575 머지 PR |
| **단계 3** | 단계 2 후 2주간 사고 없음 **+ §3.1 U7 (Supabase production deploy toggle ON) 검증 통과 + §7.2 R5 (production Data API 콘솔 봉인) 통과 + §7.3 C3 (connection-string 노출 0건) 통과** | `.github/workflows/neon-pr-branch.yml` 삭제. `.github/workflows/deploy.yml::release-migrate` 의 Neon DATABASE_URL 의존 삭제. `docs/runbooks/neon-branches.md` 를 archive 폴더로 이동 (`docs/runbooks/_archive/`). **U7 / R5 / C3 중 하나라도 미통과 시 머지 금지** — release-migrate 를 끄는 순간 production DB 가 migration 적용 경로를 잃거나, RLS 미완성 상태로 main migration 이 production 에 적용되며 dashboard default 노출 정책이 anon key 로 검색 가능하게 만들 수 있다. | 별도 후속 이슈 (CMP-574 가 만들거나 DevOps Lead 가 발주) |

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
| 단계 0 | `ci-status` | 현재 상태. `ci-status::migrate-check` 가 Alembic drift guard 정본. |
| 단계 1 | `ci-status`, **`supabase-status`** (wrapper) | wrapper 머지 PR 이 본 단계 시작의 전제 (§6 단계 표). 토글 ON 직전에 wrapper 를 required 로 등록해 단계 1~2 사이 required DB check 공백을 없앤다. wrapper 이름은 §6.3 가 정의. 실제 Supabase integration check 이름은 §6.3.1 의 컨텍스트 식별 절차로 확정. |
| 단계 2 | `ci-status`, `supabase-status` | `ci-status::migrate-check` 가 §6.3.2 의 **Supabase SQL migration drift guard** 로 재정의된 상태. Alembic drift guard 는 본 단계 PR 에서 교체된다. |
| 단계 3 | `ci-status`, `supabase-status` | Neon workflow 제거 후에도 동일. `ci-status::migrate-check` 는 §6.3.2 의 Supabase drift guard 로 유지 (삭제 금지 — 모델/마이그레이션 동행 누락 PR 을 잡는 마지막 가드). |

**왜 Supabase preview check 를 required 로 두는가**: production/development 매핑 PR 이 migration 깨진 채 머지되면 Supabase 가 `main`/`dev` push 에서 production/development DB 에 직접 적용하기 때문. preview branch 에서 미리 잡아야 운영 사고를 막는다.

### 6.3 path-filter deadlock 회피 (wrapper workflow 패턴)

**문제.** Automatic branching 을 "Supabase changes only" 로 제한하면 `supabase/**` 를 안 건드린 PR 에는 integration 이 만든 preview check 가 아예 나타나지 않는다. 이 상태에서 같은 context 를 GitHub branch protection 의 required check 로 등록하면 머지 deadlock 이 발생한다 (PR 이 미해결 required check 를 영원히 기다림).

**해결.** 단일 wrapper check (`supabase-status`) 를 항상 실행되는 workflow 로 두고, branch protection 은 wrapper 만 required 로 등록한다. wrapper 가 PR 안의 변경 파일을 보고 결정한다:

- `supabase/**` 변경 없음 → wrapper 자체로 succeed (skip 의미).
- `supabase/**` 변경 있음 → 실제 Supabase integration check 의 결과를 기다린 뒤 그 결과를 그대로 wrapper 결과로 반영. `gh api` 폴링 또는 `wait-on-check-action` 류 액션을 사용. timeout 발생 시 fail.

이는 본 PR 의 `ci-status` 메타 게이트와 동일한 패턴이다 (`ci-status` 가 하위 jobs 의 결과를 집계해 단일 required check 를 제공).

**적용 시점.** `.github/workflows/supabase-status.yml` skeleton + branch protection 갱신은 **단계 1 토글 ON 과 같은 PR 또는 그 직전 PR** 에서 처리한다 (단계 표 봉인). 토글 ON 시점에 wrapper 가 없으면 Neon 게이트가 꺼지면서도 Supabase 측 required check 가 없어 단계 1~2 사이 PR 들이 DB 가드 없이 머지된다. 본 PR (단계 0) 은 wrapper workflow 를 만들지 않지만 위 봉인을 반드시 지킨다.

#### 6.3.1 실제 Supabase integration check context 식별 절차

Supabase 가 integration check context 이름을 콘솔 옵션·버전에 따라 변경할 수 있으므로 단계 2 PR 머지 직전에 실제 이름을 확정한다.

1. 단계 1 토글 ON 후 `supabase/**` 를 변경하는 dummy PR 을 1개 연다.
2. PR check 목록에 나타나는 Supabase 측 check 의 context 이름을 기록한다 (예: `Supabase Preview`, `Supabase / Preview`, `Supabase Migrations` 등).
3. 그 이름을 §6.3 wrapper workflow 의 polling 대상으로 박는다.
4. branch protection 의 required check 는 wrapper (`supabase-status`) 만 등록한다 — Supabase 측 context 를 직접 required 로 등록하지 않는다 (path-filter deadlock 회피).

`Supabase Preview` 가 2026-05 기준 Supabase 공식 예시 context 이름이지만, 본 런북은 **wrapper 가 단계 2 PR 시점의 실제 이름을 polling 한다**는 운영 절차만 봉인한다.

#### 6.3.2 Supabase SQL migration drift guard (model-only PR 가드)

**문제.** 단계 2 에서 `ci.yml::migrate-check` 의 Alembic + `NEON_TEST_DATABASE_URL` 의존을 제거하면 `apps/api/src/models/` (SQLAlchemy 모델) 만 바꾸고 `supabase/migrations/*.sql` 을 추가하지 않은 PR 이 가드 없이 머지될 수 있다. preview branch 는 SQL 파일만 적용하므로 모델-only PR 은 preview check 도 통과한다 — 가장 흔한 "마이그레이션 누락" 사고가 잡히지 않는다.

**해결.** 단계 2 PR 이 `ci.yml::migrate-check` job 을 **Supabase SQL migration drift guard** 로 재정의한다. 본 job 은 Neon 의존을 갖지 않고, 다음 조건을 검사한다.

1. PR 의 변경 파일 중 `apps/api/src/models/**/*.py` 가 있는지 확인 (스키마 owner 경로).
2. 위 변경이 있을 때 PR 안에 `supabase/migrations/*.sql` 파일이 함께 추가/수정됐는지 확인.
3. 모델은 바뀌었는데 SQL 마이그레이션이 동행하지 않으면 **fail** 한다 (drift). 본문에 어떤 모델 파일이 SQL 마이그레이션 동행 없이 변경됐는지를 명시.
4. 모델 변경이 없거나 모델·SQL 마이그레이션이 둘 다 변경된 PR 은 통과.

**왜 wrapper 와 별도인가**: wrapper (`supabase-status`) 는 Supabase 측 preview/migration check 결과만 polling 한다 — preview branch 가 만들어진 PR 의 SQL 적용이 성공했는지 본다. 본 drift guard 는 그 반대로 **SQL 파일 자체가 빠진 PR 을 잡는 정적 가드**다. 두 가드는 잡는 케이스가 다르므로 한쪽으로 통합하지 않는다.

**구현 위치 (단계 2 PR 의 범위)**: `.github/workflows/ci.yml::migrate-check` 를 `git diff --name-only origin/${{ github.base_ref }}...HEAD` 기반 정적 검사로 교체. `NEON_TEST_DATABASE_URL` 등 Neon 시크릿 의존은 모두 제거. 본 job 은 `ci-status` 집계 대상에 포함되어 required check (`ci-status`) 의 일부로 봉인된다.

**단계 3 이후**: 본 drift guard 는 단계 3 (Neon workflow 제거) 이후에도 **유지**한다 (§6.2 단계 3 행). Supabase integration 이 production migration 을 책임진다고 해서 모델/마이그레이션 동행 누락은 잡히지 않기 때문.

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

> **봉인.** AGENTS.md §4.7 #9 은 같은 verified email 이 카카오·구글·네이버에서 각각 가입되면 **별개 user 로 둔다**고 명시한다 (duplicate email row 자체는 허용). 따라서 본 가드의 목표는 `auth.users` row 의 중복을 막는 것이 아니라, **Supabase 의 automatic identity attach** (같은 이메일을 가진 기존 user 에 새 OAuth identity 를 자동 연결하는 동작) 를 막는 것이다.

| 게이트 | 결정/검증 | 책임 | 본 PR 적용 |
|---|---|---|---|
| G1. **콘솔 토글 — 라벨 의존 금지.** Supabase 콘솔에는 자동 identity attach 동작을 통제하는 옵션이 있다고 알려져 있으나 UI 라벨은 버전에 따라 변경되고 ON/OFF 의미가 모호하다. **본 게이트는 콘솔 라벨이 아니라 PoC 결과 (G3) 를 SSOT 로 검증한다** — CMP-576 가 staging branch 에서 옵션을 토글하면서 G3 시나리오가 통과하는 콘솔 설정 조합을 기록·봉인한다. 본 PR 은 라벨 이름을 단정하지 않고 ON/OFF 도 처방하지 않는다. PoC 결과 미첨부 PR 은 머지 금지. | CMP-576 — PoC 후 콘솔 설정 봉인 | 본 PR 머지 후 |
| G2. **DB 트리거 fallback — automatic identity attach 차단.** `auth.identities` BEFORE INSERT 트리거로 "기존 user 에 다른 provider identity 가 자동으로 붙는" 경로만 reject 하고, **새 user 행을 만들어 attach 하는 경로는 허용** 한다. duplicate email user row 자체는 막지 않는다 (§4.7 #9 정합). 실제 SQL/조건절은 CMP-576 가 정본화: `supabase/migrations/<timestamp>_block_auto_email_attach.sql`. | CMP-576 (DB 트리거 SQL) | CMP-576 PR |
| G3. **PoC — 시나리오로 검증.** staging branch 에서 다음 시나리오를 실행하고 결과를 CMP-576 PR 본문에 첨부: (a) Google 가입 → 같은 email 로 Kakao 가입 시 두 user 가 분리되는가, (b) Google 재로그인이 기존 user 로 그대로 가는가, (c) 한 user 의 manual `linkIdentity()` 흐름이 영향받지 않는가. 통과한 콘솔 설정 조합을 G1 의 봉인 값으로 본 런북에 commit-back. | CMP-576 (PoC + 콘솔 봉인) | CMP-576 PR |

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

> **Phase gate (봉인).** 본 절차는 **ADR-0004 Supabase 전환 ADR 가 Accepted 되고 데이터 마이그레이션이 끝난 뒤** (Phase 2 이후) 의 정본 흐름이다. Phase 0 (본 PR — 스캐폴드) 과 Phase 1 (Supabase DB/Auth 활성화는 됐지만 legacy 흐름이 살아있는 동안) 에는 **ADR-0003 의 `anonymous_users.id` (UUID v4, localStorage `jippin_anonymous_user_id`) + `converted_user_id` claim 경로가 계속 정본**이다. `signInAnonymously()` 를 Phase 0/1 에 도입하면 두 식별자 체계가 충돌한다 — 본 절은 즉시 대체 지시로 읽지 말 것.

**Phase 정의 (본 절 한정 — 전사 phase 정의는 ADR-0004 가 정본).**

| Phase | 상태 | anonymous 식별자 정본 |
|---|---|---|
| Phase 0 | 본 PR (CMP-574, 스캐폴드) | `anonymous_users.id` (ADR-0003). Supabase anonymous 미사용. |
| Phase 1 | Supabase DB 활성화 후 ~ 데이터 마이그레이션 전 | `anonymous_users.id` 유지. **Supabase anonymous 와 dual-write/dual-read 또는 read-only 검증 만**. 사용자 흐름은 legacy. |
| Phase 2 | 데이터 마이그레이션 + ADR-0004 가 본 절을 Accepted 로 봉인 | 본 §7.1.3 A1~A5 흐름이 정본. legacy `anonymous_users` 는 ADR-0004 가 정한 sunset 절차에 따라 제거. |

**Phase 2 흐름 (참고용 — 활성화 게이트는 위 phase gate).**

| 단계 | 동작 | 책임 |
|---|---|---|
| A1. anonymous sign-in (`supabase.auth.signInAnonymously()`) 으로 user row 생성, 비회원 사전검토 데이터를 본 user 에 귀속. **Phase 2 진입 전까지 호출 금지** — Phase 0/1 는 ADR-0003 `anonymous_users.id` 가 정본. | CMP-577 (Phase 2) |
| A2. 사용자가 "로그인/가입" 누르면 OAuth provider 로 redirect — 단 anonymous session 을 유지한 채 `linkIdentity({ provider })` 호출. 새 user 가 만들어지면 안 된다 (`enable_manual_linking = true` 가 전제). | CMP-577 (Phase 2) |
| A3. callback 에서 linked identity 가 성공적으로 추가됐는지, anonymous user 의 `is_anonymous` flag 가 false 로 전환됐는지 검증. 실패 시 anonymous session 유지 + 사용자 에러 표시. | CMP-577 (Phase 2) |
| A4. **자동 병합 충돌 케이스** — anonymous user 의 OAuth identity 가 이미 다른 permanent user 의 verified email 과 같으면 §7.1.1 의 G1/G2 가드에 의해 자동 attach 가 일어나지 않는다. 본 케이스는 "기존 계정으로 로그인" 안내 UI 로 처리. 두 계정 병합은 별도 "계정 통합" 명시 흐름. | CMP-577 (Phase 2) |
| A5. PoC — staging branch 에서 anonymous → Google upgrade, anonymous → Kakao upgrade, 동일 email 충돌 케이스 3가지 시나리오 검증 로그를 CMP-577 PR 본문에 첨부. | CMP-577 (Phase 2) |
| A6. **legacy → Supabase migration gate.** Phase 1 종료 시점에 `anonymous_users` row → Supabase anonymous user row 1:1 migration (또는 `converted_user_id` 기반 직접 user 이관) 을 ADR-0004 의 마이그레이션 트랙이 정본화. 본 게이트를 통과하기 전까지 A1 을 사용자 흐름에 노출하지 않는다. | DB 트랙 (ADR-0004 후속) |

본 PR 시점에는 `enable_anonymous_sign_ins = false` 유지. Phase 2 진입 PR (CMP-577 또는 ADR-0004 supersede PR) 이 위 dual-write/migration gate (A6) 통과를 본문에 입증한 뒤에만 true 로 바꾼다.

#### 7.1.4 OAuth signup activation gate (MUST — `[auth].enable_signup = true` 진입 봉인)

§3.2 A3 PR 이 `[auth].enable_signup = true` 와 `[auth.external.*].enabled = true` 를 켜는 시점에는 다음 5개 게이트가 모두 통과 상태여야 한다. 하나라도 빠진 상태로 머지하면 (a) 환경 미설정으로 OAuth 콜백이 곧장 깨지거나 (b) AGENTS.md §4.7 의 sealed terms flow (Google/Naver 첫 signup 은 internal terms 동의 뒤에만 완료) 가 우회된다.

| 게이트 | 조건 | 책임 | 본 PR 적용 |
|---|---|---|---|
| O1. **시크릿 등록 완료.** GitHub Secrets (`SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID`/`_SECRET`, `_KAKAO_*`, Naver custom OIDC) 와 Supabase Vault (`auth.external.*.secret` 가 참조) 가 채워졌다. 콘솔에서 provider 가 활성화돼 있고 client_id/secret 이 등록됨. | CMP-576 (PR 본문에 vault key 이름만 첨부, 값은 절대 첨부 금지) | 본 PR 미적용 |
| O2. **`redirect_uri` 봉인 — Supabase Auth callback 만.** `[auth.external.*].redirect_uri` 는 **provider 콘솔에 등록되고 provider 가 인가코드를 보내는 OAuth callback URL** 이다. Supabase 공식 예시와 흐름 (provider → Supabase `/auth/v1/callback` → app `/auth/callback`) 에 따라 본 값은 **항상 `https://<PROD_PROJECT_REF>.supabase.co/auth/v1/callback`** 으로 봉인한다 (정본: https://supabase.com/docs/guides/auth/social-login). **`site_url`/`additional_redirect_urls`/app `/auth/callback` 같은 운영 도메인 값을 절대 넣지 않는다** — 그러면 provider 가 인가코드를 Next.js 로 직접 보내 Supabase Auth 가 code 교환을 못 한다. provider 콘솔 (Google Cloud / Kakao Developers / Naver Developers) 의 Authorized redirect URI 도 동일한 Supabase Auth callback URL 로 등록한다. app callback 매칭은 §3.1 `site_url` + `additional_redirect_urls` 가 책임. | CMP-576 | 본 PR 미적용 |
| O3. **§7.1.1 G1~G3 통과.** automatic identity linking 가드 (콘솔 설정 + DB 트리거 + PoC) 가 staging branch 에서 검증. 미통과 상태로는 provider 활성화 금지. | CMP-576 | 본 PR 미적용 |
| O4. **§4.7 sealed terms flow 보장 — `before-user-created` Auth Hook 이 SSOT.** Google/Naver 첫 signup 콜백에서 internal terms 동의 전에 영속 user row 가 만들어지지 않게 하려면 **Supabase Auth 흐름의 차단점이 `before-user-created` Auth Hook 단계 하나뿐** 이다. provider → Supabase `/auth/v1/callback` → Supabase 가 `auth.users` row insert → app `/auth/callback` 으로 redirect 순서이므로, app callback 단계에 도달했을 때는 이미 permanent user 가 생성돼 있어 callback 라우트에서 "pending-user 토큰만 발급" 식의 어플리케이션 가드로는 §4.7 sealed flow 를 봉인할 수 없다 (정본: https://supabase.com/docs/guides/auth/auth-hooks/before-user-created-hook). 따라서 본 게이트의 **유일한 차단점**은:<br/>(a) **MUST — `before-user-created` Auth Hook 등록.** Supabase Console (Auth → Hooks → Before user created) 또는 `[auth.hook.before_user_created]` config 로 internal terms 미동의 + OAuth signup 시도를 reject 한다. Hook 의 입력은 candidate user payload, 출력은 reject/continue 이며 reject 되면 `auth.users` 가 만들어지지 않는다. Hook 구현 SQL/함수는 CMP-576 가 정본화 (`supabase/functions/before-user-created-terms-gate.sql` 등). PoC 결과를 CMP-576 PR 본문에 필수 첨부.<br/>(b) **보조 — callback 라우트의 terms 확인 + 미동의 시 즉시 정리.** Hook 차단이 통과한 user 에 대해서도 app `/auth/callback` 에서 terms 동의 상태를 재확인하고, 미동의 user 는 즉시 `auth.admin.deleteUser()` 로 정리하거나 internal terms UI 로 redirect. **(b) 단독으로는 §4.7 봉인 불충분** — (a) Hook 없이 (b) 만 적용하면 hook 차단 전 단계에 이미 만들어진 user 가 idle 상태로 잔존한다. (b) 는 (a) 의 추가 안전망 역할만 한다.<br/>(c) **자동 linking 우회 차단.** §7.1.1 G2 DB 트리거가 같은 PR 에서 함께 적용돼 있어야 (a) Hook 의 reject 가 "기존 user 에 identity attach" 우회로 빠지지 않는다. (c) 미적용 시 (a) (b) 모두 우회 가능. | CMP-576 + CMP-577 (Web) | 본 PR 미적용 |
| O5. **anonymous → OAuth upgrade 흐름 분리.** §7.1.3 의 phase gate 가 Phase 2 진입 전이면 `signInAnonymously()` 흐름을 사용자 UI 에 노출하지 않는다. OAuth signup 만 활성화. Phase 2 진입은 ADR-0004 가 따로 봉인. | CMP-577 | 본 PR 미적용 |

본 PR (CMP-574, 단계 0) 은 `[auth].enable_signup = false` + 모든 `[auth.external.*].enabled = false` 봉인을 유지한다. CMP-576 PR 머지 직전에 본 §7.1.4 의 O1~O5 결과를 PR 본문에 첨부하고 통과시킨다. 미통과 PR 은 Web/Auth required check (단계 2 후속) 와 본 런북 §3.2 A3 봉인으로 머지 금지.

### 7.2 PostgREST / GraphQL 노출 게이트 (RLS 완성 전 봉인)

Supabase 는 default 로 `public` 스키마의 모든 테이블/뷰를 PostgREST + GraphQL 로 외부 노출한다. 본 PR 시점의 정본 스키마 (Alembic 산출 — `users`, `request_logs`, `anonymous_users`, `consultations` 등) 에는 RLS policy 가 전혀 없고 `ENABLE ROW LEVEL SECURITY` 도 걸려 있지 않다. 따라서 `[api]` 가 켜진 채 본 마이그레이션을 적용하면 anon key 보유자가 PostgREST/GraphQL 로 `public` 테이블을 직접 조회할 수 있어 FastAPI 게이트웨이를 우회한다.

> **봉인.** `[api].schemas` 에서 `"public"` 만 빼는 우회는 **public 노출 차단 가드로 무효**다. Supabase 내부 동작은 PostgREST 의 `db-schema` 에 `public` 과 `storage` 를 항상 포함시키므로 (`api.schemas` 는 그 위에 더하는 allow-list — 정본: https://supabase.com/docs/guides/api/securing-your-api), `enabled = true` 가 되는 순간 `schemas = ["graphql_public"]` 이어도 `public` 테이블이 anon key 로 조회된다. 따라서 RLS 완성 전 PostgREST 차단의 **유일한 정본 가드는 `[api].enabled = false`** 다. `schemas` 는 보조 통제일 뿐 본 게이트의 SSOT 가 아니다.

| 게이트 | 조건 | 책임 |
|---|---|---|
| R1. **테이블별 RLS 활성화.** `public` 의 모든 영속 테이블에 `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` 를 SQL 마이그레이션으로 적용. | CMP-575 |
| R2. **운영 policy 봉인.** anon / authenticated / service_role 각 역할별 SELECT/INSERT/UPDATE/DELETE policy 가 정의. policy 빈 테이블이 0건임을 PR 본문 self-check 에 첨부. | CMP-575 |
| R3. **PostgREST 토글 PR (local + Supabase preview branch).** `supabase/config.toml` 의 **`[api].enabled = true` 자체를 토글하는 PR** 이 본 게이트의 단일 진입점. `schemas` 만 수정해서 `public` 을 제외한 채 `enabled = true` 로 바꾸는 PR 은 무효 (위 봉인 박스 참고) — 본 게이트로 잡는다. PR 본문에 R1·R2 결과 첨부. CMP-575 머지 직후 또는 별도 후속 PR. | CMP-575 후속 |
| R4. **preview branch 운영 검증.** preview branch 에서 anon key 로 `public` 의 민감 테이블 (`users`, `request_logs`, `consultations`) 직접 조회를 시도해 RLS 가 차단하는지 확인. 통과 결과를 PR 본문에 첨부. | CMP-575 후속 |
| R5. **production Dashboard / config-push 가드 (MUST — config.toml 밖에서 봉인).** Supabase GitHub integration 은 **production 배포 시 migration/Edge Functions/Storage 만 적용하고 `[api]`, `[auth]` 등 일반 config 는 default 로 무시한다** (정본: https://supabase.com/docs/guides/deployment/branching/github-integration). 따라서 `supabase/config.toml` 의 `[api].enabled = false` 봉인 값은 local 과 preview branch 에만 적용되고, **production branch 의 Data API 노출은 콘솔 Dashboard 설정 (Settings → API → Data API) 이 SSOT** 다. 본 게이트는 다음을 명시 봉인한다:<br/>① **production Data API OFF (또는 `public` 미노출) 봉인.** Supabase Console (production project) → Settings → API → Data API 에서 본 API 자체를 **OFF (disabled)** 로 두거나, ON 인 경우 Exposed schemas 에 `public` 이 포함돼 있지 않은 상태를 R1~R4 통과 PR 머지 시점까지 유지. 위 봉인 박스대로 Exposed schemas 에서 `public` 만 빼도 PostgREST 내부적으로 `public` 이 포함될 수 있으므로 **R1~R4 완료 전에는 Data API OFF 가 1차 권장**, "ON 이지만 public 제외" 는 2차 가드 (해당 시 Dashboard → SQL Editor → `public` 스키마 권한 회수 + GRANT 회수 SQL 마이그레이션 보강). CMP-575/후속 R3 PR 머지와 동시에 콘솔 토글 (또는 `supabase config push --project-ref <PROD_REF>` 가 가용해지면 config.toml 동기화). R3 PR 본문에 dashboard 스크린샷 + Data API 상태 캡처 (key/secret 마스킹) 또는 `supabase config diff` 결과 첨부.<br/>② **단계 3 머지 게이트.** Neon `release-migrate` 제거 PR (§6 단계 3) 본문에 R5-① "production Data API OFF 또는 RLS 완성 후 R1~R4 통과" 확인 결과를 첨부해야 머지 게이트 통과. R1~R4 미통과 상태에서 단계 3 머지를 시도하면, `main` push 가 `users`/`request_logs`/`consultations` 마이그레이션을 production 에 적용하는 순간 dashboard default 노출 정책이 anon key 로 본 테이블을 검색 가능하게 만들 위험이 있다.<br/>③ **회복 절차.** 사후 노출이 발견되면 즉시 콘솔에서 Data API → OFF 로 회귀 → 1Password 의 anon key 회전 → R3 PR revert → 노출된 테이블 권한 회수 SQL 마이그레이션 보강. | CMP-575 후속 + DevOps |

R1~R5 미통과 상태에서 `[api].enabled = true` / `schemas` 에 `"public"` 추가 / production Dashboard 의 Data API ON + `public` 노출을 시도하는 PR 은 머지 금지. 본 봉인은 §6.3.2 의 drift guard 와 독립이다 (drift guard 는 모델/마이그레이션 동행 가드, 본 게이트는 RLS 완성 + production 노출 가드).

본 PR (CMP-574, 단계 0) 의 `supabase/config.toml` 봉인 값: `[api].enabled = false` (1차 SSOT), `schemas = ["graphql_public"]` (2차 통제). 본 값은 **local + Supabase preview branch 에만 적용**되고, **production Data API 노출은 R5-① 의 콘솔 Data API 토글이 SSOT** 다. CMP-575/후속 R3 PR 이 config.toml + 콘솔 양쪽을 동시에 토글한다.

### 7.3 Preview branch connection-string 노출 가드 (MUST)

Supabase preview branch 가 PR 별로 생성되면 integration / wrapper / 운영자가 PR 코멘트에 "preview DB 접근 정보" 를 적고 싶어지는 유혹이 있다. 그러나 Supabase connection string (`postgresql://postgres.<branch_ref>:<password>@<host>:6543/postgres`) 은 **DB password 자체를 포함**한다. anon key 가 박힌 `SUPABASE_URL` + key 조합도 RLS 미완성 상태에서는 광범위 노출 위험이 동일하다. PR 코멘트는 organization 외부 GitHub 사용자 / 봇 / 검색 인덱스가 읽을 수 있으므로 이를 적는 것은 즉시 시크릿 leak 이다.

**허용 / 금지 패턴 봉인.**

| 채널 | 허용 (PR comment / PR body / log 출력) | 금지 |
|---|---|---|
| Supabase branch ID, branch status, parent branch 이름 | ✅ | — |
| Migration apply 결과 (성공/실패 + 실패 SQL 라인 번호) | ✅ | 실패 SQL 본문에 password 가 있는 경우 redact |
| Supabase 콘솔 deep-link (`https://supabase.com/dashboard/project/<ref>/branches/<branch_id>`) | ✅ | — |
| DB connection string (`postgres(ql)?://...@...supabase.(co\|com\|net)`) | — | ❌ PR comment / PR body / workflow log |
| `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` | — | ❌ |
| JWT (`eyJhbGciOi...`) | — | ❌ |
| `SUPABASE_DB_URL_*`, `SUPABASE_DB_PASSWORD_*` | — | ❌ |

**가드.**

| 게이트 | 조건 | 책임 |
|---|---|---|
| C1. **콘솔 토글 (가용 시).** Supabase GitHub integration 콘솔에 "Include connection details in PR comment" / "Post database URL" 류 옵션이 있으면 OFF 봉인 (§3.1 U4). 라벨은 단정하지 않고 실제 동작은 C3 self-check 결과로 검증한다. | DevOps (§3.1 U4) |
| C2. **wrapper workflow gag.** §6.3 의 `.github/workflows/supabase-status.yml` 가 Supabase API 응답을 PR comment 로 옮기는 어떤 단계든 connection string / key / JWT 패턴을 redact 한 뒤에만 출력. wrapper 구현 PR (CMP-575 또는 별도) 본문에 본 redact 로직 + unit-test 결과를 첨부. | DevOps (wrapper PR) |
| C3. **PR self-check (필수).** preview branch 가 만들어진 첫 PR (또는 단계 1 토글 ON 후 첫 supabase-touching PR) 의 코멘트/PR 본문에서 §8 self-check 4종 패턴 (sbp_/sb_secret_/JWT/supabase Postgres URL) 이 0건임을 PR 본문에 캡처해 첨부. 노출 발견 시 즉시 §7.3 회복 절차 적용. | 단계 1 토글 ON PR 작성자 |
| C4. **회복 절차.** 노출이 발견되면 (a) 해당 PR comment 즉시 삭제/edit, (b) 1Password 에서 노출된 시크릿 (DB password / anon key / service role) 즉시 회전 (§8 시크릿 회전 정책), (c) Supabase 콘솔에서 해당 preview branch 삭제 후 재생성, (d) `tools/secret-scan` + `gitleaks` 의 노출 패턴을 보강 PR 로 추가. | DevOps |

C1~C4 통과 전 단계에서 connection string 을 PR comment 로 노출하는 wrapper / workflow / 운영자 절차는 **즉시 사고 (P1 incident) 로 간주** 한다 — `tools/secret-scan` 룰셋에 본 패턴을 추가해 사후 grep self-check 가 fail 하도록 한다.

### 7.4 Supabase-visible env wiring (`env()` 참조 정본)

CMP-576 가 `[auth.external.google].client_id = "<literal>"` 를 `env(SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID)` 로 바꾸는 순간, **본 환경변수가 Supabase CLI / Supabase GitHub integration 의 실행 컨텍스트에 보여야** 값이 해석된다. **`apps/api/.env.example`, `apps/web/.env.example` 은 application runtime 용 placeholder** 일 뿐 Supabase CLI / integration 은 본 파일들을 읽지 **않는다**. CMP-576 PR 이 두 .env.example 만 업데이트하고 본 절을 빠뜨리면 local `supabase start` / `supabase db diff` 가 unresolved env 로 fail 하고, preview/production deploy 가 OAuth provider 없이 진행되어 콜백이 깨진다.

**Supabase 가 `env()` 를 해석하는 채널 — 본 4개가 SSOT 다.**

| 채널 | 적용 범위 | 값 등록 방법 | gitignored? |
|---|---|---|---|
| **W1. `supabase/.env`** | Local CLI (`supabase start`, `supabase db diff`, `supabase config push` 등) | repo root 의 `supabase/.env` 또는 `supabase/.env.local` 파일에 `KEY=value` 1줄씩. 본 파일은 본 PR 시점에 작성되지 않는다 (CMP-576 가 .env.example 동행 추가). | ✅ (`.gitignore` 의 `.env` / `.env.*` 패턴이 매칭 — supabase 디렉터리 안의 `.env` 도 포함. 본 PR 시점 self-check `.env` 패턴 확인.) |
| **W2. Supabase 콘솔 → Project Settings → Vault** | preview/production Supabase project 의 Auth/Edge Functions 가 실행될 때 참조 | 콘솔 UI 에서 1개씩 등록. 또는 `supabase secrets set --project-ref <REF> KEY=value` CLI. 정본: https://supabase.com/docs/guides/cli/managing-config#using-secrets-inside-configtoml | N/A (콘솔 only) |
| **W3. `supabase secrets set` CLI** | W2 와 동일 — CLI 자동화 채널 | `supabase secrets set --project-ref <SUPABASE_PROJECT_REF_PROD> SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID=<value>` 등. GitHub Actions 에서 `SUPABASE_ACCESS_TOKEN` 으로 인증 후 호출. | N/A |
| **W4. GitHub Actions env 주입 (제한적)** | 본 레포의 GitHub Actions job 이 `supabase` CLI 를 호출하는 step 의 `env:` 블록 | step 의 `env:` 에 `SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID: ${{ secrets.SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID }}` 식으로 주입. **integration 자체가 호출하는 deploy 단계에는 적용 안 됨** — W2 / W3 가 정본. | N/A |

**활성화 PR 의 봉인 절차 (CMP-576 PR 본문 self-check 의무).**

| 단계 | 조건 | 책임 |
|---|---|---|
| W-A. **`supabase/.env.example` 동행 추가.** `supabase/.env.example` 에 본 PR 이 도입하는 `env()` 변수명을 placeholder 값과 함께 등록 (예: `SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID=<google-oauth-client-id>`). **`apps/api/.env.example`, `apps/web/.env.example` 만 업데이트하는 PR 은 본 게이트로 reject** — supabase CLI 가 안 읽는 위치만 갱신했기 때문. | CMP-576 |
| W-B. **W2/W3 콘솔/CLI 등록.** Production + Development + Staging persistent branch project 각각의 콘솔 Vault 또는 `supabase secrets set --project-ref <REF> ...` 실행 결과 (키 이름만, 값은 redact) PR 본문에 첨부. | CMP-576 (DevOps + Auth Lead) |
| W-C. **검증 PoC.** staging branch 에서 `supabase db diff` / `supabase status` 가 `env()` 값을 unresolved 상태로 떨어뜨리지 않고 통과하는지 캡처 첨부. 실패하면 변수명 / 등록 채널 (W1~W4) 매칭 재확인. | CMP-576 |
| W-D. **`.gitignore` 봉인 확인.** `supabase/.env` / `supabase/.env.local` 이 `.gitignore` 의 `.env` / `.env.*` 패턴에 매칭되는지 self-check (`git check-ignore -v supabase/.env`). 미매칭 시 본 PR 에서 명시 추가. | CMP-576 |

W-A 미통과 시 `env()` 해석이 깨져 `supabase start` 부터 fail. W-B 미통과 시 local 만 통과하고 preview/production OAuth 가 깨짐. W-C 미통과 시 통합 환경에서만 fail 하는 silent 버그. W-D 미통과 시 secret 실수 커밋 위험.

본 PR (CMP-574, 단계 0) 시점에는 모든 `[auth.external.*]` 가 `enabled = false` 이고 `client_id`/`secret` 이 빈 문자열이므로 `env()` 가 등장하지 않는다 — W-A~W-D 는 CMP-576 PR 시점 게이트.

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
# 1) 레거시 service-role / personal access token (sbp_*) + 신형 elevated secret (sb_secret_*).
git grep -nE "sbp_[A-Za-z0-9]{40,}|sb_secret_[A-Za-z0-9]{20,}" -- ":(exclude)*/node_modules/*" ":(exclude)*/.venv/*"
# 2) JWT-like (anon/service-role JWT 형식 — eyJhbGciOi... 로 시작).
git grep -nE "eyJhbGciOi[A-Za-z0-9._-]{40,}" -- ":(exclude)*/node_modules/*" ":(exclude)*/.venv/*"
# 3) Supabase Postgres connection string — pooler/direct 모두 포함.
git grep -nE "postgres(ql)?://[^[:space:]\"]*@[^[:space:]\"]*\.supabase\.(co|com|net)[^[:space:]\"]*" -- ":(exclude)*/node_modules/*" ":(exclude)*/.venv/*"
# 4) supabase.co URL 안에 password-like 토큰이 박혀 있는지.
git grep -nE "supabase\.co[^[:space:]\"]*password" -- ":(exclude)*/node_modules/*" ":(exclude)*/.venv/*"
```

**gitleaks 보강**: 본 PR 시점의 `tools/secret-scan` / `gitleaks` 룰셋에 위 4종 패턴이 모두 들어있는지는 단계 1 (CMP-573 머지 PR 또는 CMP-574 후속) 이 검증·갱신한다. 누락 시 PR 본문에 보강 커밋 링크를 첨부한다.

---

## 9. 검증 (본 PR 머지 전 self-check)

`AGENTS.md` 와 본 이슈의 "테스트/검증" 절을 만족하기 위한 self-check:

```powershell
# 1) supabase 스캐폴드가 들어왔다 (config.toml, .gitkeep 2개).
git ls-files supabase/

# 2) Neon 흔적은 본 PR 에서 건드리지 않았다.
git diff origin/dev...HEAD -- .github/workflows/neon-pr-branch.yml .github/workflows/ci.yml .github/workflows/deploy.yml docs/runbooks/neon-branches.md
# → 위 명령의 출력은 빈 줄이어야 한다 (단계 0 의 봉인 — Neon 무변경).

# 3) 평문 시크릿이 들어가지 않았다 (§8 의 확장 패턴 4종).
git grep -nE "sbp_[A-Za-z0-9]{40,}|sb_secret_[A-Za-z0-9]{20,}" supabase/ docs/
git grep -nE "eyJhbGciOi[A-Za-z0-9._-]{40,}" supabase/ docs/
git grep -nE "postgres(ql)?://[^[:space:]\"]*@[^[:space:]\"]*\.supabase\.(co|com|net)[^[:space:]\"]*" supabase/ docs/
git grep -nE "supabase\.co[^[:space:]\"]*password" supabase/ docs/
# → 네 명령 모두 결과 0건.

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

# 8) RLS 정책 완성 전 PostgREST 노출 봉인 (§7.2).
#     [api].enabled = false 이고 schemas 에 "public" 이 포함되지 않는다.
git grep -nE '^\[api\]|^enabled = false|^schemas = ' supabase/config.toml | grep -A2 '\[api\]'
# → enabled = false, schemas = ["graphql_public"].

# 9) OAuth callback redirect allow-list 봉인 (§4.7 sealed flow + Supabase
#    exact-match redirect 정책).
#     additional_redirect_urls 에 origin + /auth/callback + /** 가 localhost / 127.0.0.1
#     양쪽 모두 들어있다.
git grep -nE '/auth/callback"|/\*\*"' supabase/config.toml
# → 최소 4건: localhost/127.0.0.1 의 /auth/callback 와 /** 항목.

# 10) production-side Data API guard (§7.2 R5) 와 preview connection-string
#     노출 가드 (§7.3) 가 런북에 봉인되어 있다 — 단계 3 머지 게이트 의존.
git grep -nE '7\.2 R5|7\.3 C[1-4]|production Data API|connection-string 노출' docs/runbooks/supabase-branching.md
# → §6 단계 3 행, §3.2 A4, §7.2 R5, §7.3 표/게이트가 모두 매칭된다.

# 11) `schemas` 우회 가드 — [api].enabled = false 가 1차 SSOT 임을 명시.
git grep -nE 'public 노출 차단 가드로 무효|본 게이트의 SSOT 가 아니다' docs/runbooks/supabase-branching.md
# → §7.2 봉인 박스 2개 문구가 매칭된다.

# 12) staging deployment path (A1.2) + [remotes.staging] 봉인.
git grep -nE 'A1\.2 staging deployment path|\[remotes\.staging\]|SUPABASE_PROJECT_REF_STAGING' docs/runbooks/supabase-branching.md supabase/config.toml
# → A1.2 / [remotes.staging] / U5 STAGING 변수 모두 매칭.

# 13) Supabase-visible env wiring (§7.4 W-A~W-D + auth callback redirect_uri 봉인).
git grep -nE '7\.4 Supabase-visible env wiring|auth/v1/callback|supabase/\.env|W-[A-D]\b' docs/runbooks/supabase-branching.md supabase/config.toml
# → §7.4 표/게이트 + redirect_uri 봉인 주석 + .env 가드 매칭.

# 14) U7 noop migration 영구 보존 봉인 — revert 금지 명시.
git grep -nE 'noop migration 영구 보존|revert 하지 않는다|migration repair' docs/runbooks/supabase-branching.md
# → U7 본문 + repair 절차 매칭.
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

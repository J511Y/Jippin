# Runbook — Supabase GitHub integration + 브랜치 운영 (CMP-574 인도물 / CMP-603 cutover 반영)

- 정본 책임자: **DevOps Lead** · **SRE** 리뷰
- 관련: CMP-572 (Supabase 트랙 총괄), CMP-573 (Supabase 전환 ADR), CMP-574 (본 런북 초안), CMP-575 (DB migration), CMP-576 (Auth), CMP-577 (Web), **CMP-603 (CI/CD cutover — Neon workflow archive + Supabase wrapper)**
- 대체 대상: `docs/runbooks/neon-branches.md` §1~§3 (Neon branch 트리/운영). Neon 런북은 archive 배너 + 이력 참조용.
- 정책 정본: `docs/adr/0004-supabase-transition.md` (Proposed at time of CMP-603 cutover — CI/CD 측 cutover 는 본 PR 로 완료, ADR Accepted 는 CEO 결정 대기).
- 봉인 범위: 본 런북은 **GitHub branching ↔ Supabase branch 매핑·preview 정책·CI 워크플로우 책임** 을 봉인한다. Auth/DB/Web 트랙의 실제 마이그레이션 절차는 각 트랙 런북에 위임한다.

## ⚠ CMP-603 cutover 반영 (2026-06-02)

본 런북의 §6 "Neon workflow 단계적 deprecation 순서" 는 원래 4단계로 분리되었으나, **CMP-603 cutover PR 에서 단계 1~3 을 일괄 처리**했다. 결과:

- `.github/workflows/neon-pr-branch.yml` → `.github/workflows/_archive/neon-pr-branch.yml.archived` (비활성).
- `.github/workflows/deploy.yml::release-migrate` (Neon `DATABASE_URL` + `alembic upgrade head`) → 제거. `deploy.yml` 은 빌드 smoke + 어플리케이션 배포 스텁만 남는다. DB migration 은 Supabase GitHub Integration 단독 책임.
- `.github/workflows/ci.yml::migrate-check` (Alembic + `NEON_TEST_DATABASE_URL`) → Supabase SQL migration drift 가드 (model-only PR 차단) 로 재정의. §6.3.2 정본.
- `.github/workflows/supabase-status.yml` (wrapper) → 신규. path-filter deadlock 회피 + 실제 Supabase integration check polling. §6.3 정본.

§6 단계표는 이력 참조용으로 보존하되 "본 PR" 표기는 CMP-603 cutover 완료 기준으로 읽는다. Neon project 폐기 + 시크릿 일괄 삭제는 사용자 콘솔 작업 (본 런북 §3.1 후속 + Neon archive 런북).

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
| 기존 Neon workflow 처리 | **CMP-603 cutover 완료**. `neon-pr-branch.yml` archive, `deploy.yml::release-migrate` 제거, `ci.yml::migrate-check` Supabase drift 가드 재정의. 위 "CMP-603 cutover 반영" 박스 참조. |
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
- [ ] **A1.1** 같은 PR 에서 `[remotes.development].project_id` 를 `SUPABASE_PROJECT_REF_DEV` (development persistent branch 의 BRANCH PROJECT ID, U5 참고) 값으로 채운다. 본 절이 빠지면 development branch 를 대상으로 한 CLI 명령이 production 으로 잘못 흐른다. CLI 명령 시퀀스는 다음 둘 중 하나를 쓴다 (Supabase CLI 는 `--remote <name>` 플래그를 지원하지 않는다 — 정본: https://supabase.com/docs/reference/cli/introduction):<br/>① 새 셸: `supabase link --project-ref <DEV_BRANCH_PROJECT_REF>` 후 **`supabase db diff --linked`** / **`supabase db push`** 호출.<br/>② 또는 `supabase db push --db-url "postgres://...@<dev_branch_host>/postgres"` (DB connection string 직접 지정).<br/>**`--linked` / `--db-url` 봉인 (MUST).** `supabase db diff` 를 **plain (`supabase db diff`) 로 실행하면 local Postgres (Docker) 를 diff 대상으로 본다** — `link --project-ref` 가 적용된 remote branch 가 아니다 (Supabase CLI reference: https://supabase.com/docs/reference/cli/supabase-db-diff). 따라서 development/staging persistent branch 의 실제 schema 와 diff 하려면 **반드시 `supabase db diff --linked`** (linked remote 대상) 또는 **`supabase db diff --db-url "postgres://..."`** (connection string 직접 지정) 를 쓴다. 본 봉인 누락 시 CMP-575 가 stale local Docker DB 의 schema 로 migration 을 생성/검증하면서 "development branch 와 일치한다" 고 잘못 결론낼 수 있다. 같은 봉인은 §3.2 A1.2 staging path 에도 적용된다.
- [ ] **A1.2 staging deployment path (별도 봉인 — PoC 적용 채널).** staging persistent branch 는 §1 매핑에서 **GitHub 트리거 없음** (Supabase 콘솔에서만 수동 promote) 이므로 §7.1.1 G3 / §7.1.3 A5 / §7.1.4 O3 PoC 를 staging 에 적용할 GitHub Actions 자동화 경로가 존재하지 않는다. 대신 **로컬에서 Supabase CLI 로 직접 staging 에 적용하는 path** 를 정본화한다. 같은 PR (A1) 또는 별도 후속 PR 에서 다음을 수행:<br/>① `supabase/config.toml` 의 `[remotes.staging].project_id` 를 `SUPABASE_PROJECT_REF_STAGING` (U5 staging BRANCH PROJECT ID) 값으로 채운다. 본 PR (CMP-574) 시점에는 `jippin-staging-placeholder` 봉인.<br/>② **로컬 CLI 시퀀스 (PoC 적용 표준 절차).** 새 셸에서 다음을 차례로 실행한다:<br/>&nbsp;&nbsp;&nbsp;&nbsp;1. `supabase link --project-ref <STAGING_BRANCH_PROJECT_REF>`<br/>&nbsp;&nbsp;&nbsp;&nbsp;2. **검증 — `supabase db diff --linked`** (linked remote 가 staging 인지 확인 — A1.1 봉인). diff 결과가 예상한 staging 상태와 일치하지 않으면 link 가 잘못 걸린 것이므로 즉시 멈춤. plain `supabase db diff` 는 local Docker DB 를 diff 대상으로 보므로 사용 금지.<br/>&nbsp;&nbsp;&nbsp;&nbsp;3. `supabase db push` (SQL 마이그레이션 적용 — G2 `auth.identities` 트리거 SQL + `private.identity_link_intents` + `private.pending_terms_consents` + `before-user-created` Hook 함수 등이 staging 에 반영)<br/>&nbsp;&nbsp;&nbsp;&nbsp;4. `supabase config push` (가용 시 — `[auth.external.*]` 등 config 동기화. 미가용 시 Supabase 콘솔 staging project 에서 수동 동기)<br/>&nbsp;&nbsp;&nbsp;&nbsp;5. PoC 실행 후 `supabase link --project-ref <DEV_BRANCH_PROJECT_REF>` 로 셸 컨텍스트 복귀 (production ref 와 혼동 방지)<br/>③ **GitHub Actions 자동화 비범위.** 본 PR 시점에는 staging promote 를 GitHub Actions 로 자동화하지 않는다 (§1 봉인: GitHub 측 staging 트리거 없음). 자동화가 필요해지면 별도 ADR + workflow 추가 (예: `hotfix/*` 와 동일한 trigger 패턴으로 `staging-promote.yml` 도입) 가 정본.<br/>④ **PoC 결과 첨부 의무.** CMP-576/CMP-577 PR 본문에 위 ②.1~②.4 명령의 출력 캡처 (DB password / connection string redact 후) 와 PoC 결과 (사용자 분리 / Hook reject / linkIdentity 흐름) 를 첨부한다. 첨부 없는 PR 은 §7.1.4 O3 / O4 게이트로 머지 금지.
- [ ] **A2.** CMP-575 (DB 트랙) 가 Alembic → SQL migration 변환 결과를 `supabase/migrations/` 에 채운다.
- [ ] **A3.** CMP-576 (Auth 트랙) 이 `supabase/config.toml` 의 `[auth.external.*]` 를 켜고 **같은 PR 에서 `[auth].enable_signup` 글로벌 gate 를 `true` 로 함께 바꾼다** (글로벌 gate 가 false 면 OAuth signup 도 막힘). `[auth.email].enable_signup` 은 영구 false 유지. **OAuth signup gate (MUST — PR 머지 직전 봉인).** A3 PR 머지 직전에 §7.1.4 O1~O5 + §7.1.5 H1~H4 (41-시나리오 PoC + 파일 ⓪ `public.terms` 선행 + R15 #2~#6 정합 + R16 #1~#3 정합: **Hook event identity_data 부재 → trigger 로 위임, anonymous upgrade M-INTENT 강제 분기, Kakao trigger 의 version 컬럼은 각 term 의 active `public.terms.version`**) + §7.1.6 cron + §7.1.7 A-AUTH-1~A-AUTH-5 + §7.1.8 HK-REG-1~HK-REG-4 + §7.4 W-A~W-D + §7.1.1 G1~G3 (G2 ① 이 `is_anonymous + prior identity` 결합 분기) + §7.1.2 M-INTENT 모두 통과. **`supabase/config.toml` 의 `[storage].enabled = false` 명시** (wake R14 #2) + `[api].enabled = false` 봉인 (§7.2) 유지. 핵심 추가 항목: callback 의 expected_provider 는 **signed cookie marker 또는 path 분리** (wake R13 #6) 로 trusted source 도출, H2 함수 시그니처는 **`p_term_ids uuid[]` multi-term** 통일 (wake R13 #2), Kakao trigger 는 **`AFTER INSERT ON auth.identities`** 위치 (wake R13 #3), `private_owner` cross-schema GRANT 에 **`SELECT (id, is_anonymous, raw_app_meta_data, raw_user_meta_data) ON auth.users` + `SELECT (id, user_id, provider, identity_data) ON auth.identities`** 포함 (wake R13 #4). 미통과 시 PR 머지 금지. CMP-577 트랙이 `[auth].enable_anonymous_sign_ins=true` 로 전환하며 §7.1.3 PoC 절차 (A5) 를 함께 수행. 핵심: terms 화면 → backend `/api/terms/accept` 가 UI provider (`google` / `naver`) → **정본 provider id (`google` / `custom:naver` — wake R10 #3)** 매핑 후 server-only direct Postgres path 로 `create_pending_terms_consent` 호출 → cookie 발급 → no-cookie callback reject → direct PG validate (정본 id 매칭) → @supabase/ssr exchangeCodeForSession → `is_new_user`==true 면 consume_internal 이 다중 term_id 별 terms_consents INSERT + cross-schema GRANT 통해 public/auth 접근 → consume false 시 raw_app_meta_data marker UPDATE + session JWT signOut + cookie clear (`auth.admin.deleteUser` 절대 금지). **Kakao signup 은 Hook weak gate + `persist_kakao_sync_terms_consents` AFTER INSERT trigger 가 `terms_consents(source='kakao_sync')` 영속화 (wake R10 #5)**. 미통과 시 PR 머지 금지. CMP-577 트랙이 `[auth].enable_anonymous_sign_ins=true` 로 전환하며 §7.1.3 PoC 절차 (A5) 를 함께 수행.
- [ ] **A4.** §6 단계 1~3 에 따라 Neon workflow 를 단계적으로 제거하고 Supabase integration 으로 대체한다.<br/>**단계 1 진입 전 (선행 PR — MUST).** §6 단계표 + §6.2 required check 정합대로 **`.github/workflows/supabase-status.yml` wrapper (§6.3) + §7.3 C2 (connection-string redact + unit-test) 봉인 + branch protection 의 `supabase-status` required check 등록 까지 완료** 한 PR 이 **단계 1 의 `SUPABASE_BRANCHING_LIVE=true` 토글 PR 보다 먼저 머지**되어야 한다. wrapper 가 required 가 아닌 상태에서 Neon preview check 가 단계 1 토글로 꺼지면 **stage 1 ↔ stage 2 사이 required DB check 공백** 이 생긴다. wrapper 선행 PR 본문에 §6.3.1 컨텍스트 식별 절차 캡처 + §7.3 C2 unit-test 결과 첨부 의무. CMP-575 또는 별도 후속 (DevOps) 가 wrapper PR 의 소유자.<br/>**단계 1 PR.** wrapper 가 이미 required 인 상태에서 `SUPABASE_BRANCHING_LIVE=true` 토글 + Neon workflow 의 게이트 추가 (§6.1) 만 수행.<br/>**단계 2 PR.** `ci.yml::migrate-check` 를 §6.3.2 Supabase SQL migration drift guard 로 재정의. 본 PR 은 wrapper 자체를 새로 추가하지 않는다 (이미 단계 1 진입 전 PR 에 있음).<br/>**단계 3 PR.** 머지 직전 **§3.1 U7 (production deploy/migration toggle ON) 검증 결과 + §7.2 R5 (production Data API exposed schemas 에 `public` 미포함) 확인 결과 + §7.1.7 A-AUTH (production Auth config Dashboard / `supabase config push` 적용 확인 — wake R9 #3) + §7.3 C3 (preview PR 의 코멘트/본문에서 connection string / key / JWT 패턴 0건) self-check 결과** 4종을 모두 PR 본문에 첨부해야 머지 금지 게이트가 해제된다.

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

상태는 **repo-side 변경** 과 **operational activation (ADR Accepted / Supabase 콘솔 게이트 / branch protection)** 두 축으로 분리해 읽는다. CMP-603 은 repo-side 만 처리하며, ADR-0004 Accepted / 콘솔 토글 / required check 등록은 별도 사용자 작업이다.

| 단계 | 원래 트리거 | 작업 범위 | 책임 이슈 | Repo-side 상태 | Operational activation 상태 |
|---|---|---|---|---|---|
| **단계 0 (CMP-574)** | CMP-574 PR 머지 | `supabase/` 스캐폴드 + 본 런북 추가. Neon workflow 무변경. | CMP-574 | ✅ 머지 완료 | ✅ — 본 단계는 콘솔 게이트 없음 |
| **단계 1** | (원래) CMP-573 ADR-0004 Accepted + wrapper workflow 머지 | Neon workflow gating 또는 archive. wrapper workflow 추가. | CMP-603 | ✅ repo-side 완료 (`neon-pr-branch.yml` archive + `supabase-status.yml` 추가) | ⏳ 대기: (a) ADR-0004 Accepted (CEO), (b) branch protection 의 required check 에 `supabase-status` 등록, (c) §3.1 U6 의 `SUPABASE_INTEGRATION_CHECK_NAME` 변수 등록 |
| **단계 2** | 단계 1 직후 | `ci.yml::migrate-check` 를 Supabase SQL migration drift guard 로 재정의 (§6.3.2). | CMP-603 | ✅ repo-side 완료 (Neon secret 의존 제거, 모델↔SQL drift 정적 가드 활성) | ⏳ 대기: 첫 model+SQL PR 로 가드 작동 확인 |
| **단계 3** | (원래) 단계 2 후 + §3.1 U7 + §7.2 R5 + §7.3 C3 통과 | `deploy.yml::release-migrate` 의 Neon 의존 제거. Neon archive 배너 강화. Neon project 폐기 + 시크릿/변수 일괄 삭제. | CMP-603 (repo) / 사용자 (콘솔) | ✅ repo-side 완료 (release-migrate 잡 제거, archive 배너 갱신, Neon 시크릿/변수 GitHub Settings 삭제 체크리스트 명문화) | ⏳ 대기: (a) §3.1 U7 production deploy/migration toggle ON 검증, (b) §7.2 R5 production Data API exposed schemas 봉인 확인, (c) §7.3 C3 preview connection-string 노출 0건 확인, (d) Neon project 자체 폐기 + GitHub Settings 의 Neon 시크릿/변수 삭제, (e) Neon archive 런북을 `docs/runbooks/_archive/` 로 이동. |

> **읽는 법 (MUST).** "Repo-side 완료" 는 워크플로우/문서 변경이 PR 머지로 끝났다는 뜻이며, 단계 1 원래 트리거였던 **ADR-0004 Accepted 결정 자체는 본 PR 시점에 여전히 Pending** 이다 (`docs/adr/0004-supabase-transition.md` 상태: Proposed). 단계 3 의 operational gate (U7 / R5 / C3) 도 Supabase 콘솔 연결 후에 검증된다. 본 표를 근거로 "ADR-0004 가 Accepted 됐다" / "U7·R5·C3 가 통과됐다" / "Neon project 가 폐기됐다" 고 후속 트랙이 가정하면 안 된다. 특히 [`supabase-web-auth.md`](supabase-web-auth.md) 의 Phase 2 legacy cleanup 가드는 ADR-0004 Accepted 가 명시 조건 — 본 표가 "단계 1 완료" 라고 표시한다고 cleanup 을 시작하지 말 것.

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
| G2. **DB 트리거 fallback — automatic identity attach 차단 (discriminator 필수).** `auth.identities` BEFORE INSERT 트리거로 "기존 user 에 다른 provider identity 가 자동으로 붙는" 경로만 reject 하고, **새 user 행을 만들어 attach 하는 경로는 허용** 한다. duplicate email user row 자체는 막지 않는다 (§4.7 #9 정합). **단순 "기존 user + 새 provider = reject" 룰만으로는 §7.1.2 manual `linkIdentity()` / §7.1.3 anonymous→OAuth upgrade 흐름도 동시에 reject 되어 정책이 깨진다** — automatic attach 와 manual link 는 둘 다 `auth.identities` 에 새 row 를 추가하므로 트리거 입장에서 구분 불가. 따라서 **명시적 manual-link intent marker** 가 SSOT 다 (§7.1.2 봉인). 트리거 흐름:<br/>① `INSERT INTO auth.identities` 가 들어오면 트리거가 **새 user 생성 흐름인지** 확인 — `auth.identities.user_id` 가 `auth.users(id)` 참조 (FK) 이므로 identity insert 시점에는 user row 가 이미 존재한다. 따라서 "같은 transaction 의 `auth.users` insert 동행" 만으로는 신규 user 흐름과 manual link 흐름을 구분할 수 없다 (wake R15 #5). **관측 가능한 new-user discriminator + anonymous-upgrade 분리 (wake R16 #2)**:<br/>&nbsp;&nbsp;• `auth.users.is_anonymous` 조회 + `EXISTS prior identity` 결합 분기:<br/>&nbsp;&nbsp;&nbsp;&nbsp;**(i) `is_anonymous = false` AND prior identity 0건** → **신규 OAuth signup** (Supabase Auth 가 user + 첫 identity 를 같은 흐름에서 insert) → 허용. M-INTENT 불요.<br/>&nbsp;&nbsp;&nbsp;&nbsp;**(ii) `is_anonymous = true` AND prior identity 0건** → **anonymous → OAuth upgrade** (Phase 2 §7.1.3 A2). prior identity 가 없어도 본 경로는 manual link intent 보유 필수 → 아래 ② 의 M-INTENT 검사로 진입 (R16 #2 봉인 — anonymous user 가 prior identity 0 으로 ① 통과해 audit guard 우회하지 않도록).<br/>&nbsp;&nbsp;&nbsp;&nbsp;**(iii) prior identity 존재 (≥1건)** → 기존 user 에 추가 identity 가 붙는 경로 → 아래 ② 의 M-INTENT 검사로 진입.<br/>SQL 흐름:<br/>```sql<br/>DECLARE v_is_anonymous boolean; v_prior_count int;<br/>SELECT is_anonymous INTO v_is_anonymous FROM auth.users WHERE id = NEW.user_id;<br/>SELECT count(*) INTO v_prior_count FROM auth.identities WHERE user_id = NEW.user_id AND id <> NEW.id;<br/>IF v_is_anonymous = false AND v_prior_count = 0 THEN<br/>  RETURN NEW;  -- (i) 신규 OAuth signup — 허용.<br/>END IF;<br/>-- (ii) anonymous upgrade + (iii) manual link 모두 ② M-INTENT 검사.<br/>```<br/>본 discriminator 는 `auth.users.is_anonymous` + `auth.identities` row 만으로 관측 가능 — `auth.uid()` / 동행 INSERT 시점 의존 없음. **anonymous → OAuth upgrade (§7.1.3 A2) 흐름 봉인**: `linkIdentity()` 호출 직전 backend 가 `private.identity_link_intents` 에 row INSERT (M-INTENT, §7.1.2). trigger 가 (ii) 분기에서 M-INTENT active row 검증 → manual link 로 인정 + consume. 미발급 시 reject — anonymous precheck user 의 자동 OAuth attach 우회 차단. cross-schema GRANT (`SELECT is_anonymous ON auth.users TO private_owner` 는 §7.1.5 H2 파일 ① 에 이미 포함).<br/>한계: 같은 transaction 의 race (신규 user 의 첫 identity insert 직후 매우 짧은 시간 안에 두 번째 identity insert) 가 manual link intent 없이 진행되면 두 번째 insert 가 prior identity (= 방금 추가된 첫 identity) 를 보고 ② 단계 reject 한다. 정상 흐름에서는 M-INTENT 발급이 우선이므로 race window 자체가 매우 좁다.<br/>② 기존 user (`auth.users` row 가 이미 있음) 에 새 provider identity 가 붙는 경우 → **§7.1.2 의 `private.identity_link_intents` 테이블 (M-INTENT)** 에서 `(NEW.user_id, NEW.provider)` 매칭 + active (consumed_at IS NULL + expires_at > now()) row 가 있으면 manual link 로 간주 → 허용 + intent row consume. **`auth.uid()` 미사용** (wake R13 #1) — `auth.identities` insert 는 Supabase Auth (postgres role) 가 수행하므로 트리거 컨텍스트에서 `auth.uid()` 가 NULL. `NEW.user_id` 가 트리거 입력의 정본 user 식별자.<br/>③ intent row 없음 → automatic attach 로 간주 → reject (`raise exception 'automatic identity attach blocked'`).<br/>④ anonymous → OAuth upgrade (§7.1.3 A2) 도 같은 intent marker 를 사용 — anonymous session 에서 `linkIdentity()` 호출 직전에 intent row INSERT.<br/>실제 SQL/조건절은 CMP-576 가 정본화: `supabase/migrations/<timestamp>_block_auto_email_attach.sql` + `supabase/migrations/<timestamp>_identity_link_intents.sql`. | CMP-576 (DB 트리거 SQL + intent 테이블) | CMP-576 PR |
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
| **M-INTENT. Manual link intent marker (MUST — §7.1.1 G2 discriminator).** Manual `linkIdentity()` (M1) / anonymous→OAuth upgrade (§7.1.3 A2) 호출 **직전 N초** (예: 5분) 안에 `private.identity_link_intents (intent_id uuid PK DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES auth.users(id), provider text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL DEFAULT now() + interval '5 minutes', consumed_at timestamptz NULL)` 에 row INSERT (현재 인증된 user 의 user_id + 추가할 provider).<br/>**관측 가능한 discriminator (wake R11 #2 + R13 #1 — `NEW.user_id` 정본).** §7.1.1 G2 트리거가 `auth.identities` BEFORE INSERT 시점에 `NEW.user_id` (트리거 입력의 정본 user 식별자) + `NEW.provider` 매칭의 active intent (consumed_at IS NULL + expires_at > now()) 가 존재하는지 검사. 매칭 있으면 manual link → 허용 + `UPDATE consumed_at`. 매칭 없으면 automatic attach 로 간주 → reject. **nonce 검증은 사용하지 않는다** (PKCE state 는 Supabase 자체 관리, hook payload 노출 안 됨). 정본 discriminator 는 `(NEW.user_id, NEW.provider, active intent 존재)` 3종 매칭. 관측 가능한 이유:<br/>&nbsp;&nbsp;• `NEW.user_id` = `auth.identities` insert row 의 user_id 컬럼 — 트리거 입력 정본. **`auth.uid()` 미사용** (wake R13 #1) — `auth.identities` insert 가 Supabase Auth (postgres role) 컨텍스트에서 실행되므로 트리거 시점에 `auth.uid()` 가 NULL.<br/>&nbsp;&nbsp;• `NEW.provider` = `auth.identities` insert row 의 provider 컬럼 — 트리거가 직접 접근.<br/>&nbsp;&nbsp;• `expires_at > now()` 시간 윈도우 (5분) 가 stale provider intent 의 자동 attach 우회 차단.<br/>**한계**: 같은 user 가 5분 안에 manual link + automatic attach 시도 시 트리거가 두 경로를 구분 못 함 (둘 다 같은 user_id+provider). 본 케이스는 §7.1.1 G3 PoC (Google + Kakao 같은 verified email → 별도 user) 가 별도 가드 — automatic attach 는 다른 user_id 에서 일어나므로 본 case 에선 `NEW.user_id` 매칭 실패.<br/>RLS ON, `private` schema (§7.1.5 H2 동일 권한 모델). **insert 는 `public.create_identity_link_intent(p_target_user_id uuid, p_provider text)` SECURITY DEFINER 함수 호출만 허용** (owner = `private_owner`). 함수 본문이 `p_target_user_id` 가 호출자의 정당한 user id 인지 검증 — `auth.uid()` 가 가용한 컨텍스트 (RLS 기반 RPC) 에서는 함수 안에서 `IF auth.uid() <> p_target_user_id THEN RAISE EXCEPTION ... END IF` 로 보강, FastAPI 백엔드가 service_role 로 호출하는 경로는 backend 가 자체 인증된 user id 만 전달. client (anon JWT, 인증된 user 자신) 와 FastAPI 양쪽 모두 본 함수만 호출. `service_role` 직접 INSERT 는 비정본 (REVOKE). | CMP-576 (intent 테이블 + SECURITY DEFINER 함수) + CMP-577 (호출) |

본 PR (CMP-574, 단계 0) 은 토글만 봉인하고, 위 M1~M3 + M-INTENT 의 실제 코드/감사 SQL 은 CMP-576/CMP-577 트랙이 정본화한다.

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
| O1. **시크릿 등록 완료 (Vault 비의존 — wake R14 #1 + R17 #1 재봉인).** GitHub Secrets (`SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID`/`_SECRET`, `_KAKAO_*`, Naver custom OIDC) + **Supabase branch config env secrets (§7.4 W2 = `supabase secrets set --project-ref <REF> KEY=value` 또는 `--env-file <encrypted.env>`)** 로 등록. **Project Settings → Vault (Postgres `vault.secrets` 저장소) 사용 금지** — Vault 는 DB 안 application 시크릿용이지 `config.toml env()` 해석 채널 아님 (§7.4 정본 + H4 ㊸ + §9 #72). 콘솔에서 provider 가 활성화돼 있고 client_id/secret 이 `auth.external.*.secret = env(...)` 의 참조 변수로 등록됨. PR 본문에 `supabase secrets list --project-ref <REF>` 출력 (key 이름만, 값 마스킹) 첨부 의무. **vault key 이름** 첨부 지시는 stale — 본 항목은 §7.4 W-B 와 동일 정본. | CMP-576 (PR 본문에 secrets list 출력 첨부, 값은 절대 첨부 금지) | 본 PR 미적용 |
| O2. **`redirect_uri` 봉인 — Supabase Auth callback 만 (환경별 parameterize MUST).** `[auth.external.*].redirect_uri` 는 **provider 콘솔에 등록되고 provider 가 인가코드를 보내는 OAuth callback URL** 이다. Supabase 공식 예시 흐름 (provider → Supabase `/auth/v1/callback` → app `/auth/callback`) 에 따라 본 값은 **반드시 Supabase Auth callback URL** 이어야 하지만, **production / development / staging / local 각 환경마다 다른 BRANCH PROJECT REF 의 callback URL 을 가리켜야 한다** — 즉 환경별 parameterize 필수. 단일 PROD URL 로 고정하면 staging PoC 가 production Auth 로 인가코드를 보내 staging 검증 자체가 무효화된다 (정본: https://supabase.com/docs/guides/auth/social-login + https://supabase.com/docs/guides/local-development/cli/config#auth-external-provider-redirect-uri).<br/>**환경별 정본 값.**<br/>① **production:** `https://<SUPABASE_PROJECT_REF_PROD>.supabase.co/auth/v1/callback` (production branch project ref — `supabase projects list` 의 Reference ID, §3.1 U5)<br/>② **development persistent branch:** `https://<SUPABASE_PROJECT_REF_DEV>.supabase.co/auth/v1/callback` (development BRANCH PROJECT ID — `supabase --experimental branches list` `development` 행, §3.1 U5)<br/>③ **staging persistent branch:** `https://<SUPABASE_PROJECT_REF_STAGING>.supabase.co/auth/v1/callback` (staging BRANCH PROJECT ID, §3.1 U5)<br/>④ **local (`supabase start`):** `http://127.0.0.1:54321/auth/v1/callback` (Supabase local Kong 포트 정본)<br/>**적용 방식.** CMP-576 PR 은 `[auth.external.*].redirect_uri = env(SUPABASE_AUTH_EXTERNAL_REDIRECT_URI)` 로 변수화하고 W1~W4 채널 (§7.4) 별로 환경 값 등록 — root `.env` 에 local 값, Supabase 콘솔/`supabase secrets set` 에 prod/dev/staging 값. provider 콘솔 (Google Cloud / Kakao Developers / Naver Developers) 의 Authorized redirect URIs 에는 **위 ①~④ 4개를 모두 등록**해야 환경별 PoC 와 production 운영이 모두 통과한다. **`site_url`/`additional_redirect_urls`/app `/auth/callback` 같은 app 도메인 값을 절대 넣지 않는다** — 그러면 provider 가 인가코드를 Next.js 로 직접 보내 Supabase Auth 가 code 교환을 못 한다. app callback 매칭은 §3.1 `site_url` + `additional_redirect_urls` 가 책임. | CMP-576 | 본 PR 미적용 |
| O3. **§7.1.1 G1~G3 통과.** automatic identity linking 가드 (콘솔 설정 + DB 트리거 + PoC) 가 staging branch 에서 검증. 미통과 상태로는 provider 활성화 금지. | CMP-576 | 본 PR 미적용 |
| O4. **§4.7 sealed terms flow 보장 — §7.1.5 정본 redirect.** **본 항목은 §7.1.5 (gate-before-exchange + cookie-required + direct Postgres + Hook weak gate) 정본을 그대로 가리키며 본 셀에서는 구현 지시를 반복하지 않는다.** 이전 revision 의 "Hook 이 유일한 차단점" / "callback 에서 `auth.admin.deleteUser` 호출" 지시는 **stale 이며 비정본** — 절대 구현 경로로 복사 금지 (PnPa / R7 #3 / R7 #4 봉인). 본 게이트의 정본 차단 구성은:<br/>(a) **Strong gate = §7.1.5 H3 의 gate-before-exchange + cookie-required + direct Postgres connection 패턴.** Hook 은 weak gate (Kakao 분기 + google/naver allow). callback Route Handler 가 cookie 검사 → `validate_pending_terms_consent` (direct Postgres) → false 시 exchange 미호출 → user 생성 0건. true 시 cookie-backed `@supabase/ssr` server client 의 `exchangeCodeForSession` → `is_new_user == true` 면 `consume_pending_terms_consent_internal` (direct Postgres) 호출. **`auth.admin.deleteUser` 절대 호출 금지** — 미동의 user 는 §7.1.6 cron (raw_app_meta_data marker user + is_anonymous=false) 만 책임.<br/>(b) **Hook 권한/cross-schema GRANT.** Hook 함수의 `private` schema + `supabase_auth_admin` 만 EXECUTE + cross-schema GRANT (private_owner ↔ public.terms / public.terms_consents / auth.users) 봉인. 자세한 SQL 은 **§7.1.5 H2** 정본.<br/>(c) **자동 linking 우회 차단.** §7.1.1 G2 DB 트리거 + §7.1.2 M-INTENT 마커. (c) 미적용 시 (a) hook reject 가 "기존 user 에 identity attach" 우회로 빠질 수 있음.<br/>(d) **PoC 결과** — §7.1.5 H4 의 45-시나리오 (㉒~㉕ raw_app_meta_data / 다중 term_id / server-only mint / cross-schema GRANT + ㊱~㊷ Kakao callback/dedupe/discriminator/version + ㊸~㊻ Vault 제외 / HK-REG-3 trigger / term-version per-term / Kakao agreed-tag mapping wake R17 정정 포함) 전부 통과 캡처 첨부 의무. CMP-576 PR 본문 첨부 미누락 PR 은 본 게이트로 reject. | CMP-576 + CMP-577 (Web) + CMP-575 (RLS policy + cron) | 본 PR 미적용 |
| O5. **anonymous → OAuth upgrade 흐름 분리.** §7.1.3 의 phase gate 가 Phase 2 진입 전이면 `signInAnonymously()` 흐름을 사용자 UI 에 노출하지 않는다. OAuth signup 만 활성화. Phase 2 진입은 ADR-0004 가 따로 봉인. | CMP-577 | 본 PR 미적용 |

본 PR (CMP-574, 단계 0) 은 `[auth].enable_signup = false` + 모든 `[auth.external.*].enabled = false` 봉인을 유지한다. CMP-576 PR 머지 직전에 본 §7.1.4 의 O1~O5 결과를 PR 본문에 첨부하고 통과시킨다. 미통과 PR 은 Web/Auth required check (단계 2 후속) 와 본 런북 §3.2 A3 봉인으로 머지 금지.

#### 7.1.5 SQL / HTTP Auth Hook 봉인 (`before-user-created` 구현 정본)

§7.1.4 O4 (a) 가 가리키는 Hook 의 실제 구현은 다음 4개 게이트를 모두 통과해야 동작한다. 함수 정의만으로 Hook 이 작동한다고 가정한 PR 은 본 게이트로 reject. Supabase 의 Auth Hook 두 가지 종류 — **SQL (Postgres function) Hook** 과 **HTTP (Edge Function) Hook** — 중 어느 쪽을 쓰든 본 4개 봉인은 동일하게 적용한다 (정본: https://supabase.com/docs/guides/auth/auth-hooks).

| 게이트 | 조건 | 책임 |
|---|---|---|
| H1. **Hook 종류 선택 + 가용성 확인.** **SQL Hook** 은 Postgres function 으로 구현해 빠르고 RLS 검사를 직접 통과하지만 한정된 SQL 환경에서만 동작 (외부 HTTP 호출 불가). **HTTP Hook** 은 Edge Function 으로 외부 시스템 (Vault, third-party) 호출 가능하지만 latency + 별도 인증 (`SUPABASE_AUTH_HOOK_*_SECRET`) 봉인 필요. **본 프로젝트는 internal terms_consent 만 조회하면 충분하므로 SQL Hook 이 1차 권장**. 가용성 확인: `before-user-created` 는 Supabase Pro plan 이상 (또는 self-hosted) 에서 사용 가능 (정본: https://supabase.com/docs/guides/auth/auth-hooks#availability). Free plan 환경에서 hook 등록을 시도하면 콘솔/CLI 가 거부함을 사전 확인. | CMP-576 |
| H2. **권한/역할 봉인 — Hook 전용 `private` schema + `supabase_auth_admin` 만 EXECUTE + SECURITY DEFINER insert 채널 (MUST).** Hook 함수와 데이터를 **`public` 이 아닌 `private` schema** (Supabase 정본 권장: https://supabase.com/docs/guides/auth/auth-hooks#developing) 에 둔다. `public` 에 두면 R3 (§7.2) 가 `[api].enabled=true` 로 바뀌는 순간 hook 함수가 PostgREST RPC 로 노출돼 클라이언트가 terms-gate 를 외부 실행/probe 할 수 있다. Postgres 는 default 로 `PUBLIC` role 에 `EXECUTE` 를 부여하므로 GRANT 만으로 충분하지 않고 **명시 REVOKE 동행 필수**.<br/>**마이그레이션 순서 봉인 (MUST — 객체 생성 → GRANT/REVOKE 순서).** Postgres GRANT/REVOKE/POLICY 는 대상 객체가 이미 존재해야 실행 가능. 따라서 마이그레이션 파일은 다음 순서로 분리:<br/>&nbsp;&nbsp;&nbsp;&nbsp;**파일 ⓪ (선행 — wake R14 #3) — `_<ts>_public_terms.sql`.** `public.terms (id uuid PK, code text UNIQUE NOT NULL, version text NOT NULL, is_active boolean NOT NULL DEFAULT true, is_required boolean NOT NULL DEFAULT true, created_at, updated_at, ...)` 테이블 + 기본 row (`service_terms`, `privacy_policy`, ...) 시드. `apps/api/src/models/auth.py::TermsConsent.term_id` 는 현재 `Text` 이지만 본 H2 봉인의 SECURITY DEFINER 함수가 `JOIN public.terms USING (id)` (uuid) 형태로 호출하므로 **UUID PK `public.terms` 테이블이 H2 봉인의 전제**. **본 파일은 §7.1.5 H2 의 ① 보다 먼저** 머지되어야 한다. CMP-575 (DB 트랙) 가 정본화 — Alembic → Supabase SQL 변환 시 본 테이블을 함께 정의. **공통 봉인 (UUID vs text term_id)**: H3 본문의 `consume_pending_terms_consent_internal` 가 `terms_consents.term_id` 에 uuid 를 insert 하려면 `apps/api/src/models/auth.py::TermsConsent.term_id` 도 UUID 로 정정 필요 — CMP-575 PR 이 본 정정 + alembic migration 동행. 본 PR (CMP-574) 시점에는 `apps/api/src/models/` 무변경 (§9 self-check #2), CMP-575 PR 이 모델 + DB 정합화.<br/>&nbsp;&nbsp;&nbsp;&nbsp;**파일 ①** `_<ts>_private_schema.sql` — `CREATE SCHEMA IF NOT EXISTS private` + `private_owner` role (`BYPASSRLS NOLOGIN`) 생성 + 스키마 default `REVOKE ALL ... FROM anon, authenticated, service_role, PUBLIC` + `ALTER DEFAULT PRIVILEGES`.<br/>&nbsp;&nbsp;&nbsp;&nbsp;**파일 ②** `_<ts>_pending_terms_consents.sql` — 테이블 정의 (§7.1.5 H3 컬럼) + `ALTER TABLE ... OWNER TO private_owner` + `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` + `ALTER TABLE ... FORCE ROW LEVEL SECURITY` + REVOKE/GRANT + **RLS policy 명시** (`supabase_auth_admin` 용 SELECT/UPDATE policy — wake#3 봉인).<br/>&nbsp;&nbsp;&nbsp;&nbsp;**파일 ③** `_<ts>_identity_link_intents.sql` — 동일 패턴 (테이블 + RLS + RLS policy + GRANT/REVOKE).<br/>&nbsp;&nbsp;&nbsp;&nbsp;**파일 ④** `_<ts>_pending_terms_consent_fns.sql` — SECURITY DEFINER 함수 3개 (모두 multi-term 시그니처 — wake R13 #2):<br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;• `public.create_pending_terms_consent(p_provider text, p_terms_version text, p_term_ids uuid[]) RETURNS uuid` — terms 화면이 backend (server-only) 호출, `consent_token` 발급.<br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;• `public.validate_pending_terms_consent(p_token uuid, p_expected_provider text) RETURNS boolean` — callback Route Handler 가 exchange 전 호출 (service_role only).<br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;• `public.consume_pending_terms_consent_internal(p_token uuid, p_provider text, p_user_id uuid) RETURNS boolean` — exchange 후 호출 (service_role only). 본 함수가 **단일 conditional UPDATE + `unnest(term_ids)` 기반 다중 `terms_consents` INSERT 를 동일 transaction 으로 atomic 수행**. owner = `private_owner` (`private` schema 접근권 + RLS bypass).<br/>&nbsp;&nbsp;&nbsp;&nbsp;**파일 ⑤** `_<ts>_create_identity_link_intent_fn.sql` — M-INTENT 발급 SECURITY DEFINER 함수.<br/>&nbsp;&nbsp;&nbsp;&nbsp;**파일 ⑥** `_<ts>_before_user_created_terms_gate.sql` — Hook 함수 (weak gate — Kakao 분기 + google/naver allow) + 함수 자체 `REVOKE EXECUTE FROM PUBLIC, anon, authenticated, service_role` + `GRANT EXECUTE ... TO supabase_auth_admin`.<br/>위 순서를 깨서 파일 ①·② 의 GRANT/POLICY 가 테이블 생성보다 먼저 실행되면 `relation "private.pending_terms_consents" does not exist` 로 fail. CMP-576 PR 본문에 본 파일 순서 캡처 (파일명 timestamp 정렬) 첨부 의무.<br/>**파일 ⓪~⑦ 의 표준 SQL 블록 (의미만 — 실 SQL 은 CMP-575/CMP-576 PR 정본).**<br/>```sql<br/>-- 파일 ⓪ (선행 — public.terms UUID PK 테이블, CMP-575 정본화 — wake R14 #3).<br/>-- 본 테이블 미정의 시 H2 의 create_pending_terms_consent / consume_pending_terms_consent_internal<br/>-- 가 `relation "public.terms" does not exist` 로 fail. 파일 ① 보다 먼저 머지.<br/>CREATE TABLE IF NOT EXISTS public.terms (<br/>  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),<br/>  code text UNIQUE NOT NULL,         -- 예: 'service_terms', 'privacy_policy'<br/>  version text NOT NULL,<br/>  is_active boolean NOT NULL DEFAULT true,<br/>  is_required boolean NOT NULL DEFAULT true,<br/>  created_at timestamptz NOT NULL DEFAULT now(),<br/>  updated_at timestamptz NOT NULL DEFAULT now()<br/>);<br/>INSERT INTO public.terms (code, version, is_active, is_required) VALUES<br/>  ('service_terms', '1.0', true, true),<br/>  ('privacy_policy', '1.0', true, true)<br/>ON CONFLICT (code) DO NOTHING;<br/>-- CMP-575 PR 이 apps/api/src/models/auth.py::TermsConsent.term_id 도 Text → UUID 로 정정<br/>-- + FK 추가 (term_id REFERENCES public.terms(id) ON DELETE RESTRICT).<br/><br/>-- 파일 ⓪.5 (선행 — Kakao tag ↔ local term mapping, CMP-575 정본화 — wake R17 #4).<br/>-- Kakao Sync 응답의 tag (e.g. "service", "privacy", "marketing") 와 local public.terms.id<br/>-- 매핑. §7.1.5 H3 파일 ⑦ 의 persist_kakao_sync_terms_consents trigger 가 본 매핑으로<br/>-- agreed=true 인 tag → 해당 public.terms 에만 consent row 영속화 (subset/disagreed/revoked 차단).<br/>CREATE TABLE IF NOT EXISTS public.kakao_term_mapping (<br/>  kakao_tag text PRIMARY KEY,<br/>  public_term_id uuid NOT NULL REFERENCES public.terms(id) ON DELETE RESTRICT,<br/>  is_required boolean NOT NULL DEFAULT true,<br/>  created_at timestamptz NOT NULL DEFAULT now()<br/>);<br/>-- 초기 매핑 시드 — CMP-576 PoC 시점에 Kakao 응답 실측으로 정정.<br/>INSERT INTO public.kakao_term_mapping (kakao_tag, public_term_id, is_required)<br/>SELECT 'service', id, true FROM public.terms WHERE code = 'service_terms'<br/>ON CONFLICT (kakao_tag) DO NOTHING;<br/>INSERT INTO public.kakao_term_mapping (kakao_tag, public_term_id, is_required)<br/>SELECT 'privacy', id, true FROM public.terms WHERE code = 'privacy_policy'<br/>ON CONFLICT (kakao_tag) DO NOTHING;<br/>-- private_owner 대상 GRANT 는 아직 role 이 없으므로 여기서 실행하지 않는다.<br/>-- 파일 ① 에서 private_owner 를 만든 직후 GRANT SELECT ON public.kakao_term_mapping 을 적용한다.<br/><br/>-- 파일 ① (private schema + cross-schema 권한 봉인 — wake#4/B-6o).<br/>CREATE SCHEMA IF NOT EXISTS private;<br/>CREATE ROLE private_owner NOLOGIN BYPASSRLS;  -- SECURITY DEFINER 함수 owner + RLS bypass.<br/>-- private schema 자체 봉인.<br/>REVOKE ALL ON SCHEMA private FROM PUBLIC, anon, authenticated, service_role;<br/>GRANT USAGE ON SCHEMA private TO private_owner, supabase_auth_admin;<br/>ALTER DEFAULT PRIVILEGES IN SCHEMA private REVOKE ALL ON TABLES   FROM PUBLIC, anon, authenticated, service_role;<br/>ALTER DEFAULT PRIVILEGES IN SCHEMA private REVOKE ALL ON FUNCTIONS FROM PUBLIC, anon, authenticated, service_role;<br/>-- private_owner 는 SECURITY DEFINER 함수가 touch 하는 public.terms / public.terms_consents / auth.users<br/>-- 에 접근 권한 필요 (wake#4/B-6o — owner role 이 private 만 보이면 permission denied).<br/>GRANT USAGE ON SCHEMA public TO private_owner;<br/>GRANT SELECT ON TABLE public.terms TO private_owner;<br/>GRANT SELECT ON TABLE public.kakao_term_mapping TO private_owner;<br/>GRANT INSERT ON TABLE public.terms_consents TO private_owner;<br/>GRANT USAGE ON SCHEMA auth TO private_owner;<br/>-- marker UPDATE 의 predicate column id 에 대한 SELECT 권한 + raw_app_meta_data UPDATE 권한 (wake R13 #4).<br/>-- WHERE id = $1 절은 SELECT(id) 가 필요 — UPDATE(col) 권한만으로는 predicate 평가 불가.<br/>GRANT SELECT (id, is_anonymous, raw_app_meta_data, raw_user_meta_data) ON TABLE auth.users TO private_owner;<br/>GRANT UPDATE (raw_app_meta_data) ON TABLE auth.users TO private_owner;  -- marker set 용.<br/>-- auth.identities 권한 — Kakao Sync after-create trigger (§7.1.5 H3 파일 ⑦) 가 provider/user 식별자와 필요 시 fallback identity_data 를 읽음.<br/>GRANT SELECT (id, user_id, provider, identity_data) ON TABLE auth.identities TO private_owner;<br/>-- 위 GRANT 는 CMP-575 RLS 정본화 시점에 변경되어선 안 됨 — definer 함수가 fail-open 되지 않도록.<br/><br/>-- 파일 ② (테이블 + RLS + policy + 권한).<br/>CREATE TABLE private.pending_terms_consents (...);<br/>ALTER TABLE  private.pending_terms_consents OWNER TO private_owner;<br/>ALTER TABLE  private.pending_terms_consents ENABLE ROW LEVEL SECURITY;<br/>ALTER TABLE  private.pending_terms_consents FORCE ROW LEVEL SECURITY;<br/>REVOKE ALL   ON TABLE private.pending_terms_consents FROM PUBLIC, anon, authenticated, service_role;<br/>GRANT  SELECT, UPDATE (consumed_at, provider_subject) ON TABLE private.pending_terms_consents TO supabase_auth_admin;<br/>-- RLS policy 명시 (wake#3 — GRANT 만으로 RLS bypass 안 됨).<br/>CREATE POLICY pending_terms_consents_auth_admin_select<br/>  ON private.pending_terms_consents FOR SELECT TO supabase_auth_admin USING (true);<br/>CREATE POLICY pending_terms_consents_auth_admin_update<br/>  ON private.pending_terms_consents FOR UPDATE TO supabase_auth_admin USING (true) WITH CHECK (true);<br/>-- private_owner (SECURITY DEFINER 함수 owner) 는 BYPASSRLS 로 별도 policy 불요.<br/>-- anon/authenticated/service_role 는 policy 없음 — 모든 row 차단.<br/><br/>-- 파일 ④ (server-only mint + atomic consume SECURITY DEFINER — wake#3/B-6m + #2/B-6i).<br/>-- create_pending_terms_consent: server-only direct Postgres path 만 허용.<br/>-- 다중 required term_id 를 array 로 받아 pending row 에 보존.<br/>CREATE OR REPLACE FUNCTION public.create_pending_terms_consent(<br/>  p_provider text,<br/>  p_terms_version text,<br/>  p_term_ids uuid[]  -- service_terms + privacy_policy 등 동의된 모든 required term_id (wake#2/B-6i).<br/>) RETURNS uuid<br/>  LANGUAGE plpgsql<br/>  SECURITY DEFINER<br/>  SET search_path = private, public<br/>AS $$<br/>DECLARE new_token uuid; required_count int;<br/>BEGIN<br/>  -- 정본 provider id 만 허용 (wake R10 #3): google (built-in) + custom:naver (custom OAuth).<br/>  -- Kakao 는 §4.7 #5 분기 — internal terms gate 미사용.<br/>  IF p_provider NOT IN ('google','custom:naver') THEN<br/>    RAISE EXCEPTION 'provider not eligible for internal terms gate: % (expected google or custom:naver)', p_provider;<br/>  END IF;<br/>  -- 동의 array 가 active 필수 term 전부를 포함하는지 server-side 검증.<br/>  -- p_term_ids 의 중복을 먼저 제거 (wake R15 #4) — 같은 term_id 중복 제출 시<br/>  -- joined count 가 required_count 와 같아 보이는 우회 사고 차단.<br/>  SELECT count(*) INTO required_count FROM public.terms WHERE is_active AND is_required;<br/>  IF (SELECT count(DISTINCT t.id)<br/>        FROM unnest(p_term_ids) AS submitted(id)<br/>        JOIN public.terms t ON t.id = submitted.id<br/>       WHERE t.is_active AND t.is_required) <> required_count THEN<br/>    RAISE EXCEPTION 'required terms missing in p_term_ids (count must match distinct required active term set)';<br/>  END IF;<br/>  -- 정규화: 중복 없는 array 로 저장.<br/>  p_term_ids := ARRAY(SELECT DISTINCT unnest(p_term_ids));<br/>  INSERT INTO private.pending_terms_consents (provider, terms_version, term_ids, expires_at)<br/>    VALUES (p_provider, p_terms_version, p_term_ids, now() + interval '30 minutes')<br/>    RETURNING consent_token INTO new_token;<br/>  RETURN new_token;<br/>END $$;<br/>ALTER FUNCTION public.create_pending_terms_consent(text, text, uuid[]) OWNER TO private_owner;<br/>-- **server-only (wake#3/B-6m)** — anon/authenticated GRANT 절대 없음. Data API 가 열린 뒤에도<br/>-- 본 함수는 service_role / direct Postgres path 만 호출 가능. backend 가 terms UI 의 acceptance<br/>-- signal 을 자체 검증한 후에만 본 함수를 호출한다 → client 가 token 자력 발급 불가.<br/>REVOKE EXECUTE ON FUNCTION public.create_pending_terms_consent(text, text, uuid[]) FROM PUBLIC, anon, authenticated;<br/>GRANT  EXECUTE ON FUNCTION public.create_pending_terms_consent(text, text, uuid[]) TO service_role;<br/>-- terms_consents 컬럼 정의 (참고 — CMP-575 정본화):<br/>--   private.pending_terms_consents 에 `term_ids uuid[] NOT NULL` 추가 (위 함수가 채움).<br/>--   consume 시 term_ids 의 각 원소별로 public.terms_consents 에 1 row 씩 INSERT.<br/><br/>-- validate (read-only pre-exchange gate — wake#JMb gate-before-exchange).<br/>CREATE OR REPLACE FUNCTION public.validate_pending_terms_consent(p_token uuid, p_expected_provider text)<br/>  RETURNS boolean<br/>  LANGUAGE plpgsql<br/>  SECURITY DEFINER<br/>  SET search_path = private, public<br/>AS $$<br/>BEGIN<br/>  RETURN EXISTS (<br/>    SELECT 1 FROM private.pending_terms_consents<br/>     WHERE consent_token = p_token<br/>       AND provider = p_expected_provider<br/>       AND consumed_at IS NULL<br/>       AND expires_at > now()<br/>  );<br/>END $$;<br/>ALTER FUNCTION public.validate_pending_terms_consent(uuid, text) OWNER TO private_owner;<br/>REVOKE EXECUTE ON FUNCTION public.validate_pending_terms_consent(uuid, text) FROM PUBLIC, anon, authenticated;<br/>GRANT  EXECUTE ON FUNCTION public.validate_pending_terms_consent(uuid, text) TO service_role;<br/>-- service_role 만 — Next.js callback Route Handler 가 서버에서 호출 (wake#JMY).<br/><br/>-- consume_internal (post-exchange atomic — wake#2 race-free + wake#4 terms_consents 영속화).<br/>-- caller-supplied term_id/terms_version 신뢰 금지 — token row 에서 도출 (wake#JMY).<br/>-- 다중 required term_id 의 row 를 모두 INSERT (wake#2/B-6i).<br/>-- 각 term 의 version 은 public.terms.version 으로 join 도출 (wake R17 #3).<br/>CREATE OR REPLACE FUNCTION public.consume_pending_terms_consent_internal(<br/>  p_token uuid, p_provider text, p_user_id uuid<br/>) RETURNS boolean<br/>  LANGUAGE plpgsql<br/>  SECURITY DEFINER<br/>  SET search_path = private, public<br/>AS $$<br/>DECLARE<br/>  consumed_count int;<br/>  row_term_ids uuid[];<br/>BEGIN<br/>  -- 단일 conditional UPDATE + RETURNING — race-free atomic consume (wake#2).<br/>  -- terms_version 컬럼은 더 이상 단일 값으로 모든 term 에 적용하지 않으므로 RETURNING 에서 제외 —<br/>  -- 각 term 의 version 은 join 시 public.terms.version 으로 도출 (wake R17 #3).<br/>  UPDATE private.pending_terms_consents<br/>     SET consumed_at = now()<br/>   WHERE consent_token = p_token<br/>     AND provider = p_provider<br/>     AND consumed_at IS NULL<br/>     AND expires_at > now()<br/>  RETURNING term_ids INTO row_term_ids;<br/>  GET DIAGNOSTICS consumed_count = ROW_COUNT;<br/>  IF consumed_count <> 1 THEN<br/>    RETURN false;  -- caller 가 signOut + 에러. deleteUser 안 함 (wake#3).<br/>  END IF;<br/>  -- 같은 transaction — 동의된 모든 required term_id 별로 terms_consents row 영속화.<br/>  -- 각 row 의 version 은 join 된 t.version 사용 (term별 active version — wake R17 #3).<br/>  -- 이전 stale: row_terms_version 단일 값을 모든 term 에 동일 적용 — audit 가 term별<br/>  -- public.terms.version 으로 join 시 일부 consent 가 missing 으로 보임.<br/>  INSERT INTO public.terms_consents (user_id, term_id, version, source, agreed_at)<br/>  SELECT p_user_id, t.id, t.version, 'internal_signup', now()<br/>    FROM unnest(row_term_ids) AS submitted(id)<br/>    JOIN public.terms t ON t.id = submitted.id<br/>   WHERE t.is_active AND t.is_required;<br/>  RETURN true;<br/>END $$;<br/>ALTER FUNCTION public.consume_pending_terms_consent_internal(uuid, text, uuid) OWNER TO private_owner;<br/>REVOKE EXECUTE ON FUNCTION public.consume_pending_terms_consent_internal(uuid, text, uuid) FROM PUBLIC, anon, authenticated;<br/>GRANT  EXECUTE ON FUNCTION public.consume_pending_terms_consent_internal(uuid, text, uuid) TO service_role;<br/>-- service_role 만 — Next.js callback Route Handler 가 서버에서 호출 (wake#JMY).<br/><br/>-- 파일 ⑥ (Hook 함수 weak gate + REVOKE/GRANT).<br/>CREATE OR REPLACE FUNCTION private.before_user_created_terms_gate(event jsonb) RETURNS jsonb<br/>  LANGUAGE plpgsql<br/>AS $$ ... (H3 본문 — Kakao 분기 + google/naver allow) $$;<br/>REVOKE EXECUTE ON FUNCTION private.before_user_created_terms_gate(jsonb) FROM PUBLIC, anon, authenticated, service_role;<br/>GRANT  EXECUTE ON FUNCTION private.before_user_created_terms_gate(jsonb) TO supabase_auth_admin;<br/>```<br/>**역할 분리 봉인 (MUST — 모순 제거).** API runtime role (`anon`/`authenticated`/`service_role`) 은 **`private` schema USAGE 권한 없음 + 테이블/함수 EXECUTE 권한 없음**. 따라서:<br/>&nbsp;&nbsp;• terms 화면의 `private.pending_terms_consents` row insert 는 **`public.create_pending_terms_consent(...)` SECURITY DEFINER 함수 호출이 유일한 정본 경로** (owner `private_owner` 가 schema 접근권 위임). client (anon) 또는 server (authenticated/service_role) 둘 다 본 함수만 호출.<br/>&nbsp;&nbsp;• **`service_role` 직접 `INSERT INTO private.pending_terms_consents` 는 비정본** — REVOKE 로 차단. 백엔드도 본 함수를 호출한다.<br/>&nbsp;&nbsp;• Hook 함수 실행은 Supabase Auth 가 `supabase_auth_admin` 으로 호출하는 경로만.<br/>**RLS 가 켜진 테이블 (§7.2 R1 이후) 에는 별도 policy** 를 `supabase_auth_admin` role 에 추가하지 않으면 SELECT 가 silent fail → hook 이 모든 signup 을 reject 한다. CMP-575 의 RLS 정본화에서 본 role 의 read policy 를 함께 봉인.<br/>**GRANT 누락 시 첫 OAuth signup 이 `permission denied` 로 fail**, REVOKE 누락 시 PostgREST 노출 시점에 hook 함수가 RPC 로 callable. staging PoC (§3.2 A1.2) 에서 H4 시나리오 ⑥ (GRANT 회수 후 permission denied) + ⑦ (RPC 우회 negative) + ⑧ (service_role 직접 SELECT/INSERT 실패) 모두 검증. | CMP-576 (Hook SQL) + CMP-575 (RLS policy) |
| H3. **pre-user terms consent intent 조회 메커니즘 (MUST — gate-before-exchange + cookie 필수 + direct Postgres connection).** Supabase OAuth flow 는 Hook payload 로 client-side consent_token 을 전달할 supported channel 이 없다 (정본 `signInWithOAuth` options: `queryParams`/`redirectTo`/`scopes` 만, `data` 는 unsupported, PKCE state 는 Supabase 자체 관리). 그리고 (a) callback-after-insert 가 §4.7 sealed flow 를 위반하고, (b) **PostgREST `supabase.rpc(...)` 호출은 `[api].enabled = true` 가 전제** 인데 §7.2 의 RLS-완성 전 봉인 (`[api].enabled = false`) 과 모순. 따라서 본 PR 의 정본은 **gate-before-exchange + cookie-required + direct Postgres connection** 패턴이다 (wake R7 #1~#5 결합 봉인).<br/>**채널 분리 봉인 (wake#2/PnPc + wake#4/PnPh).**<br/>&nbsp;&nbsp;• **Direct Postgres connection (DB URL) — terms/consent RPC 전용.** Next.js Route Handler 가 `pg` / `postgres.js` 등 Postgres client 로 **direct DB connection** (`SUPABASE_DB_URL_POOLER` 또는 `SUPABASE_DB_URL_DIRECT` — §3.1 U5 시크릿) 으로 `SELECT public.create_pending_terms_consent(...)` / `validate_pending_terms_consent` / `consume_pending_terms_consent_internal` 호출. **PostgREST 비의존** — `[api].enabled = false` 봉인 (§7.2) 과 무관하게 동작. `supabase.rpc(...)` 사용 금지.<br/>&nbsp;&nbsp;• **Cookie-backed server Supabase client (`@supabase/ssr` 의 `createServerClient`) — PKCE code exchange 전용.** `exchangeCodeForSession(code)` 는 PKCE code_verifier 가 request cookie 에 있으므로 cookie 를 읽는 server client 만 정본. service_role admin client 로 호출하면 verifier 미접근 → exchange fail (wake#2/PnPc).<br/>&nbsp;&nbsp;• **service_role admin client — RPC 호출 외 사용 금지.** Direct Postgres connection 이 정본이므로 service_role admin client 는 본 흐름에서 사용 안 함 (예외: `auth.admin.signOut`).<br/>**정본 흐름 (Google/Naver internal terms).**<br/>① **terms 동의.** Frontend 가 사용자에게 선택받은 UI-level provider (`google` / `naver` / 추가 시) 와 함께 terms 화면 통과 시 backend `/api/terms/accept` POST `{ ui_provider: '<selected>', term_ids: [...] }` 호출. Next.js Route Handler 가 **UI provider → Supabase provider id 매핑** (정본 — wake R10 #3):<br/>&nbsp;&nbsp;• `'google'` → `'google'` (built-in provider — Supabase JS `signInWithOAuth({ provider: 'google' })`)<br/>&nbsp;&nbsp;• `'naver'` → **`'custom:naver'`** (custom OAuth/OIDC provider 정본 — Supabase docs: https://supabase.com/docs/guides/auth/custom-oauth-providers#provider-identifiers — `custom:` prefix 필수)<br/>&nbsp;&nbsp;• `'kakao'` → `'kakao'` (built-in — 단 Kakao 는 §7.1.5 H3 의 kakao 분기로 처리, internal terms gate 미사용)<br/>매핑된 정본 provider id 로 검증 (`provider IN ('google','custom:naver')` — Kakao 제외, AGENTS.md §4.7 #5) 한 뒤 direct Postgres connection 으로 `SELECT public.create_pending_terms_consent($1, '<ver>', $2::uuid[])` (`$1` = **매핑된 정본 provider id**, `$2` = 동의된 active required term_ids array) 호출 → `consent_token` 반환. **`pending_terms_consents.provider` 컬럼이 정본 provider id (`custom:naver` 포함) 를 저장** — callback `validate_pending_terms_consent` / `consume_pending_terms_consent_internal` 도 같은 정본 id 로 매칭. UI 값을 그대로 저장하면 Supabase 가 보고하는 `event.user.app_metadata->>'provider'` 와 불일치로 모든 Naver signup reject 사고. **provider 하드코딩 금지** — Naver signup 이 `'google'` token 으로 mint 되면 callback validate 에서 provider 불일치로 reject 사고. **모든 active required `term_id` 를 array 로 전달**. **함수 자체는 `service_role` 전용 GRANT**. backend 가 terms UI 의 acceptance signal (sessionStorage, cookie 등) 을 자체 검증한 후에만 본 함수 호출. **명시 Set-Cookie 헤더**:<br/>&nbsp;&nbsp;`Set-Cookie: __Host-jippin_consent_token=<token>; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=1800`<br/>`__Host-` prefix 규약 3종 (Path=/ + Domain 미지정 + Secure) MUST.<br/>② **PKCE flow 시작 — backend 가 중재.** Frontend 는 generic "login" 또는 "signup" 버튼이 아니라 **terms 화면을 통과한 뒤에만** `/api/oauth/start?provider=google` 호출. backend 가 cookie 존재 확인 후 `signInWithOAuth({ flowType: 'pkce', provider, options: { redirectTo: '<app>/auth/callback', queryParams, scopes } })` 흐름 시작. **terms 화면 우회 / generic OAuth 진입점은 frontend 에 노출하지 않는다** — 따라서 정당한 OAuth flow 는 항상 cookie 와 함께 callback 에 도착한다 (wake#1/PnPZ).<br/>③ **provider OAuth → Supabase 단발성 code → app callback.** Supabase Auth `/auth/v1/callback` 단계에는 `auth.users` 미생성 (PKCE 정본) → 302 to `<app>/auth/callback?code=...`.<br/>④ **Next.js server-side Route Handler `/auth/callback`.**<br/>&nbsp;&nbsp;(a) **callback path 분리 — Kakao 는 consent-token gate 전 분기 (wake R15 #3).** Supabase OAuth callback URL 은 provider 별로 다른 app callback path 로 redirect (`/auth/callback/google`, `/auth/callback/naver`, **`/auth/callback/kakao`**). server-side Route Handler 가 path 매칭으로 provider 먼저 도출:<br/>&nbsp;&nbsp;&nbsp;&nbsp;• **Kakao path (`/auth/callback/kakao`)** → consent-token cookie 검사 **skip** (Kakao 는 internal terms gate 미사용, §4.7 #5). 곧바로 `@supabase/ssr` `exchangeCodeForSession(code)` 호출 → `auth.users` 생성 + Kakao Sync persistence trigger (§7.1.5 H3 파일 ⑦) 가 `terms_consents (source='kakao_sync')` 영속화. Hook 의 `kakao_terms_missing` reject 가 strong gate.<br/>&nbsp;&nbsp;&nbsp;&nbsp;• **Google / Naver path (`/auth/callback/google` / `/.../naver`)** → 아래 cookie 검사 진입.<br/>cookie 검사 (Google/Naver 경로). cookie 에서 `__Host-jippin_consent_token` 추출. **cookie 없음 → 정당하지 않은 callback (uninitiated OAuth flow)** → cookie 삭제 + redirect to `/auth/error?reason=invalid_oauth_flow`. **`exchangeCodeForSession` 호출 안 함 → `auth.users` 생성 안 함** (wake#1/PnPZ — google/naver signup 도 returning login 도 cookie 없이는 통과 불가). 정상 returning login 은 cookie 가 짧지만 자기 trip 시 mint 된 marker 로 들어옴 — frontend 가 `/api/oauth/start` 호출 시 항상 cookie 발급.<br/>&nbsp;&nbsp;(b) Cookie 있음 → **expected_provider 는 trusted source 에서 도출** (wake R13 #6): backend `/api/oauth/start` 가 cookie 발급 시점에 **signed cookie pair** `__Host-jippin_consent_provider=<provider>` + HMAC signature (server secret 기반) 도 함께 설정. callback 이 cookie 의 provider 값을 HMAC 검증 후에만 `validate_pending_terms_consent(token, signed_provider)` 호출. client-tampered `expected_provider` (URL query 또는 unsigned cookie) 는 trust 금지. **대안 — Kakao callback path 분리**: `/auth/callback/google`, `/auth/callback/naver`, `/auth/callback/kakao` 로 path 자체에 provider 박아 server-side handler 가 path 매칭으로 provider 도출 (cookie 의존 없음, OAuth provider 콘솔의 Authorized redirect URI 도 path 별 분리). path 분리 option 이 signed cookie 보다 단순하고 강함 — CMP-577 web 구현은 path 분리 권장. **HMAC signed cookie 옵션**은 path 분리가 불가능한 인프라 (CDN/edge 제약) 시 fallback. validate false → cookie 삭제 + redirect to `/auth/error?reason=terms_missing` — exchange 미호출, `auth.users` 생성 0건.<br/>&nbsp;&nbsp;(c) validate true → **cookie-backed `@supabase/ssr` server client 의 `exchangeCodeForSession(code)` 호출** (service_role admin 아님 — wake#2/PnPc). 응답에서 `session.access_token` (refresh_token) + `user.id` + `is_new_user` 받음. **`is_new_user == true`** (신규 signup 흐름) → (d) 로 진행. `is_new_user == false` (returning user — cookie 가 stale 한 케이스) → cookie 삭제 + 정상 login redirect.<br/>&nbsp;&nbsp;(d) **direct Postgres connection 으로** `consume_pending_terms_consent_internal(token, provider, user_id)` 호출. 같은 transaction:<br/>&nbsp;&nbsp;&nbsp;&nbsp;• 단일 conditional UPDATE (race-free atomic consume)<br/>&nbsp;&nbsp;&nbsp;&nbsp;• `INSERT INTO public.terms_consents (user_id, term_id, version, source, agreed_at) VALUES (..., 'internal_signup', now())`<br/>&nbsp;&nbsp;&nbsp;&nbsp;• 함수 true → cookie 삭제 + redirect to home.<br/>&nbsp;&nbsp;(e) **함수 false (race lose / 함수 내부 RLS 실패)** → backend 가 **(1)** `raw_app_meta_data` (DB column 명 — `app_metadata` 는 API/JWT 필드명만, wake#1/B-6d) 에 `terms_missing = true` + `terms_missing_set_at = now()` marker 를 `direct DB connection` 으로 `UPDATE auth.users SET raw_app_meta_data = jsonb_set(...)` (cron cleanup target 표시 — §7.1.6/wake#5 봉인). **(2)** 방금 발급된 **session JWT 로 signOut** — `auth.admin.signOut(session.access_token)` (session JWT 기준, UUID 아님 — wake#3/PnPf). **(3)** `@supabase/ssr` client 의 cookie clear 함수로 SSR session cookie 정리. **(4)** redirect to `/auth/error?reason=terms_consume_failed`. **`auth.admin.deleteUser` 절대 호출 금지** (wake#3 — 기존 thread).<br/>**비정본 (절대 사용 금지):**<br/>(a) `supabase.rpc(...)` PostgREST 채널 — `[api].enabled = false` 동안 endpoint 없음 (wake#4/PnPh).<br/>(b) service_role admin client 로 `exchangeCodeForSession` 호출 — PKCE verifier 미접근 (wake#2/PnPc).<br/>(c) no-cookie callback 을 returning login 으로 간주해 exchange — 신규 user 가 terms 동의 없이 만들어짐 (wake#1/PnPZ).<br/>(d) `auth.admin.signOut(user.id)` — UUID 가 아니라 session JWT (wake#3/PnPf).<br/>(e) `auth.admin.deleteUser` — returning user 사고 위험.<br/>(f) `signInWithOAuth({ options: { data: { ... } } })` — Supabase JS 정본 옵션 아님.<br/>**Hook 본문 (weak gate — Hook event 에서 보장되는 field 만 enforce, wake R16 #1).** Supabase `before-user-created` payload 는 **pre-insert `auth.users` record** 이고 `event.user.identities` 는 `[]` (insert 전이라 empty array) 이므로 Hook 에서 `identities[0].identity_data` 를 enforce 하면 모든 정상 OAuth signup 을 reject 한다. Hook 의 정본 enforcement 는 `event.user` 의 보장된 field (`email`, `phone`, `raw_user_meta_data`, `is_anonymous` 등) 만. Kakao Sync `service_terms` 검증은 `auth.identities` AFTER INSERT trigger (§7.1.5 H3 파일 ⑦) 가 정본 위치 — identity row 의 `NEW.identity_data->'service_terms'` 검사:<br/>```sql<br/>-- private.before_user_created_terms_gate(event jsonb) RETURNS jsonb<br/>BEGIN<br/>  -- Hook event 는 pre-insert auth.users + 빈 identities[]. provider/identity_data 검사는<br/>  -- auth.identities AFTER INSERT trigger (파일 ⑦) 책임 — 본 Hook 은 strong gate 아님.<br/>  -- google/naver/kakao 모두 통과시키고 (gate-before-exchange + Kakao trigger) 위임.<br/>  -- Hook 단계의 차단은 event 에서 보장되는 field (e.g. email 형식, banned domain) 으로만.<br/>  RETURN '{}'::jsonb;  -- allow.<br/>END;<br/>```<br/>**Kakao `service_terms` reject 는 §7.1.5 H3 파일 ⑦ 의 `persist_kakao_sync_terms_consents` trigger 에서 `RAISE EXCEPTION 'kakao identity persisted without service_terms'` 로 수행.** trigger 가 raise 하면 `auth.identities` insert 가 rollback 되며 같은 transaction 의 `auth.users` insert 도 rollback (Supabase Auth 의 OAuth flow 가 user + first identity 를 같은 transaction 에서 insert) → user 생성 0건 으로 강한 차단 보장. Hook 의 이전 `event.user.identities[0].identity_data.service_terms IS NULL` 검사는 stale (identities empty 라 무조건 true) → 제거.<br/>**Kakao Sync consent 영속화 (MUST — wake R10 #5 + R13 #3).** Hook 이 `service_terms` 확인 후 `{}` allow 만 반환하면 `auth.users` row 만 생성되고 **`terms_consents (source='kakao_sync')` row 는 영속화되지 않음**. **trigger 위치 정정: `auth.users` 가 아닌 `auth.identities`** (wake R13 #3) — OAuth identity payload (`identity_data.service_terms` 포함) 는 `auth.identities.identity_data` 에 직접 들어가며, `auth.users.raw_user_meta_data->identities` 는 Supabase Auth 가 채우는 시점/형식이 다를 수 있다. 정본 SQL:<br/>```sql<br/>-- 파일 ⑦ (Kakao Sync after-create — auth.identities trigger + agreed tag 검증).<br/>-- 본 trigger 는 §7.1.5 H2 봉인의 일부로 CMP-575 가 정본화. Kakao Sync 의 tag별<br/>-- `agreed=true` 만 해당 local term consent 로 영속화 (wake R17 #4 — Kakao 응답의<br/>-- subset/disagreed/revoked tag 까지 동의로 기록되는 사고 차단).<br/>--<br/>-- **선결 요구사항** (CMP-575 가 함께 정의):<br/>-- `public.kakao_term_mapping (kakao_tag text PRIMARY KEY, public_term_id uuid<br/>--   REFERENCES public.terms(id), is_required boolean NOT NULL DEFAULT true)` —<br/>-- Kakao service_terms 응답의 tag (e.g. "service", "privacy", "marketing") 와<br/>-- 본 프로젝트의 public.terms.id 매핑. 본 매핑 미존재 tag 는 무시 (Kakao 가 보낸<br/>-- 비표준 tag 가 audit 를 오염시키지 않도록).<br/>CREATE OR REPLACE FUNCTION public.persist_kakao_sync_terms_consents()<br/>  RETURNS trigger<br/>  LANGUAGE plpgsql<br/>  SECURITY DEFINER<br/>  SET search_path = public, auth<br/>AS $$<br/>DECLARE<br/>  v_service_terms jsonb;<br/>  v_prior_identity_count int;<br/>  v_required_kakao_tags text[];<br/>  v_agreed_kakao_tags text[];<br/>BEGIN<br/>  IF NEW.provider <> 'kakao' THEN RETURN NEW; END IF;<br/>  -- First-creation 제한 (wake R15 #6): 본 user 의 prior identity 0건일 때만 영속화.<br/>  SELECT count(*) INTO v_prior_identity_count<br/>    FROM auth.identities WHERE user_id = NEW.user_id AND id <> NEW.id;<br/>  IF v_prior_identity_count > 0 THEN<br/>    RETURN NEW;  -- existing user 의 Kakao manual link — 재영속화 skip.<br/>  END IF;<br/>  -- identity_data->service_terms 가 OAuth provider 응답 정본 위치 — Kakao Sync.<br/>  v_service_terms := NEW.identity_data->'service_terms';<br/>  IF v_service_terms IS NULL THEN<br/>    RAISE EXCEPTION 'kakao identity persisted without service_terms — Hook bypass';<br/>  END IF;<br/>  -- **Kakao agreed tag 별 검증 (wake R17 #4)**:<br/>  -- 매핑 테이블에서 required 인 Kakao tag set 확인.<br/>  SELECT array_agg(kakao_tag) INTO v_required_kakao_tags<br/>    FROM public.kakao_term_mapping<br/>   WHERE is_required;<br/>  -- Kakao 응답에서 `agreed=true` 인 tag 만 추출 (service_terms 는 array 또는 object 일 수<br/>  -- 있음 — CMP-576 PoC 시점에 실제 Kakao 응답 구조 확인 후 jsonb_path / array unpack 정정.<br/>  -- 본문은 의미 표기: `[{tag:"service", agreed:true}, {tag:"privacy", agreed:false}]` 형태 가정).<br/>  SELECT array_agg(elem->>'tag') INTO v_agreed_kakao_tags<br/>    FROM jsonb_array_elements(v_service_terms) AS elem<br/>   WHERE (elem->>'agreed')::boolean = true;<br/>  -- required 인데 agreed 가 아닌 tag 가 있으면 reject (Kakao Sync 약관 미동의 user).<br/>  IF NOT (v_required_kakao_tags <@ COALESCE(v_agreed_kakao_tags, ARRAY[]::text[])) THEN<br/>    RAISE EXCEPTION 'kakao required terms not fully agreed: required=% agreed=%',<br/>      v_required_kakao_tags, COALESCE(v_agreed_kakao_tags, ARRAY[]::text[]);<br/>  END IF;<br/>  -- agreed tag 별로 매핑된 local public.terms 에만 consent row INSERT.<br/>  -- version 컬럼은 join 된 t.version 사용 (wake R16 #3 동일 정본).<br/>  INSERT INTO public.terms_consents (user_id, term_id, version, source, agreed_at)<br/>  SELECT NEW.user_id, t.id, t.version, 'kakao_sync', now()<br/>    FROM jsonb_array_elements(v_service_terms) AS elem<br/>    JOIN public.kakao_term_mapping m ON m.kakao_tag = elem->>'tag'<br/>    JOIN public.terms t ON t.id = m.public_term_id<br/>   WHERE (elem->>'agreed')::boolean = true<br/>     AND t.is_active<br/>     AND t.is_required<br/>  ON CONFLICT (user_id, term_id, version) DO NOTHING;<br/>  RETURN NEW;<br/>END $$;<br/>ALTER FUNCTION public.persist_kakao_sync_terms_consents() OWNER TO private_owner;<br/><br/>-- auth.identities AFTER INSERT — OAuth identity payload 가 채워진 정본 시점 (wake R13 #3).<br/>CREATE TRIGGER persist_kakao_sync_terms_consents_after_identity_insert<br/>  AFTER INSERT ON auth.identities<br/>  FOR EACH ROW EXECUTE FUNCTION public.persist_kakao_sync_terms_consents();<br/>```<br/>본 trigger 는 §7.1.5 H2 파일 순서에 **파일 ⑦** 으로 추가 (Hook 함수 파일 ⑥ 직후). owner = `private_owner` (cross-schema GRANT 활용 — `auth.identities` SELECT (id, user_id, provider, identity_data) 권한 봉인). Kakao 가 아닌 provider 는 즉시 `RETURN NEW` 로 통과.<br/>&nbsp;&nbsp;② **callback-side reconciliation (보조).** Next.js Route Handler 가 `exchangeCodeForSession` 후 `is_new_user == true` + `provider == 'kakao'` 인 경우 direct Postgres 로 본 INSERT 를 명시 수행. trigger 가 정본이지만 trigger 실패 / 비활성 시 fallback. CMP-577 web 트랙이 본 옵션을 supplemental 로 구현.<br/>옵션 ① + ② 동시 적용 권장 (방어 다중화). **두 옵션 모두 누락 시** Kakao signup 이 후속 audit/compliance 검사에서 "terms_consents 누락 user" 로 잡힘 — §4.7 #5 sealed flow 위반.<br/>**OAuth activation sequencing 결정 (wake#4/PnPh).** 두 가지 옵션 중 본 PR 의 정본은 **옵션 A (direct Postgres connection)**. CMP-576 PR 은 본 옵션을 채택 — direct DB connection 으로 RPC 호출. 옵션 B (`§7.2 R1~R4 통과 후로 activation 미루기`) 는 CMP-575 RLS 완성 의존성을 키우므로 본 PR 비채택. CMP-576 PR 본문에 옵션 A 채택 + direct DB connection 구현 + connection 환경변수 (`SUPABASE_DB_URL_POOLER` — §3.1 U5) 사용 캡처 의무. | CMP-576 + CMP-577 + CMP-575 (RLS policy) |
| H4. **Hook + gate-before-exchange + cookie-required + direct Postgres 활성화 self-check (CMP-576 PR).** 다음 PoC 결과를 staging branch 에서 캡처해 CMP-576 PR 본문에 첨부 — **모든 시나리오에서 `auth.admin.deleteUser` 호출 0건** + **모든 RPC 가 direct Postgres connection 으로 실행** + **`exchangeCodeForSession` 은 cookie-backed `@supabase/ssr` server client 만 사용**.<br/>**Hook (weak gate) 시나리오.**<br/>① google/naver signup (Hook 만) → Hook 응답 `{}` allow. strong gate 는 ⑥~⑭ callback 시나리오. Hook 자체는 user 생성 시점이 아님 (PKCE: `exchangeCodeForSession` 시점).<br/>② Kakao signup `service_terms` 있음 → Hook `{}` + Kakao 흐름 internal terms gate 우회 (§4.7 #5) → `auth.users` + `terms_consents (source='kakao_sync')` row.<br/>③ Kakao signup `service_terms` 누락 → Hook `{"error":{"http_code":403,"message":"kakao_terms_missing"}}` + `auth.users` 0건.<br/>④ **error 형식 negative.** Hook 본문을 `decision/reject` 형식으로 바꾸고 ③ 재실행 → fail-open 으로 user 생성됨 캡처 (원상복구).<br/>**Cookie `__Host-` 시나리오 (wake#1/PnPZ).**<br/>⑤ `Set-Cookie: __Host-jippin_consent_token=<token>; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=1800` 응답 헤더 캡처 + `Path=/` 제거 negative (cookie reject).<br/>**Gate-before-exchange + cookie-required 시나리오 (wake R7 #1).**<br/>⑥ **no-cookie callback negative (wake#1/PnPZ).** consent_token cookie 없이 callback 도달 → handler 가 **uninitiated OAuth flow** 로 간주 → cookie 삭제 + redirect to `/auth/error?reason=invalid_oauth_flow`. **`exchangeCodeForSession` 호출 0건 + `auth.users` 행 수 불변 + deleteUser 0건**. 신규 user 가 cookie 없이는 절대 만들어지지 않음을 입증.<br/>⑦ Cookie 있음 + `validate_pending_terms_consent` (**direct Postgres connection 으로** — wake#4/PnPh) false → cookie 삭제 + redirect to `/auth/error?reason=terms_missing`. **`exchangeCodeForSession` 0건 + `auth.users` 0건 + deleteUser 0건**.<br/>⑧ Cookie 있음 + validate true → **`@supabase/ssr` server client (cookie-backed)** 의 `exchangeCodeForSession(code)` 호출 (wake#2/PnPc — service_role admin client 아님). 응답에서 `session.access_token` + `user.id` + `is_new_user`. `is_new_user == true` → **direct Postgres connection 으로** `consume_pending_terms_consent_internal` 호출. 같은 transaction:<br/>&nbsp;&nbsp;• `private.pending_terms_consents.consumed_at` 채워짐<br/>&nbsp;&nbsp;• `public.terms_consents` 에 `(user_id, term_id, version, source='internal_signup', agreed_at)` row 1건<br/>&nbsp;&nbsp;• `auth.users` 보존 (deleteUser 0건)<br/>⑨ Cookie 있음 + validate true + exchange + `is_new_user == false` (stale cookie 케이스) → cookie 삭제 + 정상 login. consume 호출 0건. **deleteUser 0건**.<br/>⑩ **Race-free atomic consume (wake#2).** 동시 2 signup flow → validate 둘 다 true → exchange 둘 다 user 생성. `consume_internal` 의 단일 conditional UPDATE 가 정확히 1개만 통과. 한 쪽 false → backend 가 (1) **`raw_app_meta_data->>'terms_missing' = true` + `raw_app_meta_data->>'terms_missing_set_at' = now()`** marker 를 direct DB 로 `UPDATE auth.users SET raw_app_meta_data = jsonb_set(...)` (cron cleanup 표시 — wake R15 #2 column 정정) **(2)** **`auth.admin.signOut(session.access_token)` — UUID 아닌 session JWT 사용** (wake#3/PnPf) **(3)** `@supabase/ssr` cookie clear. **deleteUser 0건**. `terms_consents` row 1건만.<br/>**Channel 분리 negative (wake#2/PnPc + #4/PnPh).**<br/>⑪ **service_role admin client 로 exchangeCodeForSession 호출 시도** → PKCE code_verifier 미접근으로 fail 캡처 (negative — 본 channel 미사용 입증).<br/>⑫ **`supabase.rpc(...)` PostgREST 호출 시도** (`[api].enabled=false` 상태) → 404 / endpoint 없음 캡처. 본 PR 의 모든 RPC 가 direct Postgres connection 만 사용함을 입증.<br/>⑬ **session JWT signOut PoC (wake#3/PnPf).** ⑩ 의 race lose 시나리오에서 `auth.admin.signOut(user.id)` (UUID) 호출 시 session 이 invalidate 안 됨 → `getUser(access_token)` 이 여전히 user 반환 캡처. `auth.admin.signOut(session.access_token)` (JWT) 호출 시 session invalidate 확인. UUID vs JWT 차이 입증 (원상복구).<br/>**RPC 권한 negative (wake#JMY 유지).**<br/>⑭ `anon` JWT 로 PostgREST `/rest/v1/rpc/...` 호출 → 404 (`[api].enabled=false` 상태). `[api].enabled=true` 가정 시에도 `permission denied for function` (service_role 만 GRANT).<br/>⑮ `authenticated` JWT 로 동일 → 동일 fail.<br/>⑯ `service_role` JWT 로 `SELECT * FROM private.pending_terms_consents` direct 시도 → `permission denied for schema private`.<br/>**RLS policy 보강.**<br/>⑰ 임시로 `DROP POLICY pending_terms_consents_auth_admin_select` 후 PoC → Hook 자체는 `private` 접근 안 하므로 영향 없음. 미래 Hook 본문이 SELECT 추가 시 silent 0 rows 됨 캡처 (원상복구).<br/>**Sealed flow + cron 협동 (wake#5/PnPk).**<br/>⑱ ⑥/⑦ 시나리오 (no-cookie / validate false) 직후 `auth.users` + `terms_consents` 둘 다 0건 확인 = §4.7 sealed flow 충족.<br/>⑲ ⑧ 시나리오 직후 `auth.users` 1 + `terms_consents` 1 (source=internal_signup) 확인. 같은 backend handler 안 sequential.<br/>⑳ **Anonymous user 정상 흐름 (wake#5/PnPk negative).** Phase 2 진입 가정 후 `signInAnonymously()` 호출 → `auth.users` row 1건 (`is_anonymous=true`) + `terms_consents` 0건. 24h+ 후 §7.1.6 Cron1 실행 → 본 anonymous user **`banned_until` 미설정 + marker 없음**. `is_anonymous=true` + `raw_app_meta_data->>'terms_missing'` 부재 조건으로 제외됨을 명시 캡처.<br/>㉑ ⑩ 시나리오 (race lose) 후 24h+ 시뮬레이션 + cron 실행 → marker 있는 user 만 `banned_until` 채워짐. 정상 signup user + anonymous user 모두 무영향 확인.<br/>**SQL 컬럼/스키마 정합 (wake R8 #1~#4 PoC).**<br/>㉒ **`raw_app_meta_data` vs `app_metadata` (wake#1/B-6d).** 임시로 marker SQL 을 `UPDATE auth.users SET app_metadata = ...` 로 바꿔 실행 → `column "app_metadata" does not exist` 에러 캡처. 정정 SQL (`raw_app_meta_data` + `jsonb_set` + `COALESCE(..., '{}'::jsonb)`) 로 marker set + cron 양쪽 정상 동작 캡처. cron SELECT 시에도 `raw_app_meta_data->>'terms_missing'` 으로 접근 확인.<br/>㉓ **다중 term_id 영속화 (wake#2/B-6i).** `create_pending_terms_consent('google', '<ver>', ARRAY[service_terms_id, privacy_policy_id, marketing_id])` 호출 후 callback consume 통과 → `public.terms_consents` 에 term별 row 3개 (service_terms / privacy_policy / marketing 각 1) 생성됨 캡처. 단일 row 만 들어가면 fail. `term_ids` 가 일부 active required 누락하면 `create_pending_terms_consent` 가 `required terms missing in p_term_ids` 예외 던지는 negative 도 캡처.<br/>㉔ **server-only mint (wake#3/B-6m).** `anon` JWT 로 `supabase.rpc('create_pending_terms_consent', ...)` 호출 시도 (가정: 미래에 `[api].enabled=true` 가정) → `permission denied for function` 캡처 (REVOKE FROM anon, authenticated). client 가 token 자력 발급 불가 입증. backend (service_role / direct Postgres) 만 호출 가능.<br/>㉕ **SECURITY DEFINER 권한 누락 negative (wake#4/B-6o).** 임시로 `REVOKE INSERT ON public.terms_consents FROM private_owner` 후 ⑧ 재실행 → `consume_pending_terms_consent_internal` 이 INSERT 단계에서 `permission denied for table terms_consents` 로 fail → callback 이 false 받고 consume false path 진입. 원상복구 후 정상. 같은 패턴으로 `REVOKE SELECT ON public.terms`, `REVOKE UPDATE (raw_app_meta_data) ON auth.users` 각각 negative 캡처. 본 PoC 가 §7.1.5 H2 파일 ① 의 cross-schema GRANT 가 누락 없이 모두 있어야 함을 입증.<br/>**Provider parameterize + 정본 provider id (wake R9 #4 + R10 #3).**<br/>㉖ **Provider parameterize PoC.** Naver signup 시 frontend → backend `/api/terms/accept { ui_provider: 'naver', term_ids: [...] }` → backend mapping `naver` → **`custom:naver`** → `create_pending_terms_consent('custom:naver', ...)` 호출 → callback `validate_pending_terms_consent(token, 'custom:naver')` 통과 (Supabase 가 `event.user.app_metadata->>'provider'` 로 `custom:naver` 반환). Google signup 도 `'google'` 매핑 그대로. **하드코딩 negative**: backend 가 `'google'` 또는 `'naver'` (mapping 누락) 로 강제 mint 후 Naver signup 시 callback validate false → exchange 미호출 캡처. mapping 누락 시 SQL 함수가 `RAISE EXCEPTION 'provider not eligible for internal terms gate: naver (expected google or custom:naver)'` 캡처.<br/>**Production Auth config (wake R9 #3 + R10 #1 + R10 #4).**<br/>㉗ **§7.1.7 A-AUTH-1~A-AUTH-4 PoC.** A3 머지 직전:<br/>&nbsp;&nbsp;• A-AUTH-1: Console (production) → Providers Google/`custom:naver`/Kakao Enabled + Client ID/Secret 등록 + Redirect URL = `https://<PROD_REF>.supabase.co/auth/v1/callback` 캡처.<br/>&nbsp;&nbsp;• A-AUTH-2: `[auth].enable_signup` ON + `[auth.email].enable_signup` OFF 캡처.<br/>&nbsp;&nbsp;• **A-AUTH-2b (wake R10 #4)**: production `site_url` + `additional_redirect_urls` 가 `https://<prod-app>` + `https://<prod-app>/auth/callback` + `https://<prod-app>/**` 4종 포함 dashboard 캡처. `[remotes.production.auth]` override 블록 (옵션 ①) 또는 dashboard direct edit (옵션 ②) PR 본문 첨부.<br/>&nbsp;&nbsp;• A-AUTH-3: `supabase config push --project-ref <PROD_REF>` 출력 (가용 시).<br/>&nbsp;&nbsp;• **A-AUTH-4: smoke signup PoC + provider Enabled 유지 (wake R10 #1)**. 테스트 계정의 user row 만 후속 `auth.admin.deleteUser` 로 cleanup (한정). **provider 전체를 Disabled 로 회귀시키지 않음** — 정상 완료 시 production signup 즉시 가용 상태 유지.<br/>**Kakao Sync persistence + W2 channel 정정 (wake R10 #5 + R10 #2).**<br/>㉘ **Kakao Sync after-create persistence PoC (wake R10 #5).** Kakao signup 시 Hook 통과 → `auth.users` row insert → `persist_kakao_sync_terms_consents_after_insert` trigger firing → `public.terms_consents` 에 `source='kakao_sync'` row (active required terms 개수만큼) 영속화 캡처. 임시로 trigger DROP 후 Kakao signup → `terms_consents` 0건 fail 캡처 (정정 후 통과). callback-side reconciliation 옵션 ② 가용 시 fallback 도 캡처.<br/>㉙ **W2 channel — `supabase secrets set` 만 정본 (wake R10 #2).** 임시로 OAuth client secret 을 Project Settings → Vault 에만 등록 + CLI `supabase secrets set` 미실행 후 staging branch 에서 `supabase db diff` 또는 OAuth signup 시도 → `env(SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID)` unresolved 로 fail 캡처 (Vault 가 config env source 아님 입증). 정정 `supabase secrets set --project-ref <REF> --env-file <encrypted.env>` 실행 후 정상 동작 캡처.<br/>**Trigger + permission + remote 정합 (wake R13 #1/#3/#4/#5).**<br/>㉚ **`NEW.user_id` discriminator PoC (R13 #1).** §7.1.1 G2 트리거가 `auth.identities` BEFORE INSERT 시 `(NEW.user_id, NEW.provider)` 매칭으로 manual/auto attach 구분. 임시로 `auth.uid()` 사용 후 `linkIdentity()` 호출 → 트리거 컨텍스트에서 NULL 로 모든 정당한 manual link reject 됨을 캡처 (negative, 원상복구 후 통과).<br/>㉛ **Kakao trigger `auth.identities` PoC (R13 #3).** Kakao signup 후 `auth.identities` AFTER INSERT trigger 가 firing → 서버가 Kakao `/v2/user/service_terms` 응답을 provider token/server credential 로 조회해 agreed tag 를 확인 → `terms_consents (source='kakao_sync')` 영속화 캡처. Supabase `NEW.identity_data->service_terms` 는 PoC 로 실제 포함이 입증된 경우에만 fallback 으로 허용. 임시로 trigger 를 `auth.users` AFTER INSERT 로 되돌리고 동일 signup → `raw_user_meta_data->identities` 가 비었거나 타이밍 mismatch 로 fail 캡처 (negative, 원상복구).<br/>㉜ **predicate column SELECT 권한 (R13 #4).** `UPDATE auth.users SET raw_app_meta_data = ... WHERE id = $1` 실행. 임시로 `REVOKE SELECT (id) ON auth.users FROM private_owner` 후 marker UPDATE 시도 → `permission denied for column id` 캡처. 원상복구 후 통과. `SELECT (id, is_anonymous, raw_app_meta_data, raw_user_meta_data)` GRANT 봉인 입증.<br/>㉝ **`[remotes.production]` 동행 PoC (R13 #5).** `supabase config push --project-ref <PROD_REF>` 실행 시 `[remotes.production.auth]` 만 있는 config (without `[remotes.production] project_id`) 로 push → override 미적용/skip 됨을 캡처 (negative). `[remotes.production] project_id = <PROD_REF>` 추가 후 동일 push → site_url + additional_redirect_urls 가 production 에 적용됨 확인.<br/>**Signed provider marker + preview secrets (wake R13 #6/#7).**<br/>㉞ **Signed provider marker / path 분리 PoC (R13 #6).** callback `/auth/callback/naver` (path 분리 옵션) 또는 `__Host-jippin_consent_provider=naver` + HMAC signature cookie 가 trust 채널임을 입증. 임시로 URL query `?expected_provider=naver` 만 사용 후 client 가 tampered query 로 Google signup 을 Naver provider 로 위장 시도 → callback handler 가 cookie/path 정본 매칭으로 reject 캡처.<br/>㉟ **Preview branch secrets provisioning PoC (R13 #7).** persistent branch (prod/dev/staging) secret 만 등록 후 PR preview branch 생성 → preview signup PoC 가 `env(...)` unresolved 로 fail 캡처 (negative). 옵션 ① wrapper 가 `supabase secrets set --project-ref <preview_branch_ref> --env-file` 실행 후 동일 preview signup 정상 통과 캡처.<br/>**Callback path + term_ids dedup + G2 new-user + Kakao link conflict (wake R15 #3~#6).**<br/>㊱ **Kakao callback path 분리 PoC (R15 #3).** `/auth/callback/kakao` 진입 시 consent-token cookie 검사 skip + 곧바로 `exchangeCodeForSession` → Kakao Sync trigger persistence 캡처. 임시로 path 분리 제거 후 Kakao signup 시 no-cookie reject 로 모든 Kakao callback fail 캡처 (negative, 원상복구).<br/>㊲ **`term_ids` deduplicate PoC (R15 #4).** `create_pending_terms_consent('google', '1.0', ARRAY[service_terms_id, service_terms_id])` (같은 term 중복) 호출 → `required terms missing` 예외 캡처 (count(DISTINCT) <> required_count). 임시로 dedup 검증 제거 후 같은 array 호출 → token 발급 + 후속 consume 시 `terms_consents` 의 unique 제약으로 INSERT fail 캡처 (negative).<br/>㊳ **G2 new-user observable discriminator PoC (R15 #5).** 신규 user signup → `EXISTS prior identity` = false 로 ① 분기 허용. 동일 user 의 두 번째 identity (manual `linkIdentity()`) → ① 분기 false → ② M-INTENT 검사 진입 캡처. M-INTENT 없으면 reject 확인.<br/>㊴ **Kakao link conflict 차단 PoC (R15 #6).** 기존 Google user 가 Kakao `linkIdentity()` 호출 시 trigger 가 `v_prior_identity_count > 0` 분기로 terms_consents 재INSERT skip 캡처. 임시로 first-creation 가드 제거 후 동일 흐름 → ON CONFLICT DO NOTHING 가 fallback 으로 동작하지만 정상은 첫 가드. 두 layer 방어 모두 캡처.<br/>**Hook payload + anonymous upgrade + Kakao version (wake R16 #1~#3).**<br/>㊵ **Hook event identity_data 부재 PoC (R16 #1).** Hook event 의 `event.user.identities` 가 `[]` (pre-insert empty) 임을 캡처. 임시로 Hook 본문에 `event.user.identities[0].identity_data.service_terms IS NULL → reject` 부활 후 정상 Kakao signup 시도 → 모든 Kakao OAuth signup reject 캡처 (negative). 정정 후 trigger (auth.identities AFTER INSERT) 가 Kakao `/v2/user/service_terms` 결과 또는 검증된 fallback payload 로 required tag 동의를 검사하는 정상 흐름 확인.<br/>㊶ **Anonymous upgrade M-INTENT PoC (R16 #2).** Phase 2 anonymous user (`auth.users.is_anonymous = true`, identity 0건) 가 OAuth 첫 identity 추가 시 G2 ① 의 (ii) 분기 진입 → M-INTENT 없으면 reject 캡처. M-INTENT 발급 후 동일 흐름 → 허용 + intent consume. anonymous → OAuth upgrade 가 manual-link audit 우회 못 함 입증.<br/>㊷ **Kakao consent version PoC (R16 #3).** Kakao signup 후 `public.terms_consents` 의 각 row 의 `version` 컬럼이 **`public.terms.version` (각 term 의 active version)** 과 일치 캡처. 임시로 trigger 본문을 `COALESCE(v_service_terms->>'version', 'kakao_sync')` 로 되돌리고 동일 signup → 모든 term row 가 같은 version 으로 저장됨 + audit 가 `public.terms.version` 기준 검색 시 missing 으로 보임을 캡처 (negative).<br/>㊸ **Vault 제외 PoC (R17 #1).** Supabase Project Settings → Vault 에 `AUTH_EXTERNAL_GOOGLE_CLIENT_ID` 등을 등록한 환경에서 `supabase config push --project-ref <REF>` 실행 시 `[auth.external.google].client_id = env(AUTH_EXTERNAL_GOOGLE_CLIENT_ID)` 가 unresolved 로 실패함을 캡처 (negative). 동일 키를 `supabase secrets set --project-ref <REF> AUTH_EXTERNAL_GOOGLE_CLIENT_ID=...` 로 옮긴 뒤 push 가 성공함을 캡처 (positive). Vault 는 Postgres `vault.secrets` store 일 뿐 `env()` 해석 channel 이 아님을 입증.<br/>㊹ **HK-REG-3 trigger 검증 PoC (R17 #2).** `before-user-created` Hook 안에서 Kakao `service_terms` 검사를 수행하는 stale 구현은 `event.user.identities = []` + `identity_data` 부재로 항상 통과(false-negative) 됨을 캡처 (negative). 정정 후 Kakao `service_terms` 검사는 §7.1.5 H3 파일 ⑦ `auth.identities` AFTER INSERT trigger 가 담당 — 미동의 raise 가 identity insert 시점에 발생함을 캡처 (positive).<br/>㊺ **Term-version per-term 저장 PoC (R17 #3).** `private.create_pending_terms_consent_internal` 이 `term_ids = ARRAY[<service_terms_id>, <privacy_policy_id>]` 로 mint, 두 term 의 `version` 이 서로 다른 상태 (`service_terms.version='2026-05'`, `privacy_policy.version='2026-06'`). `consume_pending_terms_consent_internal` 호출 후 `public.terms_consents` 의 row 2개가 각각 자신의 `t.version` 으로 저장됨을 캡처 (positive). 임시로 함수를 `row_terms_version` 단일 값으로 되돌리면 두 row 가 동일 version 으로 저장돼 audit 누락이 발생함을 캡처 (negative).<br/>㊻ **Kakao agreed-tag mapping PoC (R17 #4).** Kakao signup `service_terms = [{"tag":"service","agreed":true},{"tag":"privacy","agreed":false}]` payload 로 진입 → `public.kakao_term_mapping` (kakao_tag → public_term_id) 가 `privacy` 를 required 로 매핑하므로 trigger 가 `kakao required terms not fully agreed` raise (negative). 동일 payload 의 `privacy.agreed=true` 로 정정 후 `public.terms_consents` 에 `source='kakao_sync'` 두 row 가 mapping 결과 (`service_terms`, `privacy_policy`) 로 저장됨을 캡처 (positive). 또한 `agreed=false` 인 tag 가 insert 에서 제외됨을 별도 캡처 (positive).<br/>위 45개 시나리오 중 1개라도 누락된 PR 은 §3.2 A3 + 본 게이트로 reject. | CMP-576 + CMP-577 + CMP-575 (RLS policy + cron SQL + Kakao trigger) |

본 PR (CMP-574, 단계 0) 은 Hook + gate-before-exchange + cookie-required + direct Postgres connection 을 직접 도입하지 않는다. CMP-576 PR 이 본 §7.1.5 H1~H4 + §7.1.6 cron 정본화를 추가한다. 마이그레이션 파일 6개를 H2 봉인 순서로 추가:<br/>① `_<ts1>_private_schema.sql`, ② `_<ts2>_pending_terms_consents.sql` (RLS policy 포함), ③ `_<ts3>_identity_link_intents.sql` (RLS policy 포함), ④ `_<ts4>_pending_terms_consent_fns.sql` (`create_pending_terms_consent` + `validate_pending_terms_consent` + `consume_pending_terms_consent_internal` 3개 함수 — service_role 만 GRANT for validate/consume), ⑤ `_<ts5>_create_identity_link_intent_fn.sql`, ⑥ `_<ts6>_before_user_created_terms_gate.sql` (weak gate — Kakao 분기 + google/naver allow). timestamp `<ts1> < <ts2> < ... < <ts6>` 강제. web 측은:<br/>&nbsp;&nbsp;• terms 화면 → server-side handler 가 **선택된 OAuth provider 를 매핑한 후** (UI `google` → `google`, UI `naver` → `custom:naver`) **direct Postgres connection (`SUPABASE_DB_URL_POOLER`)** 으로 `create_pending_terms_consent($1::text, '<ver>', $2::uuid[])` 호출 (`$1` = 매핑된 정본 provider id — `'google'` 또는 `'custom:naver'`, **하드코딩 금지** — wake R11 #1). server-only 채널 (anon/authenticated GRANT 없음, wake R8 #3) + **`Set-Cookie: __Host-jippin_consent_token=<token>; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=1800`** 응답 헤더 (wake R7 #1).<br/>&nbsp;&nbsp;• **terms 통과 후에만** `/api/oauth/start` 통과 → `createClient(..., { auth: { flowType: 'pkce' } })` 로 생성한 Supabase client 에서 `signInWithOAuth({ options: { redirectTo: '<app>/auth/callback', queryParams, scopes } })` 호출. `flowType` 은 `signInWithOAuth` 인자가 아니라 client auth 설정이다. terms 우회 generic OAuth 진입점은 frontend 에 노출 안 함.<br/>&nbsp;&nbsp;• **Next.js `/auth/callback` server-side Route Handler 가 gate-before-exchange 수행** — cookie 없음 → uninitiated OAuth flow 로 reject (exchange 미호출) → cookie 있음 + direct Postgres 로 `validate_pending_terms_consent` → false 시 cookie 삭제 + redirect (exchange 미호출) → true 시 **`@supabase/ssr` server client** 로 `exchangeCodeForSession` (cookie-backed, service_role admin 아님 — wake R7 #2) → `is_new_user == true` 일 때만 direct Postgres 로 `consume_pending_terms_consent_internal` 호출. **`auth.admin.deleteUser` 절대 호출 안 함** (wake#3). consume false 시 `app_metadata.terms_missing` marker UPDATE + **`auth.admin.signOut(session.access_token)` (session JWT 기준 — wake R7 #3)** + `@supabase/ssr` cookie clear + 에러 페이지.<br/>를 CMP-577 이 담당. §7.1.4 O4 (a) 의 PoC 첨부 의무는 본 §7.1.5 H4 결과 (34 시나리오 — `NEW.user_id` discriminator + Kakao `auth.identities` trigger + SELECT(id) GRANT + `[remotes.production]` 동행 + signed provider marker + preview branch secrets 포함) 로 만족한다. **마이그레이션 파일 ⑦** = `auth.identities` AFTER INSERT trigger (wake R13 #3 위치 정정) — 총 7개 파일 H2 봉인 순서로 머지.

#### 7.1.6 미동의 user cron cleanup (MUST — gate-before-exchange 보강망)

§7.1.5 H3 의 gate-before-exchange 흐름은 `exchangeCodeForSession` 호출과 `consume_pending_terms_consent_internal` 호출 사이의 backend handler 안에서 가능한 짧은 ms 단위 gap 만 남긴다. handler crash / `consume_internal` false (race lose / RLS 사고 등) 시 `auth.users` 행이 생성됐지만 `public.terms_consents` 가 없는 user 가 잔존할 수 있다. 본 user 는 §4.7 sealed flow 위반 후보 — `auth.admin.deleteUser` 를 callback 에서 호출하면 returning user 사고 위험 (wake#3) 이므로 **별도 cron cleanup 으로 처리**한다.

| 게이트 | 조건 | 책임 |
|---|---|---|
| Cron1. **명시적 `terms_missing` marker user 비활성 cron (MUST — wake#5/PnPk + wake#1/B-6d 컬럼 정정).** Supabase cron 이 다음 SQL 을 N분 주기로 실행. **`auth.users` 의 marker 컬럼은 DB 명세상 `raw_app_meta_data`** (API/JWT 필드명은 `app_metadata` 지만 DB column 은 `raw_app_meta_data`):<br/>```sql<br/>-- 명시적 terms_missing marker 가 있는 user (gate-before-exchange 의 backend handler 가<br/>-- consume false 시 raw_app_meta_data 에 set) 만 24h 후 ban. anonymous + 정상 signup user 는<br/>-- 절대 대상이 아님 — marker 없으면 cron 영향 0건.<br/>UPDATE auth.users<br/>   SET banned_until = now() + interval '100 years',<br/>       raw_app_meta_data = jsonb_set(<br/>         COALESCE(raw_app_meta_data, '{}'::jsonb),<br/>         '{terms_disabled_at}',<br/>         to_jsonb(now()::text)<br/>       )<br/> WHERE (raw_app_meta_data->>'terms_missing')::boolean IS TRUE<br/>   AND COALESCE(is_anonymous, false) = false  -- anonymous (signInAnonymously) 제외<br/>   AND (raw_app_meta_data->>'terms_missing_set_at')::timestamptz < now() - interval '24 hours'<br/>   AND banned_until IS NULL;<br/>```<br/>**marker set SQL (backend handler 의 consume false 경로 — §7.1.5 H3 step (e), 동일하게 `raw_app_meta_data` 사용):**<br/>```sql<br/>UPDATE auth.users<br/>   SET raw_app_meta_data = jsonb_set(<br/>         jsonb_set(<br/>           COALESCE(raw_app_meta_data, '{}'::jsonb),<br/>           '{terms_missing}', 'true'::jsonb<br/>         ),<br/>         '{terms_missing_set_at}', to_jsonb(now()::text)<br/>       )<br/> WHERE id = $1;  -- consume 시 user_id 가 callback handler 가 가진 값.<br/>```<br/>**범위 봉인:**<br/>&nbsp;&nbsp;• cleanup 대상 = `raw_app_meta_data->>'terms_missing' = true` **AND** `is_anonymous = false`.<br/>&nbsp;&nbsp;• **정상 신규 signup user** (`consume_internal` true → `terms_consents` row 생성됨) → marker 없음 → cron 무영향.<br/>&nbsp;&nbsp;• **Phase 2 anonymous user** (`signInAnonymously()`) → `is_anonymous = true` 로 제외. cron 무영향.<br/>&nbsp;&nbsp;• **returning user login** → marker set 안 됨 → cron 무영향.<br/>본 cron 은 `auth.admin.deleteUser` 가 아닌 ban 으로 처리해 audit trail 보존. **`app_metadata` 컬럼명 사용 시 SQL 자체가 fail** — `auth.users` 에 본 컬럼이 없어 `column "app_metadata" does not exist`. wake#1/B-6d 검증 self-check 추가 (`raw_app_meta_data` 사용 + `app_metadata` 미사용). | DevOps + CMP-575 (cron SQL) |
| Cron2. **PoC 시나리오.** staging branch 에서:<br/>&nbsp;&nbsp;• §7.1.5 H4 의 consume false 시 `terms_missing` marker 가 backend handler 에 의해 set 됨 캡처.<br/>&nbsp;&nbsp;• cron 24h 시뮬레이션 (timestamp 강제 조정) → marker 있는 user 만 `banned_until` 채워짐 확인.<br/>&nbsp;&nbsp;• **Anonymous user (`signInAnonymously()`) PoC** — anonymous row 가 24h+ 후에도 cron 무영향 (`is_anonymous=true` 조건으로 제외) 확인. **anonymous precheck 흐름 보호의 명시 negative PoC**.<br/>&nbsp;&nbsp;• 정상 signup user (terms_consents 있음) 도 무영향 캡처.<br/>CMP-576/CMP-577 PR 본문에 본 4종 PoC 캡처 첨부. | CMP-576 + CMP-577 |
| Cron3. **monitoring alert.** 24h `terms_missing` marker user N 건 이상 발생 시 (cron 실행 시) Slack/email 알림. backend handler 의 race lose / crash 빈도 모니터링. | DevOps |

본 PR (CMP-574, 단계 0) 은 cron 자체를 도입하지 않는다. CMP-575 의 RLS / cron 트랙이 정본화하며 CMP-576/CMP-577 PR 머지 직전 본 §7.1.6 Cron1 SQL + Cron2 PoC 캡처가 첨부돼야 §3.2 A3 게이트 통과.

#### 7.1.7 Production Auth config application gate (MUST — wake R9 #3)

Supabase GitHub integration 은 **production 배포 시 migration / Edge Functions / Storage 만 적용하고 `[api]`, `[auth]` 등 일반 config 는 default 로 무시한다** (§7.2 R5 와 동일한 동작). 따라서 CMP-576 PR 이 `supabase/config.toml` 의 `[auth].enable_signup = true` + `[auth.external.*].enabled = true` + `redirect_uri = env(SUPABASE_AUTH_EXTERNAL_REDIRECT_URI)` 등을 바꿔 머지해도 **production Supabase project 의 Auth 설정은 `Disabled` 상태로 남을 수 있다** — preview branch 에서는 PoC 가 통과하지만 production 에서 모든 Google/Naver/Kakao signup 이 fail 한다.

§7.2 R5 (Data API Dashboard 봉인) 와 같은 수준의 **production Auth config Dashboard / `supabase config push` 검증 게이트**를 A3 완료 조건에 추가한다.

| 게이트 | 조건 | 책임 |
|---|---|---|
| A-AUTH-1. **Production provider Dashboard 활성화 확인 (MUST).** Supabase Console (production project) → Authentication → Providers 에서 Google / Naver (custom OAuth) / Kakao 각 provider 가 **Enabled** 상태 + 각 `Client ID` / `Client secret` 등록 + `Redirect URL` 이 `https://<SUPABASE_PROJECT_REF_PROD>.supabase.co/auth/v1/callback` 으로 봉인됨 캡처. CMP-576 PR 본문에 dashboard 캡처 (secret 마스킹) 첨부. | CMP-576 + DevOps |
| A-AUTH-2. **`[auth].enable_signup` production 토글 확인.** Console → Authentication → Sign-Ups 또는 동등 panel 에서 신규 가입 허용 = ON 인지 확인. `[auth.email].enable_signup = false` 는 별도 panel 에서 OFF 유지 캡처 (이메일 signup 영구 차단). | CMP-576 + DevOps |
| **A-AUTH-2b. Production app redirect URL gate (MUST — A-AUTH-3 전에 통과, wake R10 #4 + R13 #5).** `supabase/config.toml` 의 `[auth].site_url` / `additional_redirect_urls` 가 local-only (예: `http://localhost:3000`, `http://127.0.0.1:3000`) 상태에서 그대로 `supabase config push` 하면 **production OAuth callback (`redirectTo=https://<prod-app>/auth/callback`) 이 Supabase redirect allow-list 에서 빠짐** → callback reject 또는 localhost fallback. 정정 옵션 중 하나:<br/>&nbsp;&nbsp;① **`[remotes.production]` + `[remotes.production.auth]` override 블록 동시 추가 (권장 — config-as-code).** Supabase CLI 가 `[remotes.<branch>]` override 를 적용하려면 같은 branch 의 root remote 선언이 먼저 있어야 한다 (wake R13 #5). 정본:<br/>&nbsp;&nbsp;&nbsp;&nbsp;```toml<br/>&nbsp;&nbsp;&nbsp;&nbsp;[remotes.production]<br/>&nbsp;&nbsp;&nbsp;&nbsp;project_id = "<SUPABASE_PROJECT_REF_PROD>"  # A1 에서 채움<br/>&nbsp;&nbsp;&nbsp;&nbsp;<br/>&nbsp;&nbsp;&nbsp;&nbsp;[remotes.production.auth]<br/>&nbsp;&nbsp;&nbsp;&nbsp;site_url = "https://<prod-app>"<br/>&nbsp;&nbsp;&nbsp;&nbsp;additional_redirect_urls = ["https://<prod-app>", "https://<prod-app>/auth/callback", "https://<prod-app>/**"]<br/>&nbsp;&nbsp;&nbsp;&nbsp;```<br/>&nbsp;&nbsp;&nbsp;&nbsp;**`[remotes.production] project_id` 미선언 시 `[remotes.production.auth]` override 가 `supabase config push` 에서 적용 안 되거나 silent skip** — config-as-code 의 정본 형식. §3.2 A1.1 의 `[remotes.development]` / A1.2 의 `[remotes.staging]` 과 동일 패턴.<br/>&nbsp;&nbsp;② **Dashboard direct edit (보조)** — Console (production) → Authentication → URL Configuration 에서 `Site URL` 과 `Redirect URLs` 에 production app callback 추가. CLI 가 push 한 local-only 값을 dashboard 가 override.<br/>옵션 ① 권장 (config-as-code). 옵션 ② 사용 시 후속 `supabase config push` 가 dashboard 값을 덮어쓸 위험 → 옵션 ① 로 보완.<br/>**검증 PoC**: production project 에서 OAuth callback redirect URL 4개 (origin / `/auth/callback` / `/**`) 가 모두 redirect allow-list 에 들어있는지 dashboard 캡처. `https://<prod-app>` 의 sample callback URL 도 reject 안 됨 확인. **A-AUTH-3 의 `supabase config push` 실행 시점에 본 게이트가 이미 통과 상태여야 한다** — 그렇지 않으면 A-AUTH-4 smoke 가 redirect rejection 으로 fail. | CMP-576 + DevOps |
| A-AUTH-3. **`supabase config push` 동기 (가용 시 — 권장).** A-AUTH-2b 통과 후 `supabase config push --project-ref <SUPABASE_PROJECT_REF_PROD>` CLI 가 production 에서 가용한 시점에는 본 명령으로 config.toml 의 `[auth.*]` + `[remotes.production.auth]` 블록을 production 에 동기. 출력 (적용된 항목 리스트 — secret 마스킹) 을 PR 본문에 캡처. CLI 미가용 시 A-AUTH-1 + A-AUTH-2 + A-AUTH-2b 의 dashboard 캡처가 SSOT. | CMP-576 + DevOps |
| A-AUTH-4. **Production signup smoke PoC.** A-AUTH-1~3 후 production project 에서 실 OAuth signup 1회 시도 (테스트 계정) → `auth.users` row 생성 + terms_consents row + `raw_app_meta_data->>'provider'` 확인. **smoke test 통과 시 provider Enabled 상태 유지** — production Google/Naver/Kakao signup 이 즉시 가용해야 함. **Disabled 회귀는 smoke 실패 또는 incident 대응 시에만 (A-AUTH-5 경로)**. PoC 결과 (성공 시 user row + terms_consents row + screenshot) PR 본문 첨부. 테스트 계정의 `auth.users` row 는 PoC 후 `auth.admin.deleteUser(test_user_id)` 로 cleanup (운영 계정 잔존 방지 — 일반 user 가 아닌 본 PoC 한정). | CMP-576 + DevOps |
| A-AUTH-5. **사후 노출 회복 절차 (incident 대응 전용).** 다음 시나리오 중 하나가 발생한 경우에만 실행 — 정상 완료 흐름에서는 사용하지 않는다:<br/>&nbsp;&nbsp;• A-AUTH-4 smoke 실패 (signup 자체가 fail / terms_consents row 미생성).<br/>&nbsp;&nbsp;• 사후 사고 (terms gate 우회 발견 / provider 시크릿 leak / `service_terms` 검증 fail).<br/>회복 절차: Console → Authentication → Providers 에서 즉시 사고 관련 provider Disabled 토글 → 1Password 의 service role / anon key (해당 provider client secret 포함) 회전 → CMP-576 PR revert 또는 hotfix PR. **정상 smoke 통과 후 본 절차를 routinely 실행하면 production signup 이 즉시 다시 fail** (wake R10 #1). | CMP-576 + DevOps |

§3.2 A3 게이트는 본 §7.1.7 A-AUTH-1~A-AUTH-4 통과 캡처 첨부를 머지 직전 의무로 추가한다. CMP-575/CMP-577 트랙은 본 게이트 의존성 없음 (A-AUTH 는 CMP-576 단독 책임).

#### 7.1.8 `before-user-created` Auth Hook 등록 절차 (MUST — wake R11 #3)

§7.1.5 H2 의 파일 ⑥ 은 `private.before_user_created_terms_gate(event jsonb)` 함수 정의 + GRANT/REVOKE 만 추가한다. **함수 정의만으로는 Supabase Auth 가 본 hook 을 호출하지 않는다** — Auth 측에 hook 활성화 + URI 등록을 별도 절차로 봉인해야 Kakao `service_terms` reject 등 H4 시나리오가 실제 실행된다. 등록 채널 2개 (둘 중 하나 — config-as-code 권장):

| 게이트 | 조건 | 책임 |
|---|---|---|
| HK-REG-1. **`supabase/config.toml` `[auth.hook.before_user_created]` 블록 등록 (권장 — config-as-code).** Supabase CLI config 정본 형식:<br/>```toml<br/>[auth.hook.before_user_created]<br/>enabled = true<br/>uri = "pg-functions://postgres/private/before_user_created_terms_gate"<br/>```<br/>정본: https://supabase.com/docs/guides/auth/auth-hooks#configuring-a-hook-with-the-cli<br/>본 블록을 `supabase/config.toml` 에 추가하면 `supabase db push` / `supabase config push` 가 production / dev / staging persistent branch 에 hook 등록을 동기. CMP-576 PR 이 §7.1.5 파일 ⑥ 머지와 같은 PR 에 본 토글 추가. | CMP-576 |
| HK-REG-2. **Dashboard direct edit (보조 — HK-REG-1 미가용 시).** Supabase Console (production project) → Authentication → Hooks → "Before user created" → **Enable** 토글 ON + Hook Type = `Postgres function` + Function = `private.before_user_created_terms_gate`. dev / staging persistent branch 도 동일하게 Console 에서 등록. **HK-REG-1 사용 시 본 단계 불필요** — config-as-code 가 동기.<br/>HK-REG-2 단독 사용 시 후속 `supabase config push` 가 dashboard 값을 overwrite 할 위험. HK-REG-1 + Dashboard 확인 조합 권장. | CMP-576 + DevOps |
| HK-REG-3. **검증 PoC (MUST — wake R17 #2 정정).** Hook event 는 pre-insert `auth.users` + `identities=[]` 라 Kakao `service_terms` 검사가 Hook 안에서는 불가능 (wake R16 #1 봉인). 정본 검증 위치는 **`auth.identities` AFTER INSERT trigger (§7.1.5 H3 파일 ⑦)** 이되, service terms 원천은 Kakao `/v2/user/service_terms` API 응답이다. 따라서 HK-REG-3 PoC 는 trigger 기준으로 정정:<br/>&nbsp;&nbsp;• **Hook 활성화 확인 시나리오.** Hook 본문은 일반 OAuth signup 을 가로채지 않고 (`{}` allow) 통과시킴을 입증 — Hook 자체의 동작 PoC 는 event-level 가드 (e.g. banned domain check) 가 있으면 그 경로로, 없으면 "정상 Hook 호출 + `{}` 응답 + identity insert 흐름 진행" 확인 캡처.<br/>&nbsp;&nbsp;• **Kakao `service_terms` 누락 negative** → **`auth.identities` AFTER INSERT trigger** 가 Kakao `/v2/user/service_terms` 조회 결과 required tag 미동의/누락을 확인 → `RAISE EXCEPTION 'kakao required terms not fully agreed'` → identity insert rollback + 같은 transaction `auth.users` rollback → **`auth.users` 0건 + `auth.identities` 0건** 캡처. Hook reject 가 아닌 trigger raise.<br/>&nbsp;&nbsp;• **Hook 등록 비활성 negative** — `config.toml` 의 `enabled = false` 또는 Dashboard Disable 후 정상 Kakao signup → Hook 미호출 + trigger 는 여전히 firing (DB trigger 는 hook 등록과 무관) → `service_terms` 있으면 정상 영속화 / 없으면 trigger raise. **Hook 등록 자체의 정상 호출 입증은 위 첫 시나리오로 확인** — Kakao service_terms 검증은 Hook 의 책임이 아님 (R17 #2).<br/>**HK-REG-1 / HK-REG-2 등록 누락 시** Hook 미호출. **단 Kakao service_terms 강제는 trigger 가 책임**이라 Hook 등록 누락이 Kakao 보안 봉인을 깨지 않음. Hook 등록은 미래 event-level 가드 추가 시점의 전제. §7.1.5 H4 의 정상 통과는 본 HK-REG 통과 + trigger 통과 동시 전제. | CMP-576 |
| HK-REG-4. **§3.2 A3 게이트 추가.** A3 PR 머지 직전 HK-REG-1 의 `supabase/config.toml` 블록 + HK-REG-3 의 PoC 캡처 첨부 의무. config push 가 production / dev / staging 모두에 동기됐는지 `supabase config diff` 출력 (적용된 hook 블록만) 첨부. | CMP-576 |

본 PR (CMP-574, 단계 0) 은 `[auth.hook.before_user_created]` 블록 자체를 도입하지 않는다 (Hook 함수가 아직 없음 — §7.1.5 가 정본화). CMP-576 PR 이 파일 ⑥ (Hook 함수) 머지와 동시에 본 블록을 `supabase/config.toml` 에 추가.

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
| **W1. project root `.env`** | Local CLI (`supabase start`, `supabase db diff`, `supabase config push` 등) | **repo root 의 `.env`** (즉 `supabase/` 와 같은 레벨의 sibling — `C:\Users\jhyou\2026\jippin\.env`) 에 `KEY=value` 1줄씩. Supabase CLI 정본은 `env()` 가 **project directory 의 root `.env`** 를 detect 하는 것이다 (https://supabase.com/docs/guides/local-development/managing-config#using-secrets-inside-configtoml). `supabase/.env` 가 아니라 **project root `.env`** 다. 본 파일은 본 PR 시점에 작성되지 않는다 (CMP-576 가 `.env.example` 동행 추가). | ✅ (`.gitignore` 의 `.env` 패턴이 root `.env` 를 매칭. 본 PR 시점 self-check `git check-ignore -v .env`.) |
| **W2. `supabase secrets set` CLI (branch config env secret)** | preview/production Supabase project 의 config env (`env(...)`) 가 참조 — **`config.toml` 의 `env()` SSOT 채널** | `supabase secrets set --project-ref <SUPABASE_PROJECT_REF_PROD> SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID=<value>` 등. GitHub Actions 에서 `SUPABASE_ACCESS_TOKEN` 으로 인증 후 호출. 정본: https://supabase.com/docs/guides/deployment/branching/configuration#managing-secrets-for-branches<br/>**Project Settings → Vault (Postgres `vault.secrets` 저장소) 는 본 채널의 정본 source 아님** (wake R10 #2). Vault 는 DB 안 application 시크릿용이지 `config.toml env()` 값을 채우지 않는다. CMP-576 PR 본문에 `supabase secrets list --project-ref <REF>` 출력 (값 마스킹) 캡처 의무. | N/A |
| **W3. Encrypted dotenv (`supabase secrets set --env-file`)** | W2 와 동일 — `.env` 파일 일괄 등록 | `supabase secrets set --project-ref <REF> --env-file <encrypted.env>` 등. local `.env` 또는 KMS-encrypted dotenv 를 한 번에 push 하는 채널. 정본: 위 W2 와 동일. | N/A |
| **W4. GitHub Actions env 주입 (제한적)** | 본 레포의 GitHub Actions job 이 `supabase` CLI 를 호출하는 step 의 `env:` 블록 | step 의 `env:` 에 `SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID: ${{ secrets.SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID }}` 식으로 주입. **integration 자체가 호출하는 deploy 단계에는 적용 안 됨** — W2 / W3 가 정본. | N/A |

> **흔한 함정.** 모노레포의 application `.env` (예: `apps/web/.env`, `apps/api/.env`) 가 이미 있어서 같은 변수를 거기 추가하기 쉽지만, Supabase CLI 는 **`apps/**/.env` 를 읽지 않는다**. `env()` 해석은 오직 **repo root `.env`** (또는 W2/W3/W4) 에서만 일어난다. local 에서 `supabase start` 시 unresolved OAuth 변수가 나오면 가장 먼저 확인할 곳은 root `.env` 의 KEY 이름.

**활성화 PR 의 봉인 절차 (CMP-576 PR 본문 self-check 의무).**

| 단계 | 조건 | 책임 |
|---|---|---|
| W-A. **root `.env.example` 동행 추가.** **repo root 의 `.env.example`** (또는 `supabase/.env.example` — 둘 다 placeholder 용. 정본 read 위치는 root `.env`) 에 본 PR 이 도입하는 `env()` 변수명을 placeholder 값과 함께 등록 (예: `SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID=<google-oauth-client-id>`). **`apps/api/.env.example`, `apps/web/.env.example` 만 업데이트하는 PR 은 본 게이트로 reject** — supabase CLI 가 안 읽는 위치만 갱신했기 때문. | CMP-576 |
| W-B. **W2/W3 CLI secrets 등록 (MUST — Vault 사용 금지).** **Production + Development + Staging + preview branch (ephemeral) 4종 모두** 에 **`supabase secrets set --project-ref <REF> KEY=value`** (개별) 또는 **`supabase secrets set --project-ref <REF> --env-file <encrypted.env>`** (encrypted dotenv) 실행. **Preview branch secret provisioning (wake R13 #7).** Supabase branch secrets 는 branch-specific 이므로 production/dev/staging persistent branch 만 등록하면 **PR preview branch (Automatic Branching 으로 생성된 ephemeral branch) 가 OAuth env 를 못 받음** → preview signup PoC fail. 정정 옵션:<br/>&nbsp;&nbsp;① **`.env.preview` encrypted dotenv 자동 주입 — wrapper workflow (§6.3)** 가 preview branch 생성 webhook 수신 시 `supabase secrets set --project-ref <preview_branch_ref> --env-file <encrypted_preview.env>` 호출. encrypted dotenv 는 GitHub Secrets 의 KMS-encrypted blob 또는 sops/age 로 관리.<br/>&nbsp;&nbsp;② **persistent dev branch 의 secret 을 자동 cascade — Supabase 정본** (가용 시): development persistent branch 의 secret 이 그 자식 preview branch 로 자동 상속되는지 확인 (`supabase branches secrets ...` 옵션, Supabase 정본 미확정 시 ① fallback).<br/>옵션 ① 이 안전한 정본 (config-as-code). 옵션 ② 가용 시 단순화 가능 — CMP-576 가 Supabase 정본 확인 후 결정.<br/>**Project Settings → Vault 등록은 `env()` 해석 채널 아님 — 사용 시 W-B 미통과** (wake R10 #2).<br/>PoC: 4종 (prod/dev/staging/preview ephemeral 1개 샘플) 모두 `supabase secrets list --project-ref <REF>` 출력 (값 마스킹) PR 본문에 첨부. preview branch 의 경우 옵션 ① wrapper 실행 후 직접 OAuth signup PoC 가 통과 (`env(...)` resolved) 캡처. | CMP-576 (DevOps + Auth Lead) |
| W-C. **검증 PoC — root `.env` resolve 확인.** 로컬 검증은 다음 시퀀스로:<br/>① repo root 에 `.env` 생성 (예: `printf 'SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID=test-id\nSUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET=test-secret\n' > .env`)<br/>② `supabase start` 또는 `supabase db diff` 가 unresolved env 로 fail 하지 않고 통과<br/>③ 같은 변수를 root `.env` 에서 제거하면 명령이 unresolved env 로 fail 함을 캡처 (positive + negative 양쪽 검증)<br/>④ staging branch 에서 `supabase db diff` / `supabase status` 가 W2/W3 콘솔 값으로 통과하는지 확인.<br/>실패하면 변수명 / 등록 채널 (W1~W4) 매칭 재확인. | CMP-576 |
| W-D. **`.gitignore` 봉인 확인.** repo root `.env` 가 `.gitignore` 의 `.env` 패턴에 매칭되는지 self-check (`git check-ignore -v .env`). 미매칭 시 본 PR 에서 명시 추가. **`supabase/.env` 위치는 정본이 아니므로 본 검증의 SSOT 가 아니다** — root `.env` 가 봉인 대상. | CMP-576 |

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

# 15) Supabase env() local 정본은 project root `.env` 임을 봉인.
git grep -nE 'project root `\.env`|repo root `\.env`|W1\. project root' docs/runbooks/supabase-branching.md supabase/config.toml
# → §7.4 W1 + W-A/W-C/W-D + 흔한 함정 박스 + config.toml [auth.external.*] 주석 매칭.

# 16) SQL Auth Hook GRANT 봉인 (§7.1.5 H2) — supabase_auth_admin role.
git grep -nE 'supabase_auth_admin|GRANT EXECUTE ON FUNCTION|GRANT USAGE ON SCHEMA' docs/runbooks/supabase-branching.md
# → §7.1.5 H2 표 + GRANT SQL 블록 매칭.

# 17) pending_terms_consents pre-user intent 봉인 (§7.1.5 H3).
git grep -nE 'pending_terms_consents|consent_token|pre-user terms consent intent' docs/runbooks/supabase-branching.md
# → §7.1.5 H3/H4 표 + SQL 블록 매칭.

# 18) provider redirect_uri 환경별 parameterize 봉인 (§7.1.4 O2).
git grep -nE 'SUPABASE_AUTH_EXTERNAL_REDIRECT_URI|127\.0\.0\.1:54321/auth/v1/callback|SUPABASE_PROJECT_REF_(DEV|STAGING)' docs/runbooks/supabase-branching.md supabase/config.toml
# → O2 의 4환경 매트릭스 + config.toml 주석 매칭.

# 19) supported consent token channel (signInWithOAuth options.data) 봉인 (§7.1.5 H3).
git grep -nE "options: \{ data: \{ consent_token|raw_user_meta_data|PKCE state.*비정본" docs/runbooks/supabase-branching.md
# → H3 supported channel + 비정본 경고 매칭.

# 20) Hook 함수 PUBLIC REVOKE + private schema 봉인 (§7.1.5 H2).
git grep -nE "REVOKE EXECUTE ON FUNCTION|REVOKE ALL ON SCHEMA private|CREATE SCHEMA IF NOT EXISTS private|hook 전용 schema" docs/runbooks/supabase-branching.md
# → H2 SQL 블록 + 역할 분리 봉인 매칭.

# 21) manual link discriminator (identity_link_intents) + db diff --linked 봉인.
git grep -nE 'identity_link_intents|M-INTENT|supabase db diff --linked' docs/runbooks/supabase-branching.md
# → §7.1.1 G2 + §7.1.2 M-INTENT + §3.2 A1.1/A1.2 --linked 매칭.

# 22) Hook payload nested 경로 봉인 (§7.1.5 H3).
git grep -nE "event->'user'->'user_metadata'|event->'user'->'app_metadata'|event->'user'->'identities'" docs/runbooks/supabase-branching.md
# → H3 정본 경로 매칭. top-level event->'user_metadata' 는 비정본.

# 23) Hook error object 정본 형식 (§7.1.5 H3/H4).
git grep -nE 'jsonb_build_object.*error.*http_code|fail-open|"\{\}"::jsonb' docs/runbooks/supabase-branching.md
# → H3 SQL + H4 시나리오 ⑩ 매칭.

# 24) Kakao Sync 분기 봉인 (§7.1.5 H3 + AGENTS.md §4.7 #5).
git grep -nE 'Kakao Sync|kakao_terms_missing|service_terms|kakao_sync' docs/runbooks/supabase-branching.md
# → H3 provider 분기 + H4 ⑨ + 마이그레이션 함수 CHECK 매칭.

# 25) 마이그레이션 파일 순서 (§7.1.5 H2 — 객체 생성 → GRANT).
git grep -nE '파일 ①|파일 ②|파일 ⑥|_private_schema\.sql|_pending_terms_consents\.sql|_before_user_created_terms_gate\.sql' docs/runbooks/supabase-branching.md
# → H2 봉인 + §7.1.5 결론 단정 매칭.

# 26) callback-after-insert 봉인 (§7.1.5 H3 — options.data 비정본 + redirectTo+cookie 정본).
git grep -nE 'callback-after-insert|options\.data.*정본 옵션 아님|__Host-jippin_consent_token|redirectTo.*consent_token' docs/runbooks/supabase-branching.md
# → H3 + 비정본 블록 + cookie 봉인 매칭.

# 27) atomic consume race-free (§7.1.5 H3/H4 — wake#2).
git grep -nE 'consume_pending_terms_consent_atomic|GET DIAGNOSTICS consumed_count|race-free|단일 conditional UPDATE' docs/runbooks/supabase-branching.md
# → H3 SQL + H2 SQL 블록 + H4 ⑦ 매칭.

# 28) RLS policy 명시 봉인 (§7.1.5 H3/H2 — wake#3).
git grep -nE 'CREATE POLICY pending_terms_consents_auth_admin|FOR SELECT TO supabase_auth_admin|FORCE ROW LEVEL SECURITY' docs/runbooks/supabase-branching.md
# → H2 SQL + H3 봉인 + H4 ⑫ 매칭.

# 29) terms_consents 영속화 (§7.1.5 H3/H4 — wake#4 — source='internal_signup').
git grep -nE "INSERT INTO public\.terms_consents|source='internal_signup'|terms_consents.*영속화|wake#4" docs/runbooks/supabase-branching.md
# → H2 SQL + H3 흐름 + H4 ⑧/⑯ 매칭.

# 30) __Host- cookie Path=/ 봉인 (§7.1.5 H3 wake#1).
git grep -nE "__Host-jippin_consent_token=.*Path=/|__Host-.*prefix 규약" docs/runbooks/supabase-branching.md
# → H3 cookie 설정 + H4 ⑤ + §3.2 A3 매칭.

# 31) gate-before-exchange + validate_pending_terms_consent service_role 만 (§7.1.5 wake#JMb + #JMY).
git grep -nE 'gate-before-exchange|validate_pending_terms_consent|service_role 만|consume_pending_terms_consent_internal' docs/runbooks/supabase-branching.md
# → H3 흐름 + H2 SQL + H4 ⑦~⑫ 매칭.

# 32) callback deleteUser 금지 (§7.1.5 H3/H4 wake#3).
git grep -nE 'deleteUser.*절대.*안 함|deleteUser.*안 함|returning user 사고|signup vs login' docs/runbooks/supabase-branching.md
# → H3 비정본 (d) + H4 ⑥~⑩ + §3.2 A3 매칭.

# 33) §7.1.6 미동의 user cron cleanup (gate-before-exchange 보강).
git grep -nE '7\.1\.6 미동의 user|banned_until|terms_missing_disabled_at|terms_disabled_at|Cron1\.' docs/runbooks/supabase-branching.md
# → §7.1.6 표 + SQL 매칭.

# 34) no-cookie callback reject + cookie-required (wake R7 #1/PnPZ).
git grep -nE 'uninitiated OAuth flow|no-cookie callback|cookie 없음.*reject|no-cookie' docs/runbooks/supabase-branching.md
# → H3 step (a) + H4 ⑥ + 비정본 (c) 매칭.

# 35) cookie-backed @supabase/ssr server client (wake R7 #2/PnPc).
git grep -nE 'createServerClient|@supabase/ssr|cookie-backed.*server client|PKCE.*verifier' docs/runbooks/supabase-branching.md
# → H3 채널 분리 + H4 ⑧/⑪ + 비정본 (b) 매칭.

# 36) session JWT signOut (wake R7 #3/PnPf).
git grep -nE 'session.*JWT.*signOut|signOut\(session\.access_token\)|session JWT 기준|UUID.*아닌' docs/runbooks/supabase-branching.md
# → H3 step (e) + H4 ⑩/⑬ + 비정본 (d) 매칭.

# 37) direct Postgres connection (wake R7 #4/PnPh) + anonymous cron 제외 (wake R7 #5/PnPk).
git grep -nE 'direct Postgres connection|SUPABASE_DB_URL_POOLER|is_anonymous.*false|terms_missing.*marker|signInAnonymously' docs/runbooks/supabase-branching.md
# → H3 채널 분리 + §7.1.6 Cron1 SQL + H4 ⑫/⑳ 매칭.

# 38) raw_app_meta_data 컬럼 정정 (wake R8 #1/B-6d).
git grep -nE 'raw_app_meta_data|column "app_metadata" does not exist' docs/runbooks/supabase-branching.md
# → §7.1.5 H3 step (e) + §7.1.6 Cron1 SQL + marker SQL + H4 ㉒ 매칭.

# 39) 다중 required term_id 영속화 (wake R8 #2/B-6i).
git grep -nE 'term_ids uuid\[\]|p_term_ids|unnest\(row_term_ids|service_terms.*privacy_policy' docs/runbooks/supabase-branching.md
# → create_pending_terms_consent signature + consume INSERT + H4 ㉓ 매칭.

# 40) server-only consent token mint (wake R8 #3/B-6m).
git grep -nE 'create_pending_terms_consent.*server-only|REVOKE EXECUTE.*FROM PUBLIC, anon, authenticated|server-only direct Postgres path' docs/runbooks/supabase-branching.md
# → H2 SQL + H3 ① + 비정본 + H4 ㉔ 매칭.

# 41) SECURITY DEFINER cross-schema GRANT (wake R8 #4/B-6o).
git grep -nE 'GRANT SELECT ON TABLE public\.terms|GRANT INSERT ON TABLE public\.terms_consents|GRANT UPDATE \(raw_app_meta_data\) ON TABLE auth\.users|cross-schema GRANT' docs/runbooks/supabase-branching.md
# → H2 파일 ① 의 cross-schema GRANT + H4 ㉕ 매칭.

# 42) O4 stale hook-only / deleteUser 제거 (wake R9 #1).
git grep -nE 'stale.*비정본|§7\.1\.5 정본 redirect|stale hook-only|stale flow 비정본' docs/runbooks/supabase-branching.md
# → §7.1.4 O4 정정 + §3.2 A3 매칭.

# 43) supabase-status.yml wrapper 선행 PR 봉인 (wake R9 #2).
git grep -nE '단계 1 진입 전 \(선행 PR|wrapper 선행 PR|stage 1 ↔ stage 2 사이 required DB check 공백' docs/runbooks/supabase-branching.md
# → §3.2 A4 정정 매칭.

# 44) §7.1.7 production Auth config gate 신설 (wake R9 #3).
git grep -nE '§7\.1\.7|A-AUTH-1|production Auth config Dashboard|supabase config push --project-ref' docs/runbooks/supabase-branching.md
# → §7.1.7 신설 + §3.2 A3 + A4 단계 3 + H4 ㉗ 매칭.

# 45) consent token provider parameterize (wake R9 #4).
git grep -nE 'provider 하드코딩 금지|선택된 provider 를 검증|Provider parameterize PoC' docs/runbooks/supabase-branching.md
# → H3 step ① + H4 ㉖ 매칭.

# 46) smoke 통과 시 provider Enabled 유지 (wake R10 #1).
git grep -nE 'provider Enabled 상태 유지|smoke test 통과 시 provider Enabled|incident 대응 전용|incident 대응일 때만' docs/runbooks/supabase-branching.md
# → §7.1.7 A-AUTH-4/A-AUTH-5 + H4 ㉗ A-AUTH-4 매칭.

# 47) W2 = supabase secrets set / encrypted dotenv 만 (wake R10 #2 — Vault 제거).
git grep -nE 'supabase secrets set|encrypted dotenv|Vault 사용 금지|Vault 등록은' docs/runbooks/supabase-branching.md
# → §7.4 W2/W3 + W-B + H4 ㉙ 매칭.

# 48) custom:naver provider 정규화 (wake R10 #3).
git grep -nE 'custom:naver|UI provider → Supabase provider id 매핑|custom-oauth-providers' docs/runbooks/supabase-branching.md
# → H3 step ① mapping + SQL CHECK + H4 ㉖ + A-AUTH-1 매칭.

# 49) production redirect URL override (wake R10 #4) — A-AUTH-2b 게이트.
git grep -nE 'A-AUTH-2b|\[remotes\.production\.auth\]|Production app redirect URL gate|URL Configuration' docs/runbooks/supabase-branching.md
# → §7.1.7 A-AUTH-2b + H4 ㉗ 매칭.

# 50) Kakao Sync after-create persistence (wake R10 #5).
git grep -nE 'persist_kakao_sync_terms_consents|AFTER INSERT ON auth\.users|kakao_sync.*영속화|after-create trigger' docs/runbooks/supabase-branching.md
# → §7.1.5 H3 Kakao 영속화 표 + 파일 ⑦ SQL + H4 ㉘ 매칭.

# 51) Rollout summary provider parameterize (wake R11 #1).
git grep -nE "create_pending_terms_consent\(\\\$1::text|매핑된 정본 provider id" docs/runbooks/supabase-branching.md
# → §7.1.5 결론 단정 매칭.

# 52) M-INTENT observable discriminator (wake R11 #2 — nonce 제거).
git grep -nE "auth\.uid\(\), NEW\.provider|observable discriminator|nonce 비의존|nonce 검증은 사용하지 않는다" docs/runbooks/supabase-branching.md
# → §7.1.1 G2 + §7.1.2 M-INTENT 매칭.

# 53) §7.1.8 Auth Hook 등록 절차 (wake R11 #3).
git grep -nE '§7\.1\.8|HK-REG-1|HK-REG-3|auth\.hook\.before_user_created|pg-functions://' docs/runbooks/supabase-branching.md
# → §7.1.8 표 + §3.2 A3 매칭.

# 54) Trigger NEW.user_id discriminator (wake R13 #1 — auth.uid() 제거).
git grep -nE 'NEW\.user_id, NEW\.provider|auth\.uid\(\) 미사용|auth\.uid\(\) 가 NULL' docs/runbooks/supabase-branching.md
# → §7.1.1 G2 + §7.1.2 M-INTENT + H4 ㉚ 매칭.

# 55) H2 함수 시그니처 multi-term 정합 (wake R13 #2).
git grep -nE 'create_pending_terms_consent\(p_provider text, p_terms_version text, p_term_ids uuid\[\]\)|consume_pending_terms_consent_internal\(p_token uuid' docs/runbooks/supabase-branching.md
# → H2 파일 ④ 시그니처 매칭.

# 56) Kakao trigger auth.identities 정본 (wake R13 #3).
git grep -nE 'AFTER INSERT ON auth\.identities|auth\.identities AFTER INSERT — OAuth identity payload|persist_kakao_sync_terms_consents_after_identity_insert' docs/runbooks/supabase-branching.md
# → §7.1.5 H3 Kakao 영속화 + 파일 ⑦ + H4 ㉛ 매칭.

# 57) SELECT(id) ON auth.users predicate 권한 (wake R13 #4).
git grep -nE 'GRANT SELECT \(id, is_anonymous, raw_app_meta_data|predicate column id 에 대한 SELECT' docs/runbooks/supabase-branching.md
# → H2 파일 ① cross-schema GRANT + H4 ㉜ 매칭.

# 58) [remotes.production] root 선언 동행 (wake R13 #5).
git grep -nE '\[remotes\.production\] project_id|root remote 선언이 먼저 있어야|remotes\.production.*동행' docs/runbooks/supabase-branching.md
# → §7.1.7 A-AUTH-2b + H4 ㉝ 매칭.

# 59) Signed provider marker / path 분리 (wake R13 #6).
git grep -nE 'signed provider marker|jippin_consent_provider|Kakao callback path 분리|/auth/callback/naver' docs/runbooks/supabase-branching.md
# → H3 step (b) + H4 ㉞ 매칭.

# 60) Preview branch secrets provisioning (wake R13 #7).
git grep -nE 'Preview branch secret provisioning|env\.preview|preview-branch secret|preview_branch_ref' docs/runbooks/supabase-branching.md
# → W-B + H4 ㉟ 매칭.

# 61) O1 Vault 언급 제거 (wake R14 #1).
git grep -nE 'Vault 사용 금지|Vault \(Postgres `vault\.secrets`|Vault 비의존|vault key 이름.*stale' docs/runbooks/supabase-branching.md
# → O1 + §7.4 W2 매칭.

# 62) [storage] enabled = false 명시 (wake R14 #2).
git grep -nE 'storage.*enabled = false 명시|storage.enabled.*default|R14 #2' supabase/config.toml docs/runbooks/supabase-branching.md
# → config.toml [storage] 블록 매칭.

# 63) public.terms UUID PK 선행 migration (wake R14 #3).
git grep -nE 'public\.terms.*UUID PK|public\.terms\.id|파일 ⓪|_public_terms\.sql' docs/runbooks/supabase-branching.md
# → §7.1.5 H2 파일 ⓪ + SQL 블록 매칭.

# 64) H4 ⑩/⑳ raw_app_meta_data 정합 (wake R15 #2).
git grep -nE "raw_app_meta_data->>'terms_missing'|raw_app_meta_data->>'terms_missing_set_at'|wake R15 #2" docs/runbooks/supabase-branching.md
# → H4 ⑩/⑳ + §7.1.6 Cron1 매칭.

# 65) Kakao callback path 분리 (wake R15 #3).
git grep -nE '/auth/callback/kakao|callback path 분리.*Kakao|Kakao 는 consent-token gate 전' docs/runbooks/supabase-branching.md
# → H3 step (a) + H4 ㊱ 매칭.

# 66) term_ids deduplicate (wake R15 #4).
git grep -nE 'count\(DISTINCT t\.id\)|p_term_ids := ARRAY\(SELECT DISTINCT|dedup|term_ids deduplicate' docs/runbooks/supabase-branching.md
# → H2 파일 ④ create_pending_terms_consent + H4 ㊲ 매칭.

# 67) G2 new-user observable discriminator (wake R15 #5).
git grep -nE 'EXISTS \(SELECT 1 FROM auth\.identities WHERE user_id = NEW\.user_id|prior identity 0건|observable new-user discriminator' docs/runbooks/supabase-branching.md
# → §7.1.1 G2 ① + H4 ㊳ 매칭.

# 68) Kakao link conflict guard (wake R15 #6).
git grep -nE 'v_prior_identity_count|First-creation 제한|ON CONFLICT \(user_id, term_id, version\) DO NOTHING' docs/runbooks/supabase-branching.md
# → §7.1.5 H3 파일 ⑦ + H4 ㊴ 매칭.

# 69) Hook event identity_data 부재 (wake R16 #1).
git grep -nE 'Hook event.*보장되는 field|event\.user\.identities.*\[\]|stale.*identities empty' docs/runbooks/supabase-branching.md
# → H3 Hook 본문 정정 + H4 ㊵ 매칭.

# 70) Anonymous upgrade M-INTENT 강제 (wake R16 #2).
git grep -nE 'is_anonymous = true AND prior identity 0건|anonymous → OAuth upgrade.*manual link intent|M-INTENT 검사로 진입.*\(ii\)' docs/runbooks/supabase-branching.md
# → §7.1.1 G2 ① + H4 ㊶ 매칭.

# 71) Kakao consent local term.version (wake R16 #3).
git grep -nE "SELECT NEW\.user_id, t\.id, t\.version|각 term 의 active local public\.terms\.version|wake R16 #3" docs/runbooks/supabase-branching.md
# → 파일 ⑦ SELECT + H4 ㊷ 매칭.

# 72) env() source 에서 Vault 제거 (wake R17 #1).
git grep -nE 'Vault.*env\(\) 해석 channel 이 아님|vault\.secrets.*env\(\) 해석|wake R17 #1' supabase/config.toml docs/runbooks/supabase-branching.md
# → config.toml `[auth.external.*]` 주석 + H4 ㊸ 매칭. Vault 가 env() 정본 목록에서 제외되었음을 입증.

# 73) HK-REG-3 — Kakao service_terms 검증을 Hook 밖으로 (wake R17 #2).
git grep -nE 'Hook event 는 pre-insert.*identities=\[\]|service_terms 검사가 Hook 안에서는 불가능|wake R17 #2' docs/runbooks/supabase-branching.md
# → §7.1.8 HK-REG-3 정정 + H4 ㊹ 매칭. Kakao 검증 정본 위치가 §7.1.5 H3 파일 ⑦ trigger 임을 입증.

# 74) consume 시 term별 t.version 저장 (wake R17 #3).
git grep -nE 'JOIN public\.terms t ON t\.id = submitted\.id|t\.version 으로 INSERT|각 row 의 version 은 join 된 t\.version|wake R17 #3' docs/runbooks/supabase-branching.md
# → consume_pending_terms_consent_internal 본문 + H4 ㊺ 매칭. single row_terms_version 단일 값 사용 회귀 방지.

# 75) Kakao agreed tag mapping 검증 + insert (wake R17 #4).
git grep -nE 'public\.kakao_term_mapping|v_required_kakao_tags|v_agreed_kakao_tags|kakao required terms not fully agreed|wake R17 #4' docs/runbooks/supabase-branching.md
# → 파일 ⓪.5 + 파일 ⑦ trigger 본문 + H4 ㊻ 매칭. Kakao tag 가 agreed=true 인 row 만 mapping 결과로 insert 됨을 입증.
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

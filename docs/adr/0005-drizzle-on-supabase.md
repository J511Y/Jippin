# ADR 0005 — Supabase 기준 Drizzle ORM 적용 범위 결정

- **상태**: **Proposed (2026-06-02)** — 본 ADR 은 ADR-0004 (Supabase 전환) 가 Accepted 되기 전에도 Drizzle 도입 여부 결정에 대한 정본을 마련하기 위해 Proposed 상태로 발행한다. Accepted 전까지 어떤 구현 PR 도 본 결정을 근거로 들 수 없다.
- **제안자**: Architecture Lead (agent `8c65d6c0-b528-4226-a87e-b5f8b3aad654`)
- **승인 권자**: CTO (기술), Backend Lead (Application tier 경계), Frontend Lead (`apps/web` server-only 표면), Database Engineer (마이그레이션 SSOT), DevOps Lead (CI 영향)
- **인계 출처**: CMP-601 본문 (ORM 으로 Drizzle 고려)
- **관련 이슈**: **CMP-601** (본 ADR) · CMP-573 (ADR-0004 발의) · CMP-575 (Supabase SQL 마이그레이션 정본화 계획) · CMP-602 (stale Neon/Alembic 문구 정리)
- **상위 컨텍스트**: 본 ADR 의 모든 결정은 ADR-0004 (Neon → Supabase 전환, Proposed) 의 결과를 전제로 한다. ADR-0004 가 Rejected 되거나 큰 폭으로 재작성되면 본 ADR 도 재평가 대상이다.
- **강한 제약 (변경 금지 — CEO 브리프 §5 / ADR-0001 / ADR-0004 봉인 상속)**:
  - **FastAPI 가 Application tier 정본**. Python 도메인 로직 (AUTH / RULE / REPORT) 을 TypeScript ORM 으로 즉시 이식하지 않는다.
  - **DB 마이그레이션 source of truth 는 단일** 이어야 한다. ADR-0004 + CMP-575 결정에 따라 정본은 `supabase/migrations/*.sql`.
  - **시크릿 봉인**: `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`, `DATABASE_POOL_URL` 은 브라우저 번들 / 클라이언트 컴포넌트 / 클라이언트 측 환경변수 (`NEXT_PUBLIC_*`) 에 노출 금지.
  - **자체 비밀번호 / 비밀번호 해시 컬럼 영구 금지** (ADR-0001 / ADR-0003 보존). Drizzle schema mirror 가 만들어지더라도 password / hash / salt 컬럼을 정의하지 않는다.

---

## 0. 결정 요약 (TL;DR)

| 항목 | 본 ADR 결정 |
|---|---|
| **Drizzle 채택 여부 (현 시점, MVP)** | **A안 — 도입 보류 (defer)**. 본 ADR 이 Accepted 되어도 `drizzle-orm` / `drizzle-kit` / `@neondatabase/serverless` / `postgres` 패키지를 즉시 설치하지 않는다. |
| **허용되는 후속 도입 경로** | **B안 — 제한 도입**. ADR-0004 가 Accepted 되고 CMP-575 의 `supabase/migrations` 기반 CI 가 봉인된 뒤에야, 별도 자식 이슈가 `apps/web` server-only BFF (route handler / server action) 또는 신규 `packages/db` TypeScript 패키지에서 read/query helper 로 Drizzle PoC 를 제안할 수 있다. PoC 채택 여부는 §6 의 사전 조건이 모두 통과해야 한다. |
| **금지되는 도입 경로** | **C안 — Drizzle Kit 을 DB schema/migration 정본으로 전환**, **D안 — Application tier 를 TypeScript/Node 로 재평가하고 Drizzle 을 주 ORM 으로 채택**. 둘 다 별도 CTO ADR 없이 진행 금지. |
| **DB schema / migration source of truth** | **`supabase/migrations/*.sql` 단일 정본**. Alembic 은 CMP-575 cutover 가 끝나면 [`/docs/runbooks/supabase-migration-plan.md`](../runbooks/supabase-migration-plan.md) §"Alembic Keep/Remove Recommendation" 절차대로 forward authority 에서 retire. Drizzle Kit 의 migration 생성/적용 기능은 **사용 금지**. |
| **Drizzle schema 의 위치 (B안 채택 시)** | **`supabase/migrations` 의 종속 mirror**. Drizzle TS schema 는 DB DDL 의 정본이 아니라 type inference 보조 mirror. drift guard 가 없으면 PoC 단계에서 중단. |
| **`apps/api` (FastAPI + SQLAlchemy) 영향** | **변경 없음**. SQLAlchemy 모델은 `apps/api` Application tier 의 ORM 정본을 유지. Drizzle 도입은 TypeScript 측 (`apps/web` server-only / `packages/db`) 표면에만 한정. |
| **AUTH 모델 가드 보존** | `apps/api/tests/auth/test_no_password_columns.py` (`public` 스키마 password 컬럼 금지) 와 `terms_consents` UNIQUE/source 가드를 그대로 유지. Drizzle TS schema 도 password 컬럼을 정의할 수 없다 — B안 PoC 의 type test 가 가드. |
| **Supabase Auth / RLS / 서비스 키 경계** | Drizzle 도입 후에도 `auth.users` / `auth.identities` 에 우리가 직접 INSERT/UPDATE 하지 않는다 (ADR-0004 §2.5 rev8 봉인 상속). RLS 정책 평가는 PostgREST 가 아니라 우리 connection role 위에서 `SET LOCAL ROLE authenticated` + `request.jwt.claims` 패턴으로 운영. Drizzle 은 SQL 호출 layer 일 뿐, RLS 우회 경로가 아님. |
| **ADR-0001 / ADR-0003 / ADR-0004 충돌** | 없음. 본 ADR 은 ADR-0001 T2 (Application tier = FastAPI) 와 ADR-0001 T3 (Postgres) 의 결정을 **확정 유지** 하며, ADR-0004 의 Supabase / SQL migration SSOT / Supabase Auth 봉인을 그대로 상속한다. supersede 행 없음. |

> 본 ADR 은 “지금 Drizzle 을 쓰지 말라” 가 아니라 “**언제 / 어디까지 / 어떤 가드 위에서** 쓸 수 있는지” 를 정한다. A안은 영구 결정이 아니라 baseline 이고, B안 으로 이동하려면 §6 사전 조건 통과 + 자식 이슈 + 별도 PR 검토가 필요하다.

---

## 1. 결정 컨텍스트

### 1.1 무엇을 결정해야 하는가

사용자 요청: `ORM으로 drizzle을 고려하고 있어. 적용 계획을 작성하고 페이퍼클립에 인계해보자`.

CMP-601 본문은 다음 핵심 질문을 던진다.

> **Supabase Postgres + `supabase/migrations/*.sql` 마이그레이션 정본 위에서 Drizzle 을 어디에 적용할 것인가?**

본 ADR 은 다음 6가지를 명확히 한다.

1. Drizzle 을 도입할지 여부 (지금 / 영구).
2. 도입한다면 어느 계층에서 사용할지.
3. `supabase/migrations/*.sql` 과 Drizzle Kit migration 의 관계.
4. FastAPI Application tier 와 TypeScript query layer 의 책임 경계.
5. Supabase Auth / RLS / service role / anon key 보안 경계.
6. stale Neon/Alembic 문서 정리 필요 범위.

### 1.2 현재 정본 상태 (검증된 사실)

- ADR-0001 §2 / §3 — `apps/api = FastAPI 0.115 / Python / uv`, `apps/web = Next.js 16.2 LTS / React 19 / Node 22 / pnpm 9.x`.
- ADR-0001 T3 / ADR-0004 §2 — DB 는 **Supabase Postgres** (managed). ADR-0004 가 Proposed 이지만 `origin/dev` 의 코드/문서 산출물 (supabase config / migrations / 런북 / `apps/web/lib/supabase/*` / `apps/api/src/services/supabase_session.py` / `apps/api/src/auth/supabase_jwt.py`) 이 이미 Supabase 기준으로 정렬되어 있다.
- CMP-575 / `docs/runbooks/supabase-migration-plan.md` — DB schema source of truth 를 `supabase/migrations/*.sql` 로 두고, Alembic 을 forward authority 에서 retire 하는 cutover 계획이 봉인됨. Alembic CI 작업 (`.github/workflows/ci.yml` migrate-check / `neon-pr-branch.yml`) 은 Supabase migration apply 작업으로 교체 예정.
- `apps/api/src/db.py` — psycopg3 async engine. `database_pool_url` (request path) + `database_url` (migration / direct) 2종 분리.
- `apps/api/src/models/` — SQLAlchemy `DeclarativeBase` + mixin + AUTH skeleton. `tests/auth/test_no_password_columns.py` 가 `public` 스키마 password 컬럼 부재를 가드.
- `apps/web/lib/supabase/{client,server,proxy,providers,env}.ts` — `@supabase/ssr` 기반 SSR client / Route Handler client / proxy 핸들러. `apps/web` 은 **현재 직접 DB 접근 코드가 없다** — Supabase JS client 만 사용한다. 즉 “server-only DB query helper” 가 필요한 신호는 아직 존재하지 않는다.
- `packages/contracts` — JSON Schema 정본 + 생성된 TypeScript / Python 바인딩. API 계약 타입 SSOT 역할. **Drizzle 이 “TypeScript 타입 이득” 으로 주는 값의 상당 부분을 이미 packages/contracts 가 제공** 한다.
- `pnpm-workspace.yaml` 부재 — `apps/web` 과 `packages/contracts` 는 현재 모노레포 workspace 로 묶여 있지 않다. Drizzle 을 `packages/db` 로 분리하려면 workspace 셋업 변경이 선행되어야 한다 (별도 DevOps 이슈 후보).
- 검색 결과 (`rg -i drizzle`) — 현재 레포 전체에 Drizzle 참조 0건. 즉 “이미 도입된 Drizzle 을 어떻게 정리하느냐” 가 아니라 “신규 도입 여부” 만 결정하면 된다.

### 1.3 평가 기준

본 ADR 은 다음 7가지 질문에 모두 답할 수 있어야 도입을 허용한다. 하나라도 답이 없으면 도입을 보류한다.

1. **FastAPI 가 Application tier 정본으로 유지되는가?** — Yes 가 필수 (ADR-0001 T2).
2. **DB schema 변경의 단일 정본이 하나인가?** — Alembic 과 Drizzle Kit 이 동시에 migration 을 만들면 안 된다. 본 ADR 결정: SSOT = `supabase/migrations/*.sql`.
3. **Supabase GitHub integration / migration apply / branching workflow 가 유지/명시 대체되는가?** — CMP-574 / `docs/runbooks/supabase-branching.md` 가 정본. Drizzle 이 그 흐름에 끼어들지 않는다.
4. **`DATABASE_URL` (direct/migration) 과 `DATABASE_POOL_URL` (request path) 분리가 보존되는가?** — Yes. Drizzle 호출 시에도 동일 분리 적용 (B안 PoC 가드).
5. **Drizzle 을 쓰는 코드가 Node server runtime 에만 남고 browser bundle 에는 포함되지 않는가?** — B안 채택 시 lint + bundle check + env 분리로 강제. 위반 시 PoC 중단.
6. **AUTH 모델의 password 컬럼 금지, provider ENUM 정책, anonymous user claim 정책을 테스트로 계속 가드할 수 있는가?** — `apps/api/tests/auth/test_no_password_columns.py` 그대로 유지. B안 채택 시 Drizzle TS schema 측에도 type-level 가드 (password 컬럼 type 정의 금지) 추가.
7. **TypeScript 타입 이득이 실제로 현재 문제를 줄이는가?** — 현재 `apps/web` 에서 직접 DB 접근이 0건. `packages/contracts` 가 API 계약 타입을 이미 제공. 즉 **현 시점에는 줄여야 할 “DB type drift 문제” 자체가 발생하지 않은 상태**. 이것이 A안 (보류) 의 핵심 정당화.

---

## 2. 결정 (정책 봉인 — Proposed)

### 2.1 채택 안 (A안 baseline + B안 opt-in)

본 ADR 은 §1.3 의 평가 기준을 §0 표대로 처리한 결과, **A안 (도입 보류)** 을 baseline 으로 채택하고 **B안 (제한 도입)** 을 사전 조건부 opt-in 경로로 봉인한다. C안 / D안 은 별도 ADR 없이 금지한다.

| 안 | 본 ADR 처리 | 사전 조건 |
|---|---|---|
| **A안 — 미도입** | **채택 (baseline).** Drizzle 패키지를 설치하지 않는다. `apps/web` 은 Supabase JS client (`@supabase/supabase-js` + `@supabase/ssr`) 만 사용. `apps/api` 는 SQLAlchemy 만 사용. | 사전 조건 없음 — 즉시 적용. |
| **B안 — `apps/web` server-only 또는 `packages/db` 에 제한 도입** | **사전 조건부 허용.** 본 ADR 이 Accepted 된 뒤, §6 사전 조건이 모두 충족되었음을 후속 자식 이슈가 입증할 때만 PoC PR 발행. PoC 가 §6 가드 중 하나라도 깨면 즉시 중단. | §6 의 5종 모두. |
| **C안 — Drizzle Kit 을 migration 정본으로 전환** | **금지.** Supabase GitHub integration / `supabase/migrations` 정본 / Alembic retire 계획 전체를 supersede 해야 하므로, 새 CTO ADR + DevOps 재설계 (CI / branching / drift guard) 가 선행되어야 한다. | 신규 ADR + CTO 승인 + DevOps 재설계. |
| **D안 — Application tier 를 TypeScript/Node 로 재평가** | **금지.** ADR-0001 T2 를 supersede 해야 하므로 별도 대형 ADR 이 필요. 본 ADR 은 “Drizzle 을 주 ORM 으로 채택하기 위해 FastAPI 를 폐기” 라는 결정을 허용하지 않는다. | 신규 ADR + CTO 승인 + 도메인 로직 이식 영향 분석. |

### 2.2 정본 분리 (계층 책임 경계)

| 계층 | 정본 도구 | 정본 위치 | Drizzle 사용 여부 |
|---|---|---|---|
| **DB schema / DDL / migration** | `supabase/migrations/*.sql` (Supabase CLI / GitHub integration apply) | `supabase/migrations/` | **사용 안 함.** Drizzle Kit migration generate/apply 금지. |
| **`apps/api` ORM / 도메인 로직** | SQLAlchemy 2.x (psycopg3 async) | `apps/api/src/models/`, `apps/api/src/services/`, `apps/api/src/auth/` | **사용 안 함.** Drizzle 은 Python 측에서 호출할 수 없다 (정의상). |
| **`apps/api` request-path query (FastAPI)** | SQLAlchemy 2.x core / ORM | `apps/api/src/repos/` 또는 service layer | **사용 안 함.** |
| **`apps/web` SSR / Server Action / Route Handler 의 Supabase 접근** | Supabase JS client (`@supabase/supabase-js` v2 + `@supabase/ssr`) | `apps/web/lib/supabase/*.ts`, `apps/web/app/**/route.ts` | **현재 정본** — A안 baseline. B안 채택 시에도 PostgREST/RLS path 는 Supabase JS 가 정본. Drizzle 은 **PostgREST 우회 직접 SQL 경로** 에만 적용. |
| **`apps/web` server-only 직접 SQL (있을 경우)** | (현재 없음) | (예정: `apps/web/app/**/route.ts` 또는 신규 `packages/db`) | **B안 사전 조건 충족 시 Drizzle 허용**. 단 RLS 우회 + service role key 사용은 별도 가드 (§3.3). |
| **API 계약 타입 (web ↔ api)** | JSON Schema 정본 + 생성 TS/Py 바인딩 | `packages/contracts/schemas/`, `packages/contracts/ts/`, `packages/contracts/python/` | **사용 안 함** (Drizzle 은 DB schema mirror 이지 API 계약 SSOT 가 아님). |
| **Browser bundle / Client Component** | Supabase JS client (anon key) | `apps/web/lib/supabase/client.ts` 등 | **금지** — Drizzle 호출 / Drizzle import / DB URL 노출 전부 금지. |

> **packages/db 채택 보류.** B안 PoC 가 `packages/db` 형태로 떠야 한다고 결정된 것은 아니다. PoC 자식 이슈가 (a) `apps/web` 안의 server-only 디렉터리 (`apps/web/server/db/`) 로 갈 것인지, (b) 신규 `packages/db` TS 패키지로 분리할 것인지를 결정한다. 후자는 pnpm workspace 셋업 변경이 선행되어야 하므로 별도 DevOps 자식 이슈를 동반한다.

### 2.3 Drizzle TS schema 의 위치 (B안 채택 시)

B안 이 사후 채택되더라도, Drizzle TS schema 의 정합 규칙은 다음으로 봉인한다.

1. **`supabase/migrations/*.sql` 이 정본**. Drizzle schema 는 그 mirror.
2. **drift guard 필수**. PoC 자식 이슈는 다음 중 하나의 drift guard 를 함께 제출해야 한다:
   - (a) `supabase/migrations` → Drizzle schema 자동 생성 (예: `drizzle-kit introspect` 결과를 PR 단위로 commit 하고 CI 가 `git diff --exit-code` 로 drift 차단).
   - (b) 별도 lint/test 로 Drizzle schema 가 정의한 테이블/컬럼/제약이 `supabase/migrations` 의 정본 schema 와 1:1 일치하는지 검증.
   - 둘 다 없는 PoC PR 은 **본 ADR 위반** 으로 reject.
3. **Drizzle Kit migration 명령 (`drizzle-kit generate` / `drizzle-kit push`) 사용 금지**. PoC 가 우연히 그 명령을 호출해도 CI 가 차단할 수 있도록, B안 자식 이슈는 `package.json` script / pre-commit hook / lint rule 중 하나로 봉인한다.
4. **AUTH 스키마 (`auth.*`) 를 Drizzle schema 에 정의하지 않는다.** ADR-0004 §2.5 rev8 (Supabase auth 스키마 직접 INSERT 금지) 봉인 상속. mirror 대상은 `public` 스키마 한정.
5. **Password / hash / salt 컬럼 type 정의 금지**. `apps/api/tests/auth/test_no_password_columns.py` (Python 쪽 가드) 에 대응되는 TS-level 가드를 B안 자식 이슈가 추가.

### 2.4 Supabase Auth / RLS / 시크릿 경계

| 경계 | 본 ADR 봉인 |
|---|---|
| `auth.users` / `auth.identities` 직접 쓰기 | **금지** — ADR-0004 §2.5 rev8 상속. Drizzle 도입 후에도 마찬가지. Auth Admin SDK 또는 `linkIdentity()` SDK call 만 정합 경로. |
| RLS 정책 평가 경로 (FastAPI 측) | ADR-0004 §4.3 / rev8 (Codex P2 line 398) 봉인 그대로 — `app_backend` login role + `SET LOCAL ROLE authenticated` + `SET LOCAL "request.jwt.claims"`. Drizzle 도입과 무관. |
| RLS 정책 평가 경로 (`apps/web` 측) | **Supabase JS client 위에서 PostgREST 가 RLS 평가.** Drizzle 의 server-only 직접 SQL 경로는 PostgREST 를 거치지 않으므로 **RLS 평가가 자동으로 fire 하지 않는다**. B안 PoC 가 server-only 에서 user JWT 컨텍스트의 RLS 가 필요한 쿼리를 호출한다면 반드시 connection role 전환 + claims 주입 패턴을 적용. service role key 우회 사용 금지. |
| `SUPABASE_SERVICE_ROLE_KEY` 사용처 | **API-only**. 정본 위치는 `apps/api` 런타임 또는 운영 시크릿 매니저이며, `apps/web` 배포 환경 / `apps/web/lib/supabase/server.ts` / web server-only DB 모듈에도 두지 않는다. 기존 `docs/runbooks/supabase-web-auth.md` 의 "service role key 는 웹에 두지 않음" 봉인을 유지한다. Drizzle PoC 가 web server-only 직접 SQL 을 쓰더라도 service-role/admin credential 로 RLS 를 우회하지 않는다. |
| `DATABASE_URL` / `DATABASE_POOL_URL` 노출 | **server-only**. Drizzle 의 Node connection 도 동일. browser bundle 금지. `apps/web/next.config.*` 의 환경변수 노출 설정에서 prefix `NEXT_PUBLIC_` 를 절대 붙이지 않는다. |
| Connection pooler 선택 (Drizzle 도입 시) | **Supabase pooler (Supavisor) / port 6543 / transaction mode / prepared statement OFF** — ADR-0004 §2.3 rev9 봉인 상속. Drizzle 의 query helper 도 동일. direct 5432 는 마이그레이션 / DDL 전용. |

### 2.5 의존성 정책

본 ADR 이 Accepted 되어도 다음 패키지를 **즉시** 설치하지 않는다.

- `drizzle-orm`
- `drizzle-kit`
- `@neondatabase/serverless` — Neon 은 ADR-0004 에서 DB 호스팅 정본에서 제거. 명시적 의존 추가 금지.
- `postgres` (drizzle 의 `node-postgres` 또는 `postgres.js` driver 계열)

설치는 **B안 PoC 자식 이슈의 PR 안에서만** 일어난다. 본 ADR 의 다른 후속 작업 (예: ADR-0004 수렴, stale 문서 정리 CMP-602) 은 위 패키지 의존을 추가하지 않는다.

---

## 3. 대안 분석

### 3.1 A안 — Drizzle 미도입 (채택, baseline)

**채택 이유.**

1. **현재 `apps/web` 에서 직접 DB 접근이 0건.** Drizzle 이 줄여줄 “TypeScript ↔ DB drift” 문제 자체가 존재하지 않는다 (§1.2 / §1.3 #7).
2. **`packages/contracts` 가 API 계약 타입 SSOT 를 이미 담당.** web ↔ api 사이의 typed boundary 는 이미 보호되어 있다.
3. **Supabase 전환 자체가 미완** (ADR-0004 Proposed, CMP-575 cutover 미집행, CMP-602 stale 문서 정리 진행 중). 새 ORM 의존을 더하면 검토 표면이 누적된다.
4. **신규 의존 (`drizzle-orm`, `drizzle-kit`, driver) 의 운영·보안 표면 0**. 추가하지 않는 것이 가장 보수적인 default.

**기각하지 않는 이유.** A안 은 baseline 일 뿐, 영구 “Drizzle 영구 금지” 가 아니다. §6 사전 조건이 충족되면 B안 으로 전진할 수 있다.

### 3.2 B안 — `apps/web` server-only / 신규 `packages/db` 에 제한 도입 (사전 조건부 opt-in)

**미래 채택 후보 이유.**

- ADR-0004 cutover 후 `apps/web` 에서 SSR 시 server-only Postgres 직접 쿼리가 정당화되는 표면 (예: 관리자 list 쿼리, 통계 집계 BFF, Supabase JS 의 PostgREST 가 표현하기 어려운 복합 join 쿼리) 이 생길 수 있다.
- Drizzle 의 TypeScript inference + SQL builder 는 그 시점에 SQL 문자열 보다 안전한 path 가 된다.

**현 시점에 즉시 채택하지 않는 이유.**

1. 그 “server-only 직접 쿼리” 표면이 아직 존재하지 않는다 (§1.2).
2. drift guard / browser bundle leak guard / RLS context guard 가 모두 아직 설계 안 됨 — §6 에 봉인된 사전 조건이 모두 후속 작업이다.
3. PoC 단계에서 Drizzle schema 가 `supabase/migrations` 와 drift 하면 사용자가 정본을 혼동할 수 있다. drift guard 가 먼저 들어와야 한다.

### 3.3 C안 — Drizzle Kit 을 DB schema / migration 정본으로 전환 (금지)

**기각 사유.**

1. **`supabase/migrations/*.sql` SSOT (ADR-0004 + CMP-575) 와 정면 충돌.** Supabase GitHub integration 이 SQL 파일을 read 하므로, Drizzle Kit 이 schema authority 가 되려면 GitHub integration 흐름을 갈아엎고 Drizzle Kit 의 SQL 출력을 `supabase/migrations` 에 commit 하는 형태로 다시 설계해야 한다. 그 경로의 운영 사고 표면 (drift, partial apply, branching 호환성) 이 본 ADR 범위를 초과한다.
2. **Alembic retire cutover (CMP-575) 와 동시에 두 번째 migration authority 교체를 던지면** schema source of truth 가 일시적으로 3중 (Alembic / supabase SQL / Drizzle Kit) 으로 분기. 이 상태에서 incident 가 나면 복구 불가.
3. **FastAPI / SQLAlchemy 모델 메타데이터 테스트가 Drizzle Kit 산출 SQL 의 결과를 검증해야 함.** 그 호환 layer 가 또 추가된다.

→ **별도 ADR 발행 + CTO 승인 + DevOps 재설계 없이 진행 금지**.

### 3.4 D안 — Application tier 를 TypeScript/Node 로 재평가 (금지)

**기각 사유.**

1. **ADR-0001 T2 (Application tier = FastAPI) 를 supersede 해야** 한다. 본 ADR 의 권한 범위 밖.
2. `apps/api/src/{auth,services,rules,reports}` 의 Python 도메인 로직 이식이 곧 Drizzle 채택의 사전 조건이 됨. MVP 일정과 양립 불가.
3. Supabase Auth + FastAPI 검증 path (`apps/api/src/auth/supabase_jwt.py`) 가 Python 측에서 봉인되어 있어, Node 측에서 동일 정합을 재구현해야 함.

→ **별도 대형 ADR + CTO 결정 없이 진행 금지**. 본 ADR 은 D안 평가 자체를 본 이슈 범위에서 종결한다 (CMP-601 비범위 봉인).

---

## 4. CI / 마이그레이션 영향

### 4.1 CI workflow 영향 (A안 baseline)

본 ADR 이 Accepted 되어도 CI workflow 는 **변경 없음**. ADR-0004 / CMP-575 가 `.github/workflows/ci.yml` 의 Alembic migrate-check 단계를 Supabase migration apply 단계로 교체하는 cutover 를 담당. 본 ADR 은 그 흐름에 끼어들지 않는다.

### 4.2 CI workflow 영향 (B안 사전 도입 시)

B안 PoC 자식 이슈는 다음을 함께 land 해야 한다.

1. **drift guard CI step** (§2.3 #2) — `supabase/migrations` → Drizzle schema 자동 동기 또는 1:1 검증 잡.
2. **browser bundle leak guard** — `apps/web` 의 Next.js build 산출물 (`.next/static`) 에 `drizzle-orm` / driver / DB URL 이 포함되지 않음을 검증. 가능한 방식:
   - `next build` 후 `.next` 산출물을 스캔해 금지 심볼/문자열 부재 검증.
   - 또는 server-only 모듈을 명시적으로 분리 (`"use server"` 또는 server-only path) 하고 lint 로 client component 의 import 차단.
3. **type-level password column 가드** — `apps/api/tests/auth/test_no_password_columns.py` 의 TS 대응.

### 4.3 마이그레이션 흐름

- 정본: `supabase/migrations/*.sql` (Supabase CLI / GitHub integration).
- Alembic retire: CMP-575 cutover 완료 시점에 `apps/api/migrations/` 를 historical reference 로 격하 → 별도 cleanup 이슈가 forward 작업 (새 revision 생성) 금지를 봉인.
- Drizzle Kit: **never used as authority**. B안 PoC 가 Drizzle schema 를 commit 해도 그 schema 는 정본이 아니다.

---

## 5. 보안 영향

| 항목 | 본 ADR 영향 |
|---|---|
| Service role key 노출 | A안 baseline 에서는 추가 표면 없음. B안 도입 시 server-only 경로 + bundle leak guard + lint 로 봉인 (§4.2). |
| `DATABASE_URL` / `DATABASE_POOL_URL` 노출 | 동일. browser bundle 금지. |
| `auth.users` / `auth.identities` 직접 INSERT/UPDATE | ADR-0004 §2.5 rev8 봉인 상속. Drizzle 이 SDK 우회 경로를 제공하지만 본 ADR 은 그 경로를 명시적으로 금지. |
| RLS 평가 우회 | Drizzle 직접 SQL 경로는 PostgREST 를 거치지 않으므로 자동 RLS 평가 fire 안 함. B안 PoC 는 connection role 전환 + claims 주입 (§2.4 / ADR-0004 §4.3) 을 강제. |
| Password 컬럼 영구 금지 | `apps/api/tests/auth/test_no_password_columns.py` 유지 + B안 PoC 의 TS-level 가드 추가 (§2.3 #5). |
| Anonymous user claim 정책 | ADR-0004 §2.3 / `is_anonymous` 분리 봉인 상속. Drizzle 이 `auth.users.is_anonymous` 를 직접 update 하지 않는다 (애초에 `auth.*` 직접 쓰기 금지). |

---

## 6. B안 사전 조건 (Drizzle 제한 도입 자식 이슈가 land 하기 위한 게이트)

본 ADR 이 Accepted 된 뒤, 다음 5종이 모두 통과해야 B안 PoC 자식 이슈가 PR 을 제출할 수 있다.

1. **ADR-0004 Accepted** — Supabase 전환 봉인이 Proposed 가 아니라 Accepted 로 확정.
2. **CMP-575 cutover 완료** — `supabase/migrations/*.sql` 이 실제 Supabase 프로젝트에 apply 되고 Alembic 이 forward authority 에서 retire. CI / deploy workflow 가 Supabase apply 로 교체.
3. **CMP-602 (또는 후속 정리 이슈) 완료** — `AGENTS.md` / `apps/api/README.md` / workflow / compose 의 stale Neon/Alembic 문구가 Supabase 기준으로 정리. 정본 문서가 일관성을 회복.
4. **`apps/web` 안에서 “server-only 직접 DB 쿼리가 필요한 표면” 이 명시적으로 식별됨** — 막연한 “미래 가능성” 이 아니라 구체적 use case (예: 관리자 list, BFF 집계) 가 자식 이슈 본문에 명시되고 그 use case 가 Supabase JS PostgREST 만으로 표현 불가능한 이유 (성능 / 복합 join / RLS 미적용 admin path) 가 입증.
5. **drift / bundle / RLS / secret 가드 4종이 PoC 자식 이슈 본문에 설계 포함** — §2.3 / §4.2 / §5 의 가드가 PoC 의 정의 안에 포함. 가드 없이 “일단 Drizzle 깔고 보자” 형태의 PR 은 본 ADR 위반.

5종 중 하나라도 미충족이면 PoC 자식 이슈 자체를 발행하지 않는다.

---

## 7. 후속 이슈 (proposal)

본 ADR 은 **즉시 코드 의존성을 추가하지 않으므로**, 후속 자식 이슈는 모두 “필요 시” 발행한다. 현 시점 강제 발행 의무가 있는 자식 이슈는 없다.

| 후속 이슈 후보 | 발행 트리거 | 비고 |
|---|---|---|
| `[WEB][DB] server-only Drizzle PoC` | §6 사전 조건 5종 모두 충족 + Architecture Lead 가 명시 발행 결정 | 본 ADR §2 / §6 / §4.2 가드 일체 포함. PoC 가 가드 위반 시 즉시 중단. |
| `[ARCH][ADR] Drizzle Kit 을 migration authority 로 채택` | C안 검토가 다시 필요해진 시점 (예: Supabase GitHub integration 폐기 등) | 별도 ADR 발행. 본 이슈 단독 처리 금지. |
| `[ARCH][ADR] Application tier TypeScript 재평가` | D안 검토가 필요해진 시점 | 별도 대형 ADR. |
| `[INFRA] pnpm workspace 셋업` (B안 PoC 가 `packages/db` 방향일 경우) | B안 PoC 자식 이슈가 `packages/db` 분리를 선택할 때 | `apps/web` + `packages/contracts` + `packages/db` 를 workspace 로 묶는 작업 선행. |
| stale Neon/Alembic 문구 정리 | **CMP-602 가 이미 존재** — 본 ADR 은 새 자식 이슈를 발행하지 않고 CMP-602 에 정리 범위 위임. | 본 ADR 의 결정 (Drizzle SSOT 표 / Alembic retire 보강) 이 CMP-602 의 cleanup 범위에 추가될 수 있음. |

---

## 8. 검증

본 ADR 은 문서/정책 결정이므로 코드 변경이 없다. 다음 검증을 수행했다.

- `git status --short --branch` — worktree clean (ADR 파일만 신규 추가).
- `git grep -i drizzle` (origin/dev) — 0건. 즉 본 ADR 이 결정하는 “신규 도입 여부” 외 기존 사용 사례 없음.
- `git ls-tree -r --name-only origin/dev -- supabase docs/adr docs/runbooks` — `supabase/migrations/*.sql` 6 종, ADR 0001–0004, Supabase 런북 5 종 존재 확인.
- 시크릿 헌팅: `rg -n "npg_|sk-|AKIA|SUPABASE_SERVICE_ROLE_KEY=.*[^<]|postgresql://.*@" . --glob '!apps/web/node_modules/**' --glob '!apps/web/.next/**'` — 본 ADR 파일 안에 실제 시크릿 값 0건.

---

## 9. 수용 기준 매핑 (CMP-601)

| CMP-601 수용 기준 | 본 ADR 처리 |
|---|---|
| Drizzle 검토가 Supabase 기준으로 작성된다. | §1.2 / §2.2 / §4 / §5 가 ADR-0004 와 `supabase/migrations` 봉인 위에서 작성됨. |
| Neon/Alembic 을 현재 정본으로 전제하지 않는다. | §1.2 / §2.2 가 Supabase 정본을 명시. Alembic 은 retire 대상으로 처리. |
| `supabase/migrations/*.sql` 과 Drizzle Kit migration 의 관계가 명확하다. | §2.3 / §2.5 / §3.3 — Drizzle Kit 사용 금지, schema mirror 만 (B안 채택 시). |
| Supabase Auth / RLS / secret boundary 를 침범하지 않는다. | §2.4 / §5. |
| stale 문서 정리 필요 범위가 별도 후속 이슈로 제안된다. | §7 — CMP-602 에 위임. |
| 실제 시크릿이 포함되지 않는다. | §8 의 secret hunt 결과 0건. |
| 작업은 `origin/dev` 기반 별도 worktree 에서 수행한다. | `docs/cmp-601-drizzle-on-supabase` 브랜치 + `C:/Users/jhyou/2026/jippin-worktrees/CMP-601-drizzle-on-supabase/` worktree 에서 작성. |

---

## 10. 참고

- ADR-0001 — Stack reevaluation (Application tier = FastAPI, Postgres SSOT)
- ADR-0003 — Anonymous user + SSO
- ADR-0004 — Neon → Supabase 전환 (Proposed)
- `docs/runbooks/supabase-migration-plan.md` — CMP-575
- `docs/runbooks/supabase-branching.md` — CMP-574
- `docs/runbooks/supabase-web-auth.md`
- Drizzle ORM overview: <https://orm.drizzle.team/docs/overview>
- Drizzle migrations: <https://orm.drizzle.team/docs/migrations>
- Supabase + Drizzle guide: <https://supabase.com/docs/guides/database/drizzle>

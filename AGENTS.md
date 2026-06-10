# AGENTS.md — Jippin(집핀) 에이전트 작업 가이드

이 문서는 본 모노레포에서 일하는 **Paperclip 에이전트(자율형)** 와 **사람 개발자** 모두를 대상으로 한다. 한 줄 요약: *집핀은 비내력벽 철거 사전검토 AI 서비스이며, 이 레포는 단일 인스턴스 docker-compose 모노레포다. 모든 결정은 `docs/명세서/`(요구·기능·기술·SDD)와 `docs/brief/CEO_PROJECT_BRIEF.md` 에 우선 따른다.*

> **⚠ DB / Auth SSOT — Supabase (CI/CD cutover 완료, CMP-603 / 2026-06-02 기준)**
>
> 본 레포의 DB / Auth 정본은 **Supabase Postgres + Supabase Auth** 다. 정책 정본은 [`docs/adr/0004-supabase-transition.md`](docs/adr/0004-supabase-transition.md) (CMP-603 시점 Proposed — CI/CD 측 cutover 는 본 PR 로 완료, ADR Accepted 는 CEO 결정 대기). 운영 정본은 [`docs/runbooks/supabase-branching.md`](docs/runbooks/supabase-branching.md) · [`docs/runbooks/supabase-migration-plan.md`](docs/runbooks/supabase-migration-plan.md) · [`docs/runbooks/supabase-auth-poc.md`](docs/runbooks/supabase-auth-poc.md) · [`docs/runbooks/supabase-web-auth.md`](docs/runbooks/supabase-web-auth.md) · [`docs/runbooks/supabase-session-bridge.md`](docs/runbooks/supabase-session-bridge.md) 다.
>
> Forward DB schema SSOT 는 **`supabase/migrations/*.sql`** 이며, **Supabase GitHub Integration** 이 `dev` push → development branch / `main` push → production branch 로 migration 을 적용한다. Alembic (`apps/api/migrations/`) 은 historical reference 로만 잔존한다 (forward authority 아님). 콘솔에서 remote schema 를 직접 수정하지 말 것 — repo migration 파일과 어긋나 `supabase db push` sync error 가 난다. 직접 수정한 경우 `supabase db pull` / `supabase migration repair` 절차가 필요하다 (정본: docs/runbooks/supabase-migration-plan.md).
>
> CI/CD 책임 분기 (CMP-603):
> - `.github/workflows/ci.yml::migrate-check` = Supabase SQL migration drift 가드 (model-only PR 차단). Neon / Alembic 의존 없음.
> - `.github/workflows/deploy.yml` = 어플리케이션 빌드 + 배포 스텁만. DB migration 미실행 (Supabase Integration 단독).
> - `.github/workflows/supabase-status.yml` = path-filter deadlock 회피용 wrapper. `supabase/**` 변경 없는 PR 은 자체 succeed, 변경 있는 PR 은 실제 Supabase integration check 결과를 polling.
> - `.github/workflows/_archive/neon-pr-branch.yml.archived` = 비활성. 이력 참조용.
>
> Neon 런북([`docs/runbooks/neon-branches.md`](docs/runbooks/neon-branches.md) · [`docs/runbooks/neon-credential-rotation.md`](docs/runbooks/neon-credential-rotation.md)) 은 archive 배너가 붙어 있으며 Neon project 자체는 폐기 대상이다 (사용자 콘솔 작업). Neon 시크릿/변수 (`NEON_API_KEY`, `NEON_PROJECT_ID`, `NEON_TEST_DATABASE_URL`, `NEON_DEV_DATABASE_URL`, `NEON_PROD_DATABASE_URL`, `NEON_DEV_PARENT_BRANCH`, `NEON_BRANCH_CAP`) 는 본 PR 머지 후 GitHub Settings 에서 일괄 삭제 대상이다.

---

## 1. 우선순위 — 무엇을 먼저 읽어야 하는가

자동화 에이전트가 어떤 이슈를 받든, 작업 시작 전에 아래 순서로 정합성을 맞춘다.

1. **이슈 본문** (`PAPERCLIP_WAKE_PAYLOAD_JSON.issue.description`)
2. **`docs/brief/CEO_PROJECT_BRIEF.md`** — 범위·인도물·금지사항
3. **`docs/명세서/` 4종 정본** — 요구사항(v0.2) / 기능명세(v1.0) / 기술명세(v1.6) / SDD(v1.9)
4. **`docs/_extracted/`** — 위 정본에서 추출한 텍스트 캐시 (Word/Excel 미설치 환경용)
5. **디자인·문구·리포트 관련 이슈는 [`docs/design/DESIGN.md`](docs/design/DESIGN.md) 진입점 + 하위 정본** ([`BRAND.md`](docs/design/BRAND.md) · [`COLOR_SYSTEM.md`](docs/design/COLOR_SYSTEM.md) · [`TYPOGRAPHY.md`](docs/design/TYPOGRAPHY.md)) — UI·컬러·폰트·문체·결과 화면·다운로드 산출물 작업 전 반드시 통독.
6. 해당 모듈의 `README.md` 와 코드 정본

기능명세서·SDD·기술명세서 간 모순이 있으면 **(이슈 본문) > (CEO 브리프) > (SDD) > (기술명세서) > (기능명세서) > (요구사항)** 순으로 정본을 따르되, 모순 자체를 PR 또는 후속 이슈로 보고한다. 디자인·문구·시각 관련 모순은 **(이슈 본문) > (CEO 브리프) > (`docs/design/DESIGN.md`) > (`BRAND.md`) > (`COLOR_SYSTEM.md` / `TYPOGRAPHY.md`) > 코드의 임시 토큰** 순으로 정본을 따른다.

---

## 2. 모노레포 구조 (목표 상태 — CTO 분해로 확정)

```
jippin/
├── apps/
│   ├── web/           # Presentation (Next.js or 대안 — CTO ADR 결과)
│   └── api/           # Application (FastAPI or 대안 — CTO ADR 결과)
├── packages/
│   ├── contracts/     # CommonJudgmentSchema, CompletionDecision, RuleEvalResult, EstimateResult (언어 중립 JSON 스키마 + 생성된 TS/Python 타입)
│   └── eslint-config/ # (선택)
├── infra/
│   ├── docker/        # Dockerfile.web / Dockerfile.api / nginx.conf
│   └── compose/       # docker-compose.yml + override 파일
├── docs/
│   ├── 명세서/        # 정본 4종 + 참고 이미지
│   ├── _extracted/    # 위 정본의 텍스트 캐시 (read-only)
│   ├── brief/         # CEO 브리프
│   ├── adr/           # CTO 아키텍처 결정 기록
│   └── runbooks/      # 운영 런북 (후속)
└── tooling/           # extract_specs.py 등 1회성 스크립트
```

> 본 이슈(CMP-523) 종료 시점에는 위 트리의 골격만 존재한다. 모듈별 실제 코드는 후속 이슈에서 채워진다.
>
> **봉인 ADR**: 본 트리·패키지 매니저·런타임은 [`docs/adr/0001-stack-reevaluation.md`](docs/adr/0001-stack-reevaluation.md) 가 봉인한다. 변경은 새 ADR을 발행해 supersede 해야 한다. 핵심 결정:
> - `apps/web` = **Next.js 16.2 LTS** · React 19 · Node 22 LTS · **pnpm 9.x**
> - `apps/api` = **FastAPI 0.115** · Python 3.13 · **uv 0.5+**
> - DB = **Supabase Postgres** (외부 managed, 로컬 DB 컨테이너 없음). ADR-0004 cutover 완료 (CMP-603). 운영 DB URL 은 Supabase project 가 발급한 connection string. Forward migration SSOT 는 `supabase/migrations/*.sql` + Supabase GitHub Integration. Alembic 은 historical reference 만. 캐시 = **Redis 7.4-alpine** 컨테이너.
> - 객체 스토리지 = **Cloudflare R2** (S3 호환, zero-egress).
> - LLM 오케스트레이션 = **LangChain v0.3+**. VLM 기본 = OpenAI `gpt-4.1-mini` / 정밀 = `gpt-4o`.
> - 클라우드 MVP = **분리형 토폴로지 (제안 중)**: web=**Vercel** · api=**Fly.io 도쿄(`nrt`)** · redis=**Upstash 도쿄** · postgres=Supabase · 도면 추론=**Hugging Face Endpoint**. [`ADR-0006`](docs/adr/0006-deployment-split-topology.md) (Proposed) 가 [`ADR-0002`](docs/adr/0002-deployment-cloud.md) (단일 VM Lightsail Seoul) 를 supersede. 실행: [`docs/runbooks/fly-api-deploy.md`](docs/runbooks/fly-api-deploy.md). **로컬 개발은 `infra/compose/docker-compose.yml` 3-컨테이너 그대로** (production 토폴로지만 분리).

---

## 3. 모듈 ↔ 담당 에이전트 매핑

SDD §3·§4의 8개 논리 모듈 + FLOW_GUARD를 다음 라인에 배정한다. (라인 = Paperclip 디렉터/엔지니어)

| 모듈 | 책임 1줄 | 주 담당 라인 | 부 담당 |
|---|---|---|---|
| AUTH | 소셜 OAuth + JWT | Backend Lead → Python Backend Engineer | Security Engineer |
| INPUT | 주소·도면 수신·검증·OCR | Backend Lead → Python Backend Engineer | Frontend Lead (업로드 UI) |
| MASK | 도면 수치 마스킹 | Backend Lead → Python Backend Engineer | Data Lead (OCR 모델) |
| AI | Mask2Former + VLM + 스키마 정규화 | **Data Lead → AI/ML Engineer** | Backend Lead |
| OVERLAY | 도면 위 인터랙티브 선택 | **Frontend Lead → React Engineer** | — |
| CHAT | A2UI 세션 오케스트레이션 | Frontend Lead + Backend Lead (양측 책임) | — |
| FLOW_GUARD | 충분성/충돌/고위험 판단 | **AI Engineer** (별도 LLM 에이전트 옵션) | Architecture Lead (계약 가드) |
| RULE | 국토부 고시 룰 엔진 | Python Backend Engineer | Architecture Lead |
| REPORT | 리포트 + 견적 + 리드 | Python Backend Engineer + React Engineer | — |

라인 외 횡단 책임:
- **Architecture Lead** — 모듈 간 공통 컨트랙트 (공통 판단 스키마, CompletionDecision, RuleEvalResult, EstimateResult) 일관성 가드
- **Infrastructure Lead / Cloud Engineer** — 단일 인스턴스 운영 모델, 클라우드 비용 비교
- **DevOps Engineer** — CI, gitmoji 검증, GitHub Flow 정책 자동화
- **Security Lead / Security Engineer** — 시크릿 헌팅, OAuth/PII/암호화 정책 가드
- **QA Lead / Test Engineer** — 테스트 피라미드, 룰 결정성 회귀 테스트
- **Database Engineer** — DB 스키마·마이그레이션·인덱스. Forward migration SSOT 는 `supabase/migrations/*.sql` (CMP-603 cutover 완료). Alembic 은 historical reference. 운영 절차는 [`docs/runbooks/supabase-migration-plan.md`](docs/runbooks/supabase-migration-plan.md) · [`docs/runbooks/supabase-branching.md`](docs/runbooks/supabase-branching.md).

---

## 4. 글로벌 규칙

### 4.1 커밋 메시지 — gitmoji

다음 prefix만 허용한다.

| 이모지 | prefix | 용도 |
|---|---|---|
| ✨ | `feat:` | 새 기능 |
| 🐛 | `fix:` | 버그 수정 |
| 📝 | `docs:` | 문서 |
| ♻️ | `refactor:` | 동작 변화 없는 리팩터 |
| ✅ | `test:` | 테스트 추가/수정 |
| 🔧 | `chore:` | 빌드·설정·도구 |
| 🚀 | `perf:` | 성능 개선 |
| 🔒 | `security:` | 보안 패치 |
| 🚧 | `wip:` | 임시 (PR 머지 전 squash) |

예: `✨ feat(auth): kakao oauth callback`

### 4.2 브랜치 전략 — `main ← dev ← feature/*`

- `main` 보호. **직접 푸시 금지.** 운영 트래픽이 가리키는 단일 정본.
- `dev` 보호. `dev` 가 통합 브랜치(integration branch)이며 모든 작업 브랜치의 기본 PR base 다.
- 작업 브랜치는 `dev` 에서 분기한다. 명명: `<type>/<scope>-<short>` (예: `feat/auth-kakao-callback`, `docs/cmp-557a-auth-policy`, `fix/auth-jwt-leak`, `refactor/api-audit-mixin`).
- 흐름: `main` ← (release PR) ← `dev` ← (작업 PR) ← `feature/* | fix/* | docs/* | refactor/* | chore/* | perf/* | test/* | security/*`.
- **PR base 기본값 = `dev`.** `main` 으로의 PR 은 운영 release 컷 또는 핫픽스에 한정하며 CTO/DevOps 승인 필요.
- PR 본문·제목에는 관련 Paperclip 이슈 식별자(`CMP-###`)와 영향 모듈을 표기한다. **보드 이슈 없이 사람과의 직접 대화로 수행한 작업은 `CMP-DIRECT`** 를 식별자로 쓴다 (pr-title-lint 가 허용).
- 머지 방식: **Squash and merge** (gitmoji prefix 유지).
- `dev` → `main` 승급 자동화는 `.github/workflows/` 의 release 워크플로우(CMP-539 가드 적용)에 따른다.

### 4.3 PR 체크리스트

- [ ] 관련 이슈 식별자 명시 (보드 이슈 없는 직접 대화 작업은 `CMP-DIRECT`)
- [ ] 영향 모듈 명시 (`AUTH` / `INPUT` / …)
- [ ] 공통 컨트랙트(`packages/contracts/`) 변경 시 schema_version bump
- [ ] 비밀번호·키·도면 등 민감 자료 미포함
- [ ] `docker compose up` 또는 모듈별 dev 명령 정상 동작
- [ ] (해당 시) README 갱신

### 4.4 시크릿 & 환경변수

- 실제 값은 `.env` 로컬 또는 운영 시크릿 매니저. 커밋 금지.
- `.env.example` 만 커밋. 변수명·예시값 형식·설명 포함.
- **DB URL 관리**: `DATABASE_URL` (non-pooler, 마이그레이션·DDL), `DATABASE_POOL_URL` (pooler, 일반 쿼리). `sslmode=require` 는 모든 URL 에 필수. 두 URL 의 호스트는 **Supabase project 의 direct port 5432 / pooler port 6543** 을 가리킨다. Neon URL 은 cutover 완료 (CMP-603) 시점에 forward authority 가 아니다 — Neon project 잔존 동안에는 archive 런북 ([`docs/runbooks/neon-branches.md`](docs/runbooks/neon-branches.md)) 참조 가능하지만 신규 워크플로우/secret 추가 금지.
- **Supabase Auth 환경변수**: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_FLOW_COOKIE_SECRET`, `SUPABASE_JWT_SECRET`, `SUPABASE_JWT_AUDIENCE`, (ADR-0004 §2.3 rev9 신설) `SUPABASE_JWKS_URL`. 정본 정의는 `apps/api/.env.example` / `apps/web/.env.example`.
- **APP_ENV ↔ DB 브랜치 매핑은 봉인** (CMP-538 / CMP-574). 코드 분기 금지 — 매핑은 환경별 `.env` 의 URL 값으로만 한다 (12-factor). `apps/api/src/config.py::ALLOWED_APP_ENVS` 가 그 외 값을 부팅 단계에서 차단한다. 변경하려면 ADR 을 새로 발행한다.

  | APP_ENV       | Supabase 브랜치           | GitHub branch                  | 수명           | 비고                                                |
  |---------------|---------------------------|--------------------------------|----------------|-----------------------------------------------------|
  | `development` | `development`             | `dev`                          | 장기, 공유     | `dev` push → Supabase Integration 이 development 적용 |
  | `test`        | preview/pr-N (ephemeral)  | feature/fix/* (PR base=`dev`)  | 단기           | Automatic Branching, `supabase/**` 변경 PR 한정     |
  | `staging`     | `staging`                 | (없음 — Supabase-only)         | 장기           | QA / 사전검증 — Supabase 콘솔에서 수동 promote      |
  | `production`  | `production`              | `main`                         | 장기           | `main` push → Supabase Integration 이 production 적용 |

  Supabase 운영 절차 (정본): [`docs/runbooks/supabase-branching.md`](docs/runbooks/supabase-branching.md). hotfix/fix/security PR (base=`main`) 의 preview branch parent 는 `production` 이다 (드물게만 사용). Neon archive 런북 ([`docs/runbooks/neon-branches.md`](docs/runbooks/neon-branches.md) · [`docs/runbooks/neon-credential-rotation.md`](docs/runbooks/neon-credential-rotation.md)) 은 이력 참조용만 — 신규 작업 base 로 쓰지 말 것.

### 4.5 에러·응답 표준

모든 백엔드 모듈은 다음 응답 포맷을 따른다.

```json
{ "error": { "code": "INSUFFICIENT_DATA", "message": "...", "request_id": "...", "timestamp": "..." } }
```

- 비즈니스 예외는 `ZippinException` 계열 도메인 예외로 raise → 공통 예외 핸들러가 변환.
- AI 단계는 SDD §8.2에 정의된 코드(`SEGMENTATION_FAILED` / `VLM_TIMEOUT` / `ANALYSIS_LOW_CONFIDENCE` 등) 사용.
- 로그는 structlog 기반 JSON, `request_id` 컨텍스트 주입.

### 4.6 법적 고지 — 절대 누락 금지

모든 리포트 화면·다운로드 산출물(웹/PDF/DOCX/공유링크 OG)은 다음 문구를 포함한다.

> 본 서비스는 AI 기반 사전 검토 시스템입니다. 최종 행위허가 여부는 관할 행정기관 판단에 따라 달라질 수 있습니다.

이 문구의 시각·문체 규칙은 [`docs/design/BRAND.md §6`](docs/design/BRAND.md) 과 [`docs/design/COLOR_SYSTEM.md §5`](docs/design/COLOR_SYSTEM.md) 가 정본이다. 디자인 단독으로 문구를 줄이거나 다듬지 않는다. 문구 자체 변경이 필요하면 CEO·Security Lead 가 함께 검토하는 별도 이슈를 연다.

### 4.7 사용자 식별 정책 — 비회원 사전검토 + 전환 시점 OAuth 간편가입

> **봉인.** 본 절은 CEO 정책 (CMP-557) 결정. 정본은 `docs/adr/0003-anon-user-and-sso.md`. 기존 명세 4종 (요구·기능·기술·SDD) 중 “소셜 OAuth 로그인 필수 / 비회원 사전검토 불가” 가정은 본 절로 **supersede** 된다. 모순 추적: `docs/명세서-모순.md`.
>
> **Supabase Auth cutover 완료 (CMP-603/CMP-604)**: ADR-0003 §2.1·§2.2 의 `anonymous_users`, `external_sso_accounts`, 자체 `/auth/{provider}/start` · `/auth/callback/{provider}` 라우트, 자체 OAuth state store 는 forward 정본이 아니다. Supabase Auth (`auth.users`, `auth.identities`, Anonymous Sign-In, `linkIdentity()`) 가 인증 정본이다. 봉인된 항목 (자동 병합 금지 #9, 자체 비밀번호 금지 #3, 약관 분리 저장 #5·#6, OAuth provider 정책 #4) 은 보존한다. 운영 라우트·세션 정본은 [`docs/runbooks/supabase-auth-poc.md`](docs/runbooks/supabase-auth-poc.md) · [`docs/runbooks/supabase-web-auth.md`](docs/runbooks/supabase-web-auth.md) · [`docs/runbooks/supabase-session-bridge.md`](docs/runbooks/supabase-session-bridge.md).

**원칙.**

1. **비회원 사전검토 허용.** 도면 업로드·마스킹·1차 AI 판단·리포트 미리보기까지는 익명 세션으로 진행 가능하다. 로그인 게이트로 사전검토 흐름을 끊지 않는다.
2. **전환 시점 OAuth 간편가입 의무.** 다음 전환 지점에서만 OAuth 로그인을 강제한다.
   - (a) **상담 전환** — 사업자 연결·견적·연락 요청 시점.
   - (b) **리드 생성** — 사업자 측 리드 풀에 사용자 식별이 필요한 시점. **(override — `docs/adr/0007` / CMP-DIRECT, 2026-06-08)**: 운영자 결정으로 **상담 신청/리드 생성은 비회원(익명 Supabase 토큰)도 허용**한다. `POST /leads` 는 익명 OK 인증을 쓰고 `consultation_leads.is_anonymous` 로 익명 여부를 보존한다. 리드 테이블은 PostgREST 미노출 + RLS client grant 없음(백엔드 전용, PII 보호).
   - (c) **리포트 저장 / 공유** — 익명 세션 만료 이후에도 리포트 다시 보기·공유 링크 발급이 필요한 시점.
3. **자체 비밀번호 가입 금지.** `users` 또는 어떤 인증 테이블에도 password / hash / salt 컬럼을 두지 않는다. 모델 메타데이터 단위 테스트(`tests/auth/test_no_password_columns.py` 권고)로 가드한다.
4. **OAuth provider 정책은 `google` · `naver` · `kakao` 기준.** Supabase Auth provider / `auth.identities` 가 identity 를 관리한다. 신규 provider 추가 시 ADR + Supabase provider 설정 + 필요 public schema migration 이 필요하다.
5. **Kakao Sync 약관 분리 저장.** Kakao 는 Kakao Sync 약관 동의 source 를 우리 내부 약관 동의와 분리하여 저장한다 (별도 `terms_consents` row + `source='kakao_sync'`). Kakao 가 자체 약관 화면을 이미 제공하므로 우리 내부 약관 화면을 중복 노출하지 않는다.
6. **Google / Naver 는 내부 약관 동의 화면을 거친다.** OAuth 콜백 → 내부 약관 동의 화면 → 가입 완료 → 채팅/상담 진입 순. 약관 미동의 시 가입 미완료, 익명 세션 유지.
7. **비회원 식별자.** Supabase Anonymous Sign-In 이 생성하는 `auth.users.id` 와 Supabase access token 이 정본이다. 브라우저 `localStorage.jippin_anonymous_user_id` 및 API `/auth/anonymous-users` 는 legacy 경로이며 신규 호출 금지.
8. **가입 성공 시 claim.** anonymous → permanent 전환은 `supabase.auth.linkIdentity()` 로 같은 `auth.users.id` 를 승격한다. 익명 세션의 도면·리포트·판단 결과는 해당 Supabase user id 를 그대로 사용한다.
9. **동일 이메일 + 다른 provider 자동 병합 금지.** 같은 이메일이 카카오·구글·네이버에서 각각 가입되면 별개 user 로 둔다. 사용자가 명시적으로 “계정 통합” 흐름을 요청하기 전까지 자동 병합·linking 금지. 자동 병합은 계정 탈취 벡터.
10. **OAuth state store.** Authorization Code Flow 의 `state` / `nonce` / `code_verifier` 는 **Redis** 에 짧은 TTL(≤10분)로 저장한다. 메모리 단일 인스턴스 가정과 정합.

**모델 가드 (요약 — 정본은 ADR-0003).**

- `users(id uuid pk, email text null, display_name, status, created_at, last_login_at)` — **password 컬럼 영구 금지**. citext 의존 회피, 대소문자 무시 매칭은 `LOWER(email)` functional index 로.
- Supabase managed: `auth.users(id uuid pk, is_anonymous, email, ...)`, `auth.identities(user_id, provider, provider_id, ...)`.
- `public.users(id uuid pk fk → auth.users.id, display_name, profile_image_url, role, status, last_login_at, created_at, updated_at)` — 앱 프로필/RBAC 전용. email/password/provider subject 를 중복 저장하지 않는다.
- `public.terms_consents(id, user_id uuid fk → auth.users.id, term_id, version, source text, agreed_at)` — `source ∈ {'internal_signup', 'kakao_sync', ...}`.

**환경변수 이름 (정본은 `apps/api/.env.example`).**

- `KAKAO_REST_API_KEY`, `KAKAO_CLIENT_SECRET`, `KAKAO_REDIRECT_URI`
- `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI`
- `NAVER_OAUTH_CLIENT_ID`, `NAVER_OAUTH_CLIENT_SECRET`, `NAVER_OAUTH_REDIRECT_URI`
- `OAUTH_STATE_REDIS_URL`, `OAUTH_STATE_TTL_SECONDS`
- `AUTH_JWT_SECRET`, `AUTH_JWT_ALG`, `AUTH_JWT_ACCESS_TTL_SECONDS`, `AUTH_JWT_REFRESH_TTL_SECONDS`
- `ANON_SESSION_HEADER` _(기본 `x-jippin-anon-id`)_, `ANON_SESSION_TTL_DAYS`
- `FRONTEND_AUTH_SUCCESS_URL`, `FRONTEND_AUTH_FAILURE_URL` — API 가 콜백 처리 후 302 하므로 **`apps/api/.env.example`** 가 정본. `apps/web/.env.example` 의 `NEXT_PUBLIC_FRONTEND_AUTH_SUCCESS_URL`, `NEXT_PUBLIC_FRONTEND_AUTH_FAILURE_URL` 은 SPA 표시용 보조 표기.

### 4.8 디자인 SSOT — 임의 변경 금지

집핀 브랜드의 시각·문구·결과 화면·다운로드 산출물 디자인은 [`docs/design/DESIGN.md`](docs/design/DESIGN.md) 진입점과 그 하위 정본(`BRAND.md` / `COLOR_SYSTEM.md` / `TYPOGRAPHY.md`) 이 단일 정본(SSOT) 이다.

- **브랜드 색·상태 색·법적 고지 문구·폰트·문체** 를 코드에서 임의로 바꾸지 않는다. 임시 토큰(`#1f6feb` 등) 이 보이면 SSOT 토큰(`brand.primary` 등) 으로 교체하는 PR 을 별도로 낸다.
- 색·폰트의 **의미가 바뀌는 변경**(역할 변경, 새 토큰 도입, 톤 재정의) 은 SSOT 문서를 먼저 갱신하고 PR 본문에 영향 범위(`BRAND` / `DESIGN` / `DOCS` / 필요 시 `WEB`) 를 명시한다. 필요 시 ADR 또는 `docs/design/decisions/` 결정 기록을 함께 남긴다.
- 리포트·다운로드·공유링크 OG 의 시각/문구 변경은 `§4.6` 법적 고지 누락 금지와 교차 검증한다 (`COLOR_SYSTEM.md §5`, `TYPOGRAPHY.md §4.5` 참조).
- 디자인 SSOT 의 §1 브랜드 약속·금지 톤·법적 고지는 **CEO 봉인 영역**이며, 변경하려면 새 CEO 브리프 리비전이 필요하다.

---

## 5. 자동화 에이전트 작업 프로토콜 (Paperclip)

1. **Wake payload 우선** — `PAPERCLIP_WAKE_PAYLOAD_JSON` 이 가리키는 이슈만 처리한다. 다른 이슈로 분기하지 않는다.
2. **본 이슈 범위를 벗어나면 자식 이슈를 생성** — `POST /api/issues` 로 자식 이슈를 만들고 본 이슈에 blockedBy 또는 related로 묶는다. 직접 폭주 X.
3. **변경 후 반드시 final disposition** — `done` / `in_review` / `blocked` / `in_progress(live continuation only)` 중 하나로 본 이슈 상태를 정리.
4. **읽기 자료** — 정본 docx/xlsx는 `tooling/extract_specs.py` 로 `docs/_extracted/` 에 텍스트 캐시가 만들어져 있다. 정본이 갱신되면 캐시도 갱신할 것.
5. **시크릿 헌팅** — PR/커밋 단계에서 `npg_`, `sk-`, `AKIA` 등 시크릿 패턴이 들어가지 않도록 검사. 발견 시 즉시 회전 요청.
6. **모순 보고** — 명세 4종 간 모순을 발견하면 `docs/명세서-모순.md`(없으면 생성)에 기록하고 후속 이슈로 분리.

### 5.7 병렬 에이전트 격리 — git worktree 필수

> **배경.** Paperclip 멀티에이전트가 같은 루트 체크아웃에서 브랜치를 바꿔가며 작업하면, 서로의 변경·브랜치·PR 상태가 섞여 CMP-523 처럼 미머지 브랜치와 중복 PR 이 대량으로 생긴다. 2026-05-28 CMP-523 병렬 브랜치/PR 정리 사고 재발 방지.

**Paperclip 에이전트는 코드·문서 변경을 루트 체크아웃(`C:\Users\jhyou\2026\jippin`)에서 직접 수행하지 않는다.** 루트 체크아웃은 조정·조회·PR 정리용으로만 사용하고, 실제 변경은 이슈별 독립 worktree 에서만 진행한다.

원칙:

- **1 Paperclip 이슈 = 1 브랜치 = 1 worktree.** 자식 이슈는 자식 브랜치와 자식 worktree 를 새로 만든다.
- 서로 다른 에이전트가 같은 worktree 를 공유하지 않는다.
- worktree 위치는 기본적으로 `C:\Users\jhyou\2026\jippin-worktrees\<CMP-ID>-<slug>` 를 사용한다.
- 이미 브랜치가 있으면 새로 만들지 말고 `git worktree add <path> <branch>` 로 해당 브랜치를 붙인다.
- 이미 worktree 경로가 있으면 `git -C <path> status --short --branch` 로 같은 이슈의 깨끗한 작업공간인지 확인한 뒤 재사용한다.
- 루트 체크아웃의 변경을 치우기 위해 stash/reset/checkout 을 하지 않는다. 충돌이 있으면 새 worktree 를 만들거나 해당 worktree 에서만 해결한다.

표준 시작 절차 (PowerShell) — **§4.2 정합: 기본 base 는 `origin/dev`. `origin/main` base 는 hotfix/release 컷 같은 예외에만 사용**:

```powershell
$issue = "CMP-XYZ"
$branch = "feat/cmp-xyz-thing"     # type ∈ feat | fix | docs | refactor | chore | perf | test | security
$worktree = "C:\Users\jhyou\2026\jippin-worktrees\$issue-thing"

New-Item -ItemType Directory -Force -Path C:\Users\jhyou\2026\jippin-worktrees | Out-Null
git -C C:\Users\jhyou\2026\jippin fetch origin
git -C C:\Users\jhyou\2026\jippin worktree add -b $branch $worktree origin/dev    # ← dev 가 정본 base
Set-Location $worktree
git status --short --branch
```

이미 원격 브랜치가 있을 때:

```powershell
$branch = "feat/cmp-xyz-thing"
$worktree = "C:\Users\jhyou\2026\jippin-worktrees\CMP-XYZ-thing"

New-Item -ItemType Directory -Force -Path C:\Users\jhyou\2026\jippin-worktrees | Out-Null
git -C C:\Users\jhyou\2026\jippin fetch origin
git -C C:\Users\jhyou\2026\jippin worktree add -b $branch $worktree origin/$branch
Set-Location $worktree
```

**`origin/main` 에서 분기해도 되는 예외** (드물어야 함):

- hotfix — 운영 사고 즉시 패치. 머지 후 `dev` 로 back-merge 필수.
- release 컷 — `dev` 가 아직 머지되지 않은 채 운영에 특정 시점을 찍어야 할 때 CTO/DevOps 승인.
- 위 외 모든 경우 `origin/dev` 를 base 로 한다.

이미 로컬 브랜치가 있을 때는 `-b` 없이 붙인다: `git -C C:\Users\jhyou\2026\jippin worktree add <path> <branch>`.

push/PR 전 자기 점검:

- [ ] `git status --short --branch` 가 의도한 이슈 브랜치를 가리킨다.
- [ ] 현재 경로가 `jippin-worktrees\<CMP-ID>-...` 이며 루트 체크아웃이 아니다.
- [ ] `git worktree list` 에서 같은 이슈를 여러 에이전트가 공유하지 않는다.
- [ ] PR 본문에 Paperclip 이슈 ID 와 영향 모듈을 적었다.

PR 머지 또는 폐기 후 정리:

```powershell
git -C C:\Users\jhyou\2026\jippin worktree remove C:\Users\jhyou\2026\jippin-worktrees\CMP-523-bootstrap
git -C C:\Users\jhyou\2026\jippin branch -d chore/cmp-523-bootstrap
git -C C:\Users\jhyou\2026\jippin push origin --delete chore/cmp-523-bootstrap
```

단, worktree 가 dirty 이면 삭제하지 말고 변경 소유자와 상태를 확인한다.

### 5.8 한글(UTF-8) 인코딩 — 이슈/코멘트/문서 작성 시 절대 위반 금지

> **배경.** Windows(PowerShell/cmd.exe) 호스트에서 `curl -d '{"title":"한글"}' ...` 형태로 Paperclip API 를 인라인 호출하면, 활성 코드페이지(CP949)와 curl 의 UTF-8 가정이 충돌해 본문이 `?` 로 깨진 채 서버에 저장된다. **이 손상은 비가역적**(원문 복원 불가)이며, 보드와 위임받은 에이전트 모두 작업 컨텍스트를 잃는다. 2026-05-28 CMP-524 사고(자식 이슈 7개 제목·본문 전손) 재발 방지.

**모든 에이전트는 Paperclip API(POST/PATCH `/api/...`)로 한글 콘텐츠를 보낼 때 다음 절차를 따른다.**

1. **JSON 페이로드를 파일로 먼저 작성** — Claude Code `Write`/`Edit` 툴은 기본 UTF-8 (BOM 없음). PowerShell `Out-File`/`Set-Content` 사용 시 반드시 `-Encoding utf8NoBOM`.
2. **`curl` 은 `--data-binary @<파일>` + 명시적 charset 헤더** 로 전송한다.
3. **인라인 `-d '...'` 또는 here-string 으로 한글을 박지 않는다.** PowerShell here-doc 도 환경에 따라 변환된다 — 금지.

표준 호출 패턴 (Git Bash / MSYS):

```bash
# 1) JSON 본문을 UTF-8 파일로 저장 (Claude Code Write 툴 권장)
#    또는 Git Bash 한정: cat > .tmp/payload.json <<'EOF' ... EOF
#    PowerShell here-string 금지.

# 2) PATCH/POST 호출 — --data-binary @ 와 charset 헤더 반드시 포함
curl -s -X PATCH \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json; charset=utf-8" \
  --data-binary @.tmp/payload.json \
  "$PAPERCLIP_API_URL/api/issues/<ID>" \
  -o .tmp/resp.json

# 3) 응답을 node 로 검증 — PowerShell Get-Content 는 인코딩 자동변환 위험
node -e "const d=JSON.parse(require('fs').readFileSync('.tmp/resp.json','utf8')); console.log(d.title)"
```

자기 점검 체크 (이슈 생성/수정 직후 즉시):

- [ ] 같은 ID 를 `GET /api/issues/<ID>` 로 재조회해 `title`/`description` 에 `?` 가 아닌 정상 한글이 들어있는지 확인.
- [ ] 깨진 흔적이 보이면 즉시 PATCH 로 복구 + 사고 코멘트.
- [ ] 자식 이슈를 7개 이상 일괄 생성할 때는 첫 1개 직후 위 검증을 통과해야 다음 6개를 만든다.

위반 시: 위임 사슬의 모든 자식 이슈가 영문/`?` 만 보여 보드와 위임받은 에이전트가 작업 식별 불가. **인수 거부 사유**다.

> 사람 작업자 주의: 시스템 PowerShell 콘솔 폰트가 `Lucida Console` 인 경우 정상 출력된 한글도 콘솔에서는 `?` 로 보일 수 있다. **보드(웹 UI) 또는 `GET /api/issues/<ID>` 응답을 진실의 원천으로 삼는다.**

### 5.9 CI/CD 워크플로우 — Supabase Integration + drift guard + status wrapper (CMP-603 cutover 완료)

`.github/workflows/` 가 다음과 같이 책임을 나눈다.

- **`ci.yml` → `migrate-check`** (PR) — Supabase SQL migration drift 가드. `apps/api/src/models/**/*.py` 가 변경됐는데 `supabase/migrations/*.sql` 동행이 없으면 fail. Neon / Alembic 의존 없음, secret 불필요. 정본: [`docs/runbooks/supabase-branching.md`](docs/runbooks/supabase-branching.md) §6.3.2. `ci-status` 메타 게이트에 포함되어 브랜치 보호의 required check 1개 (`ci-status`) 로 자동 보장.
- **`deploy.yml`** (push to `dev` / `main`) — 어플리케이션 빌드 smoke + 클라우드 배포 스텁. **DB migration 미실행** (Supabase GitHub Integration 단독 책임). 후속 클라우드 target (Vercel / Fly / Cloud Run / Lightsail) 은 별도 이슈에서 채운다.
- **`supabase-status.yml`** (PR) — path-filter deadlock 회피 wrapper. `supabase/**` 변경 없는 PR 은 자체 succeed (skip 의미), 변경 있는 PR 은 `vars.SUPABASE_INTEGRATION_CHECK_NAME` 으로 지정된 Supabase 측 check context 결과를 polling 해 그대로 반영. 변수 미설정 시 fail (운영 사고를 초록색으로 숨기지 않음). 정본: [`docs/runbooks/supabase-branching.md`](docs/runbooks/supabase-branching.md) §6.3 / §6.3.1.
- **`secret-scan.yml`** / **`main-promotion-guard.yml`** / **`pr-title-lint.yml`** — 변경 없음 (CMP-533 / branch-strategy 가드).
- **`_archive/neon-pr-branch.yml.archived`** — 비활성. Neon GitHub integration 시절의 PR preview 잡을 이력 참조용으로 보존. GitHub Actions 는 `.yml` 확장자만 워크플로우로 인식하므로 본 파일은 실행되지 않는다.

DB 마이그레이션 적용 책임 (cutover 후 봉인):
- `dev` push → **Supabase GitHub Integration** 이 development branch 에 `supabase/migrations/*.sql` 을 timestamp 순서로 적용.
- `main` push → **Supabase GitHub Integration** 이 production branch 에 동일 적용. 콘솔의 "production migrations" 토글 ON 이 전제 (`docs/runbooks/supabase-branching.md` §3.1 U7).
- `staging` → Supabase 콘솔에서 사람이 수동 promote 또는 로컬 `supabase db push` (정본: §3.2 A1.2).
- preview/pr-N (ephemeral) → Automatic Branching 이 PR base 매핑에 따라 development 또는 production parent 에서 분기, SQL apply.

운영 시크릿 / 변수 (Settings → Secrets and variables → Actions / Environments):

- `SUPABASE_ACCESS_TOKEN` (Secret) — Personal Access Token, Supabase Console → Account → Access Tokens 발급.
- `SUPABASE_PROJECT_REF_PROD` / `SUPABASE_PROJECT_REF_DEV` / `SUPABASE_PROJECT_REF_STAGING` (Variable) — 환경별 Supabase project ref / branch project id. 값 자체는 비밀이 아니지만 변수로 관리해 PR 본문 노출을 차단.
- `SUPABASE_DB_PASSWORD_PROD` / `SUPABASE_DB_PASSWORD_DEV` / `SUPABASE_DB_PASSWORD_STAGING` (Secret) — 각 persistent branch DB password.
- `SUPABASE_INTEGRATION_CHECK_NAME` (Variable) — `supabase-status.yml` wrapper 의 polling target. 첫 `supabase/**` PR 에서 실제 check context 이름을 확인한 뒤 등록 (정본: §6.3.1).

> 실값 발급/등록은 사용자가 Supabase 콘솔 + GitHub Settings 에서 수행한다. 본 PR 머지 후 사용자 체크리스트는 PR 본문 참고. cutover 이후 폐기된 Neon 시크릿/변수 (`NEON_API_KEY`, `NEON_PROJECT_ID`, `NEON_TEST_DATABASE_URL`, `NEON_DEV_DATABASE_URL`, `NEON_PROD_DATABASE_URL`, `NEON_DEV_PARENT_BRANCH`, `NEON_BRANCH_CAP`) 는 GitHub Settings 에서 삭제 대상이다.

---

## 6. 표준 명령 (CTO ADR-0001 봉인 후 정본)

각 앱의 정본 명령은 해당 앱 README에 두되, 모노레포 루트에서 자주 쓰는 명령은 다음과 같다.

```bash
# 전체 부팅 (web + api + redis. DB는 외부 managed Supabase Postgres)
docker compose -f infra/compose/docker-compose.yml up --build

# 백엔드 단독 (uv)
cd apps/api && uv sync && uv run uvicorn src.main:app --reload --port 8000

# 프론트엔드 단독 (pnpm 9.x — apps/web engines.pnpm <10)
cd apps/web && corepack pnpm@9 install && corepack pnpm@9 dev

# 헬스체크 (DB SELECT 1 결과 포함)
curl http://localhost:8000/healthz

# DB 마이그레이션 (forward SSOT — Supabase SQL):
#   - dev/main 으로 머지하면 Supabase GitHub Integration 이 자동 적용.
#   - 로컬에서 직접 적용해야 할 때 (staging promote / 콘솔 link 후 검증):
#       supabase link --project-ref <BRANCH_PROJECT_REF>
#       supabase db diff --linked       # remote 상태와 비교 (plain `db diff` 는 local Docker DB)
#       supabase db push                # SQL 마이그레이션 적용
#   세부 절차: docs/runbooks/supabase-branching.md §3.2 / supabase-migration-plan.md
#
# Alembic 은 historical reference 만 — 신규 forward migration 생성/적용 금지.

# 정본 docx/xlsx 텍스트 캐시 재생성
python tooling/extract_specs.py
```

---

## 7. 본 문서의 변경 절차

- CEO 가 본 문서의 §1·§3·§4를 봉인한다. 변경은 새 CEO 브리프 리비전을 통해서만 일어난다.
- CTO·각 라인 리드는 §2·§5·§6을 PR로 갱신할 수 있다.
- 모든 갱신은 gitmoji `📝 docs:` 커밋과 PR 본문에 영향 범위를 명시한다.

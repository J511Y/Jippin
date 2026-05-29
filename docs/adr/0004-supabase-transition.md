# ADR 0004 — Neon → Supabase 전환 (DB / Auth) + ADR-0003 부분 supersede

- **상태**: **Proposed (2026-05-29)** — CEO 결정 + CTO 검토 + 사용자 콘솔 작업 대기.
- **제안자**: CTO (agent `4edca504-7a87-4c01-93b8-7524a223cd50`)
- **승인 권자**: CEO (정책), CTO (기술), Security Lead (탈취 벡터 재평가), Backend Lead (모델·핸들러 영향)
- **인계 출처**: CMP-573 본문 (Supabase 전환 정책 발의)
- **관련 이슈**: **CMP-573** (본 ADR) · CMP-557 (ADR-0003 의 정책 모이슈) · CMP-558 (트랙 A — ADR-0003 발행)
- **슈퍼시드 (부분)**: 본 ADR 이 Accepted 되면 아래 §6 표대로 ADR-0001 T3 / ADR-0003 §2.1·§2.3 / `AGENTS.md §4.7` 의 일부 절을 부분 supersede 한다. 본 ADR 이 Proposed 인 동안에는 기존 ADR-0001 / ADR-0003 / AGENTS.md 가 정본을 유지한다.
- **강한 제약 (변경 금지 — CEO 브리프 §5 봉인 상속)**:
  - 단일 인스턴스 + `docker-compose`. 앱 배포(웹·FastAPI·AI 서버)는 별도 클라우드 (ADR-0002 / AWS Lightsail 예정).
  - 결과 화면 법적 고지 (`AGENTS.md §4.6`) 누락 금지.
  - 자체 비밀번호 / 비밀번호 해시 컬럼 영구 금지 — Supabase Auth 채택해도 우리 측 별도 password 컬럼 신설 금지.

---

## 0. 결정 요약 (TL;DR)

| 항목 | ADR-0001 / ADR-0003 (현재 정본) | 본 ADR 결정 (Proposed) | 영향 |
|---|---|---|---|
| **DB 호스팅** | Neon Serverless Postgres | **Supabase Postgres** (managed PostgreSQL + PostgREST + Realtime + Edge Functions + Storage 옵션) | ADR-0001 §4 supersede 후보 |
| **인증 SSOT** | 자체 `users` 테이블 + `external_sso_accounts` + 자체 콜백/JWT | **Supabase Auth (`auth.users`)** + 우리 측 `public.users` 는 `auth.users.id` 를 FK 로 받는 프로필 테이블 | ADR-0003 §2.1·§2.2 부분 supersede |
| **비회원 사전검토** | 자체 `anonymous_users` + `localStorage` UUID + `x-jippin-anon-id` 헤더 | **Supabase Anonymous Sign-In** (`auth.users` 의 `is_anonymous=true` row + Supabase 발급 JWT) → 가입 시 같은 row 를 `is_anonymous=false` 로 업그레이드 | ADR-0003 §2.1 (`anonymous_users` 테이블), §2.2 (`x-jippin-anon-id` 헤더 흐름) supersede 후보 |
| **자동 병합 (동일 이메일)** | **자동 병합 금지** — 단일 provider 탈취 벡터 (CEO 정책 / ADR-0003 §2.3) | **Supabase Identity Linking 허용** — 동일 검증된 이메일에 대해 두 번째 provider 가 동일 `auth.users.id` 로 묶임 | ADR-0003 §2.3 / AGENTS.md §4.7 #9 supersede — **CEO 결정 필요 (§7 미해결)** |
| **OAuth provider** | `google` · `naver` · `kakao` 3종 ENUM 고정 (자체 콜백) | **Google / Kakao**: Supabase built-in provider. **Naver**: Supabase Custom OAuth/OIDC provider (PoC 필요) | ADR-0003 §2.2 (라우트 정본) supersede — 우리 측 `/auth/{provider}/start` · `/auth/callback/{provider}` 폐기 후보 |
| **OAuth state store** | Redis `oauth_state:*` / `pending_signup:*` TTL ≤10분 | **Supabase 측이 PKCE state · 약관 동의 → 가입 완료 사이 상태를 관리** | ADR-0003 §2.2 supersede — 자체 Redis state store 폐기. Redis 자체는 채팅·세션 캐시로 잔존. |
| **Refresh Token** | 자체 JWT `AUTH_JWT_REFRESH_TTL_SECONDS=604800` (7일) | **Supabase Auth refresh token** (Supabase Dashboard / Project Settings 의 JWT 수명 정본) | ADR-0003 §봉인표 + 보안 런북 POL-AUTH-002 재정렬 필요 |
| **객체 스토리지** | Cloudflare R2 (zero-egress, 한국 PoP) | **R2 유지** — Supabase Storage 전환은 별도 ADR / 후속 이슈. presigned URL 전략 그대로. | ADR-0001 §6 유지 |
| **AI / LLM** | SAM2 + OpenAI GPT-4.1-mini / GPT-4o, LangChain v0.3+ | **유지** — Supabase 는 AI 서버 호스팅 대상이 아니다. | ADR-0001 §7 유지 |
| **앱 배포** | AWS Lightsail Seoul (ADR-0002 Proposed) | **유지** — Supabase 는 FastAPI / AI 서버 배포처가 아니다. Web / API 컨테이너는 Lightsail (or ADR-0002 후속) 위에서 계속 운영. | ADR-0001 §8 / ADR-0002 유지 |
| **약관 동의 (`terms_consents`)** | `internal_signup` / `kakao_sync` source 분리 저장, 우리 측 `terms_consents` 테이블 | **유지** — Supabase Auth 가 동의 모달을 대체하지 않으므로 우리 측 `public.terms_consents` 는 그대로. `user_id` 가 `auth.users.id` 를 참조하도록만 정렬. | ADR-0003 §2.1 (4번 테이블) 정합 |

> **본 ADR 은 Proposed.** Accepted 전까지 어떤 구현 PR 도 본 결정을 근거로 들 수 없다. 후속 자식 이슈 (§6) 는 본 ADR 이 Accepted 된 직후 생성한다.

---

## 1. 결정 컨텍스트

### 1.1 무엇을 결정해야 하는가

CMP-573 에서 사용자(CEO 권한 행사) 가 **Neon Postgres + 자체 OAuth/JWT + 자체 `anonymous_users`** 스택을 **Supabase 에 통합 위탁**하는 방향으로 전환을 발의했다.

핵심 가설:

1. **인증 운영 부담 감소.** OAuth Authorization Code / PKCE / state / refresh / linking / password reset 라이프사이클을 우리가 직접 코딩·운영하지 않는다. 보안 사고 표면(예: state replay, refresh rotation, anon claim race)을 Supabase 가 떠안는다.
2. **익명 → 가입 claim 단순화.** Supabase Anonymous Sign-In 은 anon `auth.users.id` 를 그대로 가입 row 로 승격(`is_anonymous=true` → `false`)할 수 있어, 우리가 직접 `anonymous_users.converted_user_id` 로 join 하던 코드가 사라진다.
3. **DB + 인증 + Realtime + Edge Functions 통합.** 한 콘솔에서 RLS · Auth · JWT 수명 · provider 콘솔 항목을 본다. CEO 가 Supabase Dashboard 한 곳에서 운영 가시성을 확보할 수 있다.

대신 다음을 **포기**한다 (§3 에서 상세 비교):

- ADR-0003 §2.3 **자동 병합 금지 정책의 일부**. Supabase identity linking automatic 모드를 켜면 동일 이메일이 검증된 다른 provider 가입을 같은 `auth.users.id` 로 묶는다. 이 점이 본 ADR 의 가장 큰 변경이며 CEO 결정이 필요하다 (§7).
- ADR-0003 §2.2 의 **자체 콜백 라우트** (`POST /auth/{provider}/start` + `GET /auth/callback/{provider}`). Supabase Auth 가 PKCE state 와 약관 동의 후 user upsert 까지 1:1 대체한다.
- ADR-0001 §4 의 **Neon 봉인**. Supabase 도 PostgreSQL 이지만 호스팅 사업자가 다르고 마이그레이션·branching 패턴이 다르다 (§4.1).

### 1.2 평가 기준

1. **사고 표면 vs 신규 의존성.** 자체 코드 사고 표면 ↓, 외부 사업자(Supabase) 의존 ↑. 트레이드오프가 본 ADR 의 핵심.
2. **CEO 정책 보존.** 비회원 사전검토 허용, 전환 시점 OAuth 의무, 자체 비밀번호 영구 금지, 결과 화면 법적 고지 — 본 ADR 이 어느 것도 무력화하지 않는다.
3. **마이그레이션 비용.** ADR-0003 트랙 B/C/D 가 아직 미완(자식 이슈 단계). 코드 변경량이 **상대적으로 적은 시점**이라 Neon → Supabase 전환의 매몰 비용이 가장 낮다. ← 본 ADR 발의 타이밍의 핵심 정당화.
4. **데이터 주권 / 한국 리전.** Supabase 는 Seoul (ap-northeast-2) 리전 옵션 존재. Neon 은 ap-southeast-1 (싱가포르). 사용자 PII 한국 잔존 측면에서 Supabase 유리 (단, **사용자 확정 필요** §7).
5. **공급사 lock-in 거리.** PostgreSQL 자체는 둘 다 표준이라 SQL 수준 이식성은 높음. 다만 `auth.users` + RLS 패턴은 Supabase 의존이라 잠재 lock-in. Supabase 자체 호스팅(self-hosted) 으로 빠질 경로가 있다는 점이 lock-in 거리 단축.

### 1.3 외부 제약

- CEO 브리프 §5 강한 제약 — 단일 인스턴스 + docker-compose. 본 ADR 은 이 제약을 깨지 않는다 (앱 컨테이너는 Lightsail 그대로).
- AGENTS.md §4.4 시크릿 정책 — Supabase URL / anon key / service role key 는 `.env` / 운영 시크릿 매니저. `.env.example` 에는 변수명만.
- AGENTS.md §4.6 결과 화면 법적 고지 — Supabase Auth UI 위젯을 쓰더라도 우리 측 결과 화면 컴포넌트는 우리 코드가 렌더하므로 영향 없음.
- `docs/runbooks/security-policy.md` POL-AUTH-002 (refresh 토큰 7일) — Supabase 의 기본 refresh TTL 과 정합하도록 Project Settings 에서 정렬해야 함 (§4.4).

---

## 2. 결정 (정책 봉인 — Proposed)

### 2.1 Supabase 채택 범위

본 ADR 이 채택하는 Supabase 표면은 **2종**으로 한정한다. 다른 표면은 별도 ADR / 후속 이슈에서 결정한다.

| Supabase 표면 | 본 ADR 채택 여부 | 비고 |
|---|---|---|
| **Postgres (DB)** | ✅ 채택 — `public` 스키마는 우리 도메인 (도면·리포트·약관 등) | 마이그레이션 도구는 §4.2 |
| **Auth (`auth.users` + provider 콜백 + 익명 + identity linking)** | ✅ 채택 — 인증 SSOT | RLS 활용은 §4.3 |
| **Realtime** | 🟡 보류 — 후속 이슈에서 채팅 / OVERLAY 실시간성 재평가 시 결정 | 본 ADR 범위 외 |
| **Edge Functions** | 🟡 보류 — FastAPI 가 정본 API. Edge Function 은 webhook 정합용 옵션. | 본 ADR 범위 외 |
| **Storage** | ❌ 채택 안 함 — Cloudflare R2 유지 (ADR-0001 §6 보존) | 별도 ADR 필요 시 발행 |
| **Auth Hooks (Custom Access Token / Send SMS 등)** | 🟡 보류 — Naver Custom OAuth PoC 결과에 따라 결정 | 본 ADR §4.5 PoC |
| **Vault / Secrets** | ❌ 채택 안 함 — 시크릿은 운영 매니저 (현 정책) 유지 | — |

> Supabase 자체호스팅(self-hosted) 옵션은 본 ADR 범위 외. MVP 는 Supabase managed (cloud) 를 전제.

### 2.2 인증 모델 (ADR-0003 §2.1 부분 supersede)

**새 모델 (Proposed).**

```sql
-- Supabase 가 자동 생성·관리:
--   auth.users           — 인증 SSOT. id uuid pk.
--                          is_anonymous boolean (anon sign-in 사용 시 true)
--                          email text                       (provider 별 검증 상태 별도 컬럼)
--                          ... (Supabase managed)
--   auth.identities      — provider × subject. 자동 생성.
--                          user_id uuid fk auth.users(id)
--                          provider text                    (google | kakao | naver | ...)
--                          identity_data jsonb              (provider userinfo cache)
--                          email text                       (검증된 이메일 1순위)
--                          UNIQUE (provider, provider_id)

-- 우리 도메인 (public 스키마):
CREATE TABLE public.users (
  id              UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  display_name    TEXT,
  status          TEXT NOT NULL DEFAULT 'active',  -- active | suspended | deleted
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_login_at   TIMESTAMPTZ
  -- 의도적으로 password/hash/salt 컬럼 없음. 모델 메타데이터 테스트가 가드.
  -- email 은 auth.users 가 정본. 중복 저장 금지.
);

-- 약관 동의 — ADR-0003 §2.1 (4번 테이블) 형상 보존, user_id 참조처만 갱신.
CREATE TABLE public.terms_consents (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  term_id     TEXT NOT NULL,
  version     TEXT NOT NULL,
  source      TEXT NOT NULL,      -- 'internal_signup' | 'kakao_sync'
  agreed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, term_id, version, source)
);
```

**폐기되는 ADR-0003 §2.1 테이블.**

| 테이블 | 본 ADR 처리 |
|---|---|
| `anonymous_users` | **폐기.** Supabase Anonymous Sign-In 의 `auth.users.is_anonymous=true` row 가 대체. 익명 세션의 도면·리포트는 `auth.users.id` 를 직접 FK 로 가진다. |
| `external_sso_accounts` (PG ENUM `external_sso_provider` 포함) | **폐기.** `auth.identities` 가 1:1 대체. `(provider, provider_id)` UNIQUE 가드도 Supabase 가 제공. ENUM 봉인은 Supabase provider 활성 화면에 위임. |
| `users` (우리 측) | **변형.** `id` 가 `auth.users(id)` 의 FK 가 되고 email / oauth 컬럼은 제거. `display_name` / `status` / `last_login_at` 같은 도메인 프로필만 잔존. |
| `terms_consents` | **유지.** `user_id` 참조처만 `auth.users(id)` 로 갱신. |

**비밀번호 컬럼 영구 금지 가드 (보존).** 모델 메타데이터 테스트 (`apps/api/tests/auth/test_no_password_columns.py`) 는 본 ADR 이후에도 **`public` 스키마** 전체를 스캔하도록 유지한다. `auth` 스키마는 Supabase 관리 영역이므로 가드 범위 외 (Supabase 가 `encrypted_password` 컬럼을 자체적으로 관리하지만, 우리는 우리 측에 password 컬럼이 없도록만 잠근다).

### 2.3 비회원 사전검토 흐름 (ADR-0003 §2.2 부분 supersede)

**새 흐름 (Proposed).**

```
[브라우저]                                              [Supabase Auth]
  │  1) 익명 진입
  │     supabase.auth.signInAnonymously()                   ────▶
  │                                                  auth.users row 생성
  │                                                  (is_anonymous=true)
  │                                                  Supabase JWT 발급      ◀────
  │  2) (전환 시점) 사용자가 Google/Kakao/Naver 클릭
  │     supabase.auth.linkIdentity({ provider })           ────▶
  │                                                  provider OAuth 진행
  │                                                  콜백 → auth.identities
  │                                                  auth.users.is_anonymous=false
  │                                                  (동일 row 승격 — claim 자동)
  │  3) Google/Naver: 우리 측 약관 동의 모달 노출
  │     약관 동의 → POST /api/auth/terms-accept
  │     서버: Supabase JWT 검증 → public.terms_consents insert
  │            (source='internal_signup')
  │     Kakao: Kakao Sync 약관 신뢰
  │            서버 측 콜백에서 Supabase Auth Hook(또는 webhook) 으로
  │            public.terms_consents insert (source='kakao_sync')
  │  4) 익명 세션의 도면·리포트는 같은 auth.users.id 를 그대로 사용 → claim 자동.
```

**API 라우트 변화.**

| 기존 (ADR-0003 §2.2) | 본 ADR (Proposed) |
|---|---|
| `POST /auth/{provider}/start` | **폐기.** 클라이언트가 `supabase.auth.signInWithOAuth({provider})` 직접 호출. |
| `GET /auth/callback/{provider}` | **폐기.** Supabase 가 콜백 호스팅. Supabase 콜백 → 우리 프론트 redirect URL 로 복귀. |
| `POST /auth/refresh` | **폐기.** Supabase JS SDK 가 자동 refresh. |
| `POST /auth/logout` | **폐기.** `supabase.auth.signOut()` 사용. Redis 블랙리스트 불필요. |
| (신규) `POST /api/auth/terms-accept` | **신설.** Google/Naver 가입 직후 우리 측 약관 동의를 받아 `public.terms_consents` 에 기록. Supabase JWT 를 `Authorization: Bearer` 로 검증. |
| (신규) Supabase Auth Hook (`before_user_created` or `after_user_created`) | **검토.** Kakao 콜백에서 Kakao Sync 약관 source 분리 저장을 자동화. 본 ADR §4.5 PoC 범위. |

**환경변수 변화 (정본은 `.env.example` PR 에서 봉인).**

```env
# 신설 (Supabase)
SUPABASE_URL=                       # https://<project-ref>.supabase.co
SUPABASE_ANON_KEY=                  # 브라우저 측 (anon role)
SUPABASE_SERVICE_ROLE_KEY=          # 서버 측만 (admin/RLS bypass) — 절대 브라우저에 노출 금지
SUPABASE_JWT_SECRET=                # 우리 API 가 Supabase JWT 검증할 때 사용 (또는 JWKS URL)
SUPABASE_PROJECT_REF=               # 마이그레이션 CLI 용
DATABASE_URL=                       # Supabase pooler / non-pooler — Neon 자리 대체

# 폐기 (ADR-0003 환경변수)
KAKAO_REST_API_KEY=                 # → Supabase Dashboard / Auth Providers 콘솔로 이전
KAKAO_CLIENT_SECRET=
KAKAO_REDIRECT_URI=
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URI=
NAVER_OAUTH_CLIENT_ID=
NAVER_OAUTH_CLIENT_SECRET=
NAVER_OAUTH_REDIRECT_URI=
OAUTH_STATE_REDIS_URL=              # Redis 자체는 잔존 (채팅·세션). state store 키 prefix 만 폐기.
OAUTH_STATE_TTL_SECONDS=
AUTH_JWT_SECRET=                    # → Supabase JWT 검증으로 대체
AUTH_JWT_ALG=
AUTH_JWT_ACCESS_TTL_SECONDS=        # → Supabase Project Settings 가 정본
AUTH_JWT_REFRESH_TTL_SECONDS=
ANON_SESSION_HEADER=                # → Supabase JWT 의 sub/role 이 대체
ANON_SESSION_TTL_DAYS=
FRONTEND_AUTH_SUCCESS_URL=          # → Supabase redirect URL 로 일원화
FRONTEND_AUTH_FAILURE_URL=
```

> **시크릿 정책 준수.** 실제 Supabase URL / anon key / service role / DB password 는 본 ADR 어디에도 적지 않는다. 사용자가 §7 의 콘솔 작업으로 발급한 뒤 `.env` 또는 운영 시크릿 매니저로 주입한다.

### 2.4 Identity Linking 정책 (ADR-0003 §2.3 supersede 후보 — CEO 결정 필요)

**기존 정본 (ADR-0003 §2.3 + AGENTS.md §4.7 #9).**

> 같은 `provider_email` 이 카카오/구글/네이버에서 각각 가입되어도 별개 user 로 둔다. 이메일 매칭으로 자동 linking 하지 않는다. … 자동 병합은 단일 provider 탈취가 모든 provider 의 데이터로 권한 상승되는 벡터.

**본 ADR 제안 (Proposed).** 두 가지 옵션을 CEO 결정에 회부한다 (§7 미해결).

| 옵션 | 정책 | Supabase 설정 (Authentication → Settings → Identity Linking) | 잔여 리스크 |
|---|---|---|---|
| **A — Automatic 허용 (CMP-573 본문 발의)** | 동일 검증된(`verified=true`) 이메일이면 두 번째 provider 가입을 같은 `auth.users.id` 에 자동 linking. | `Allow account linking` = **on (automatic)**. | 단일 provider 탈취 시 다른 provider 자격으로 같은 데이터 노출. CEO 정책 변경에 해당. **AGENTS.md §4.7 #9 supersede 필요.** |
| **B — Manual only (ADR-0003 정책 보존)** | 자동 linking 안 함. 사용자가 우리 측 “계정 통합” 흐름을 명시 호출해야만 `supabase.auth.linkIdentity()` 가 실행되어 row 추가. | `Allow account linking` = **manual only**. | Supabase 채택 이득 일부 상쇄(가입 마찰 ↑). 다만 ADR-0003 탈취 벡터 분석을 보존. |

> **CTO 권고**: 결정 보류. CEO 가 §7 의 미해결 결정에 답해야 본 ADR 이 Accepted 될 수 있다. 본 ADR 본문은 두 옵션 모두 구현 가능하도록 §2.5·§6 의 자식 이슈 형상을 유지한다.

### 2.5 OAuth Provider 매핑

| Provider | Supabase 채택 방식 | 콘솔 작업 책임 |
|---|---|---|
| **Google** | Supabase built-in provider. `Authentication → Providers → Google` 에 OAuth client id/secret 등록. | 사용자 — Google Cloud Console 에서 OAuth client 생성 + redirect URI 에 Supabase callback (`https://<project-ref>.supabase.co/auth/v1/callback`) 등록. |
| **Kakao** | Supabase built-in provider. `Authentication → Providers → Kakao` 에 REST API key + client secret 등록. | 사용자 — Kakao Developers 콘솔에서 앱 생성 + redirect URI 등록 + Kakao Sync 약관 노출 설정. |
| **Naver** | **Supabase Custom OAuth/OIDC provider — PoC 필요.** Naver 는 built-in 미지원. Supabase Custom OAuth (or Auth Hooks) 로 우회. | 사용자 — Naver Developers 콘솔에서 앱 생성 + redirect URI 등록. CTO/Backend Lead — PoC 후속 이슈 (§6 #5). |

**PoC 성공 기준 (Naver).**
- Supabase Custom OAuth provider 로 Naver authorize → callback → `auth.identities` row 생성까지 정상 동작.
- `auth.users.email` 이 Naver userinfo 의 검증된 이메일을 정확히 받는다.
- 우리 측 `public.terms_consents (source='internal_signup')` 가 콜백 직후 트랜잭션 정합으로 insert 된다.

**PoC 실패 시 fallback.** Naver 만 자체 OAuth 코드 (ADR-0003 §2.2 의 `/auth/{provider}/start` + `/auth/callback/{provider}`) 패턴을 유지하고, Naver 가입 row 만 우리 API 가 `auth.admin.createUser()` 로 Supabase 에 upsert. 이 경우 본 ADR 의 §2.3 흐름은 Google/Kakao 에만 적용된다.

---

## 3. 대안과 기각 사유

| 대안 | 기각 사유 |
|---|---|
| **현 스택 유지 (ADR-0001 + ADR-0003)** | 자체 OAuth 콜백·state·refresh·linking·anon claim 코드 운영 부담. ADR-0003 트랙 B/C/D 미완 시점이 전환 매몰 비용 최저. |
| **Neon + Auth0 / Clerk** | 한국 provider (Naver/Kakao) 지원 약함. 비용 곡선이 Supabase 보다 가파름. DB 와 Auth 가 다른 사업자라 RLS 활용 어려움. |
| **Firebase Auth + Neon Postgres** | Google 의존 강함. PostgreSQL 미사용 → 우리 도메인 모델과 SQL JOIN 불가. |
| **Supabase Self-hosted** | 단일 인스턴스 docker-compose 와 정합하나, 운영 부담이 managed 대비 ↑. MVP 단계에서 이득 부족. 본 ADR 채택 시 후속 ADR 로 검토 가능. |
| **Cloudflare D1 + Cloudflare Workers OAuth** | PostgreSQL 미사용. AI 파이프라인의 `boto3` / Alembic / pgvector 와 불호환. |
| **AWS Cognito + Neon** | Cognito 의 한국 provider 지원·UX 부담 + 비용. Supabase 대비 보드 가시성 ↓. |

---

## 4. 구현 노트 (Accepted 시 자식 이슈 형상)

### 4.1 마이그레이션 패턴

- **로컬 / CI / preview**: Supabase CLI (`supabase start` 로 로컬 stack, `supabase db push` 로 마이그레이션).
- **dev / staging / production**: Supabase Dashboard 의 Branching (preview branch) + GitHub Actions 통합 (Neon `neon-pr-branch.yml` 의 1:1 대응 워크플로우 신설).
- **마이그레이션 도구 SSOT**: 본 ADR Accepted 시점 결정 — **Alembic 유지** 또는 **Supabase CLI 단독**. CTO 권고: Alembic 유지 (Python 측 모델·SQLAlchemy 정합), Supabase CLI 는 `auth` 스키마와 RLS 정책만 관리.

### 4.2 RLS 정책

Supabase 채택의 최대 이득 중 하나는 RLS 로 도메인 권한을 DB 레벨에서 잠그는 것이다.

```sql
-- 예시: 익명 사용자도 자기가 만든 도면만 본다.
ALTER TABLE public.uploads ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users can read own uploads" ON public.uploads
  FOR SELECT
  USING (auth.uid() = user_id);
```

> 본 ADR 은 RLS 정책 자체를 봉인하지 않는다. 도메인 모듈별 RLS 정책은 후속 자식 이슈 (§6 #4) 의 모델 PR 에서 정의·리뷰.

### 4.3 우리 측 API ↔ Supabase JWT 검증

- FastAPI 의존성 (`Depends(get_current_user)`) 가 `Authorization: Bearer <Supabase JWT>` 를 받아 `SUPABASE_JWT_SECRET` 또는 Supabase JWKS 로 검증. `auth.users.id` 를 컨텍스트에 주입.
- 자체 JWT 발급 코드 제거 (ADR-0003 §2.2 의 access/refresh TTL 환경변수 폐기와 연동).
- Refresh 는 SDK 측 자동 처리. 서버 측 블랙리스트 불필요.

### 4.4 Refresh Token TTL — 보안 런북 정합

Supabase Project Settings → JWT Expiry (default access token 1h, refresh token 인덱스는 Settings 의 “Refresh Token Reuse Detection” + 토큰 회전 정책) 를 `docs/runbooks/security-policy.md` POL-AUTH-002 (refresh 7일) 와 정합하도록 설정한다.

- 본 ADR Accepted 시 보안 런북 POL-AUTH-002 의 “환경변수 정본” 줄은 `apps/api/.env.example::AUTH_JWT_REFRESH_TTL_SECONDS` → **`Supabase Dashboard → Authentication → Settings → JWT Expiry`** 로 정정 필요. `docs/명세서-모순.md` CFLT-006 의 “Resolved (7일/604800s)” 결론은 유지하되 SSOT 위치만 이동.

### 4.5 Auth Hooks PoC (Naver Custom OAuth + Kakao Sync source 분리)

본 ADR Accepted 시 가장 먼저 풀어야 할 기술 리스크.

- Naver Custom OAuth/OIDC 가 Supabase Dashboard 에서 활성화되는 케이스 검증.
- Kakao 콜백 직후 `before_user_created` 또는 `after_user_created` Auth Hook 으로 `public.terms_consents (source='kakao_sync')` 자동 insert 가 트랜잭션 정합으로 가능한지 검증.
- PoC 실패 시 §2.5 fallback 또는 본 ADR 의 Accepted 조건 재조정.

---

## 5. 결과 (Consequences)

### 5.1 긍정적

- 자체 OAuth 콜백 / refresh / state store / anon claim 코드 ~수백 LOC 제거.
- Supabase Dashboard 의 user 검색·정지·삭제 UI 가 운영팀의 별도 관리자 화면 부담을 ↓.
- RLS 로 도메인 권한이 DB 레벨에서 잠겨, 우리 API 의 권한 누락 사고 표면 ↓.
- 한국 리전(Seoul) 옵션 활용 시 사용자 PII 의 잔존 위치가 명확해짐 (§7 사용자 확정 필요).
- ADR-0003 의 데이터 모델 PR (트랙 B) 이 아직 미머지인 시점이라 전환 매몰 비용 최저.

### 5.2 부정적 / 비용

- **외부 사업자 의존 ↑** — Supabase 사고/요금/SLA 변경이 우리 인증 가용성에 직결.
- **CEO 정책 변경** — ADR-0003 §2.3 자동 병합 금지가 옵션 A 시 supersede. 단일 provider 탈취 → 모든 provider 데이터 노출 벡터가 재등장.
- **마이그레이션 도구 SSOT 재정의** — Alembic 유지/폐기 결정 + 기존 마이그레이션의 Supabase `auth` 스키마 호환 검증 부담.
- **lock-in 거리** — `auth.users` + RLS 패턴은 Supabase 의존. 빠질 경로(self-hosted) 가 있긴 하나 운영 부담 ↑.
- **보안 런북 POL-AUTH-002 SSOT 이동** — refresh TTL 정본이 환경변수에서 Supabase Dashboard 로 이동. 회전·감사 절차 갱신 필요.

### 5.3 후속 (Accepted 시 자식 이슈)

| # | 자식 이슈 (제목 패턴) | 영향 범위 | 트리거 |
|---|---|---|---|
| 1 | `[SUPABASE][ADR-FOLLOWUP] AGENTS.md §4.7 + docs/명세서-모순.md 갱신 (CFLT-001/005 supersede 정렬 + CFLT-007 신설)` | DOCS | 본 ADR Accepted |
| 2 | `[SUPABASE][INFRA] Supabase 프로젝트 생성 + GitHub Actions preview branching + .env.example 변수 봉인` | DEVOPS / INFRA | 본 ADR Accepted + §7 사용자 결정 |
| 3 | `[SUPABASE][AUTH][MODEL] public.users / public.terms_consents 재정의 + auth.users FK + Alembic vs Supabase CLI 결정` | DB / API | 본 ADR Accepted |
| 4 | `[SUPABASE][AUTH][HANDLER] FastAPI Supabase JWT 의존성 + RLS 정책 초안 + ADR-0003 §2.2 라우트 폐기` | API | 자식 #3 머지 후 |
| 5 | `[SUPABASE][AUTH][POC] Naver Custom OAuth/OIDC provider PoC + Kakao Sync source 분리 Auth Hook` | API / DEVOPS | 본 ADR Accepted |
| 6 | `[SUPABASE][WEB] @supabase/supabase-js 클라이언트 + signInAnonymously + linkIdentity UX + 약관 모달` | WEB | 자식 #4 머지 후 |
| 7 | `[SUPABASE][SPEC] 명세서 4종 다음 리비전 — Supabase Auth + identity linking 반영 (CFLT-001/003/004/005 재정렬)` | DOCS | 자식 #3·#4 머지 후 |
| 8 | `[SUPABASE][OPS] R2 유지 결정 명문화 + Supabase Storage 채택 가부 별도 ADR 또는 후속 이슈로 큐잉` | OPS | 본 ADR Accepted |
| 9 | `[SUPABASE][SEC] 보안 런북 POL-AUTH-002 정본 SSOT 이동 + refresh TTL Dashboard 운영 절차` | SEC / DOCS | 자식 #2 머지 후 |

> 옵션 A (identity linking automatic) 가 선택되면 자식 #1 에 ADR-0003 §2.3 supersede + AGENTS.md §4.7 #9 변경이 포함된다. 옵션 B 가 선택되면 자식 #1 의 §2.3 supersede 는 빠진다.

---

## 6. Supersede 대상 목록 (정본)

본 ADR 이 Accepted 되는 시점에 다음 정본을 부분 supersede 한다. **본 ADR 이 Proposed 인 동안에는 supersede 가 발효되지 않는다.**

| 정본 위치 | 절 | supersede 범위 | 정본을 이동하는 곳 |
|---|---|---|---|
| `docs/adr/0001-stack-reevaluation.md` §4 (T3 — Neon Postgres) | 전체 | DB 호스팅을 Neon → Supabase Postgres 로 변경. branching·pooler·HNSW 패턴은 Supabase 대응으로 재정렬. | 본 ADR §2.1 + §4.1 |
| `docs/adr/0003-anon-user-and-sso.md` §2.1 (데이터 모델) | `users`, `anonymous_users`, `external_sso_accounts` 테이블 정의 | 우리 도메인은 `public.users` (auth.users FK) + `public.terms_consents` 만 남음. ENUM `external_sso_provider` 봉인 폐기. | 본 ADR §2.2 |
| `docs/adr/0003-anon-user-and-sso.md` §2.2 (OAuth 라우트 + 콜백) | 전체 | 자체 콜백 라우트 폐기, Supabase Auth + `supabase.auth.signInAnonymously` / `linkIdentity` 가 대체. | 본 ADR §2.3 |
| `docs/adr/0003-anon-user-and-sso.md` §2.3 (자동 병합 금지) | 전체 | **옵션 A 시**: identity linking automatic 허용으로 supersede. **옵션 B 시**: 정책 그대로 보존(manual linking). | 본 ADR §2.4 + §7 결정 |
| `docs/adr/0003-anon-user-and-sso.md` §봉인표 (Refresh Token TTL 등) | refresh TTL · OAuth start route · state store · localStorage 키 · 헤더 이름 | Supabase 정본으로 일괄 이동. 환경변수 폐기 목록은 본 ADR §2.3 환경변수 표. | 본 ADR §2.3 + §4.4 |
| `AGENTS.md §4.7` (사용자 식별 정책) | #1~#10 중 #2 (전환 시점 OAuth) 는 유지, #3 (비밀번호 금지) 는 유지, **#4 (provider ENUM 봉인)**, **#5 (Kakao Sync source 분리 — Auth Hook 으로 자동화 가능 여부)**, **#7 (localStorage 식별자)**, **#9 (자동 병합 금지)**, **#10 (Redis state store)** 가 본 ADR 의 영향권. | 자식 이슈 §5.3 #1 에서 §4.7 본문 직접 갱신. | 본 ADR 봉인표 |
| `docs/명세서-모순.md` CFLT-001 (로그인 필수 vs 사전검토 허용) | Status | 본 ADR 채택 시점에 CFLT-001 의 “새 정본” 줄이 ADR-0003 + ADR-0004 로 갱신. | 자식 이슈 §5.3 #1 |
| `docs/명세서-모순.md` CFLT-003 (ENUM vs VARCHAR) | Status | ENUM 봉인 폐기로 row 가 Resolved → Reframed (Supabase Auth 가 provider 식별 정본). | 자식 이슈 §5.3 #1 |
| `docs/명세서-모순.md` CFLT-005 (localStorage 식별자) | Status | Supabase Anonymous Sign-In 의 JWT 가 localStorage 키를 대체. row 가 Resolved → Reframed. | 자식 이슈 §5.3 #1 |
| `docs/명세서-모순.md` (신규 CFLT-007) | — | **자동 병합 금지 정책의 supersede 여부** 를 추적할 새 row 를 자식 이슈에서 추가. | 자식 이슈 §5.3 #1 |
| `docs/runbooks/security-policy.md` POL-AUTH-002 | 환경변수 정본 위치 | `apps/api/.env.example::AUTH_JWT_REFRESH_TTL_SECONDS` → `Supabase Dashboard → Authentication → Settings → JWT Expiry`. | 자식 이슈 §5.3 #9 |
| `.github/workflows/neon-pr-branch.yml`, `.github/workflows/ci.yml` (`migrate-check`), `.github/workflows/deploy.yml` (`release-migrate`) | Neon 전제 | Supabase Branching 또는 Supabase CLI 기반 워크플로우로 1:1 재작성. | 자식 이슈 §5.3 #2 |

---

## 7. 미해결 — CEO 결정 + 사용자 콘솔 작업

본 ADR 이 Proposed → Accepted 되려면 다음 항목을 사용자(CEO 권한) 가 결정·이행해야 한다.

### 7.1 정책 결정 (CEO)

1. **Identity linking 정책 — 옵션 A vs B (§2.4)**
   - **옵션 A**: Automatic 허용 (CMP-573 본문 발의). ADR-0003 §2.3 + AGENTS.md §4.7 #9 supersede.
   - **옵션 B**: Manual only (ADR-0003 정책 보존).
   - **CTO 권고**: 보안과 가입 마찰의 트레이드오프. 본 ADR 은 양자택일을 강제하지 않고 두 옵션의 구현 형상을 모두 §2.5·§6 에 보존.

2. **데이터 주권 / 리전**
   - Supabase 프로젝트 리전 — Seoul (`ap-northeast-2`) vs Singapore (`ap-southeast-1`).
   - CEO 권고 — Seoul (한국 사용자 PII 잔존, 약관·법무 측면 단순).

3. **Storage 전환 시점**
   - 본 ADR 은 R2 유지. Supabase Storage 채택은 별도 ADR.
   - CEO 결정 — R2 유지 vs 향후 Supabase Storage 검토 큐잉.

### 7.2 콘솔 작업 (사용자)

본 ADR 은 어떤 시크릿도 코드/문서/이슈/PR 본문에 적지 않는다. 사용자가 다음 콘솔 작업을 직접 수행한다.

1. **Supabase 프로젝트 생성** — 조직/리전(§7.1.2) 선택, 프로젝트 ref 발급.
2. **`SUPABASE_URL` / `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_JWT_SECRET` / `SUPABASE_PROJECT_REF` / Supabase Postgres `DATABASE_URL`** 발급 → 운영 시크릿 매니저 (or `.env`). **본 ADR / 자식 이슈 / PR 본문에는 변수명만 둔다.**
3. **Authentication → Providers → Google / Kakao 활성화** — 각 사 콘솔에서 client id/secret 발급, Supabase callback URL (`https://<project-ref>.supabase.co/auth/v1/callback`) 등록.
4. **Authentication → Providers → Naver (Custom OAuth)** — PoC (§4.5). 실패 시 fallback (§2.5).
5. **Authentication → Settings → Identity Linking** — §7.1.1 결정 옵션 적용.
6. **Authentication → Settings → JWT Expiry** — refresh 7일 (POL-AUTH-002) 정렬.
7. **GitHub Actions secrets / variables** 갱신 — `NEON_*` 시리즈를 `SUPABASE_*` 로 1:1 교체.

> 위 항목 중 어느 하나라도 미정이면 본 ADR 은 Accepted 될 수 없다. 본 ADR 을 들고 구현을 시작하는 자식 이슈 (§5.3 #2~#9) 도 동일하게 Accepted 를 의존.

---

## 8. 봉인 표 (Proposed)

| 키 | 값 | 비고 |
|---|---|---|
| Supabase 채택 표면 | DB + Auth | Realtime / Edge Functions / Storage 는 보류 (§2.1) |
| 인증 SSOT | `auth.users` | `public.users` 는 프로필 테이블 (FK only) |
| 비회원 사전검토 | `supabase.auth.signInAnonymously()` + `is_anonymous` flag | `anonymous_users` 테이블 폐기 |
| 자체 OAuth 콜백 | 폐기 | `supabase.auth.signInWithOAuth` / `linkIdentity` 가 대체 |
| Identity linking | **옵션 A 또는 B — §7.1.1 결정 대기** | 본 ADR 채택 옵션이 정해지면 본 줄 갱신 |
| OAuth provider 콘솔 | Supabase Dashboard | 사용자 콘솔 작업 (§7.2.3·4) |
| OAuth state store | Supabase | Redis `oauth_state:*` / `pending_signup:*` 폐기. Redis 자체는 채팅·세션 캐시로 잔존. |
| Refresh Token TTL | Supabase Project Settings (POL-AUTH-002 정합 = 7일) | 환경변수 정본 폐기 |
| 약관 동의 모델 | `public.terms_consents` 유지, `user_id` → `auth.users(id)` | source 분리 보존 |
| 객체 스토리지 | Cloudflare R2 유지 | ADR-0001 §6 보존 |
| AI / LLM | SAM2 + OpenAI + LangChain 유지 | ADR-0001 §7 보존 |
| 앱 배포 | Lightsail 그대로 | Supabase 는 FastAPI / AI 서버 호스팅처 아님 |
| 마이그레이션 도구 | Alembic 유지 + Supabase CLI 로 `auth`·RLS 정책 관리 (잠정) | 자식 이슈 §5.3 #3 에서 최종 결정 |
| 한국 리전 | Seoul (`ap-northeast-2`) — 사용자 결정 대기 (§7.1.2) | — |

---

## 9. 변경 절차

- 본 ADR 은 CEO 결정 (§7.1) + 사용자 콘솔 작업 (§7.2) 이 모두 완료된 시점에만 Accepted 로 승급된다. 그 전까지 어떤 구현 PR 도 본 ADR 을 근거로 들 수 없다.
- 본 ADR 의 옵션 A/B 결정 (§2.4) 은 ADR 본문 자체에 흔적을 남겨야 한다 (선택된 옵션을 §0 TL;DR 과 §8 봉인 표에 반영).
- Naver Custom OAuth PoC (§4.5) 가 실패하면 §2.5 fallback 으로 ADR 본문을 보강하거나 본 ADR 을 supersede 하는 새 ADR 을 발행한다.
- ADR-0001 §4 (T3 Neon) supersede 는 본 ADR 의 정본 채택 시 ADR-0001 상단에 `supersededBy: ADR-0004 §2.1 (T3 만)` 짧은 줄을 추가하는 방식으로만 흔적을 남긴다 (ADR-0001 본문 직접 재작성 금지).
- ADR-0003 의 부분 supersede 도 마찬가지로 ADR-0003 상단에 `partiallySupersededBy: ADR-0004 §2.2·§2.3·(§2.4 옵션 A 시 §2.3)` 만 추가하고 본문은 보존.

---

## 10. 결정 트레일

| 시각 | 행위자 | 행위 |
|---|---|---|
| 2026-05-29 | 사용자 (CEO 권한 행사) | CMP-573 본문에서 Neon → Supabase 전환 발의. |
| 2026-05-29 | CTO (`4edca504-...`, CMP-573) | 본 ADR-0004 `Proposed` 초안 발행. ADR-0003 부분 supersede 범위 + 자동 병합 정책 옵션 A/B 회부 + Naver PoC 큐잉. |
| _pending_ | CEO | §7.1 정책 결정. |
| _pending_ | 사용자 | §7.2 콘솔 작업 + 시크릿 발급. |
| _pending_ | CTO | 위 두 단계 완료 시 본 ADR 을 `Accepted` 로 승급. 자식 이슈 §5.3 #1~#9 일괄 발행. |

— 끝 —

# ADR 0003 — 익명 사용자 + 소셜 SSO 간편가입 모델

- 상태: **Accepted (2026-05-29)** — CEO 정책 (CMP-557) 확정 후 본 트랙 A (CMP-558) 가 문서 정본을 발행.
- 제안자: Backend Lead (`1e359a75`)
- 승인 권자: CEO (CMP-557 본문에서 정책 결정), CTO 검토
- 인계 출처: CMP-557 본문 (CEO 정책 결정) · `docs/명세서/02·03·04` (기존 명세서 가정)
- 관련 이슈: **CMP-557** (정책 분할 모이슈) · **CMP-558** (트랙 A — 본 ADR + AGENTS.md + .env 초안) · CMP-557-B/C/D (각 모델·핸들러·UX 트랙)
- 슈퍼시드: 없음. 기존 명세서 4종의 “소셜 OAuth 로그인 필수 / 비회원 사전검토 불가” 가정을 본 ADR 이 supersede (모순 트래킹: `docs/명세서-모순.md` CFLT-001).
- 강한 제약 (변경 금지 — ADR-0001 / ADR-0002 / CEO 브리프 봉인 상속):
  - 단일 인스턴스 + `docker-compose`. 외부 의존 (Neon Postgres / Redis 컨테이너 / Cloudflare R2 / OpenAI) 그대로.
  - 결과 화면 법적 고지 (`AGENTS.md §4.6`) 누락 금지.

---

## 0. 결정 요약 (TL;DR)

| 항목 | 결정 |
|---|---|
| **진입 모델** | **비회원 사전검토 허용** — 도면 업로드·마스킹·1차 AI 판단·리포트 미리보기는 익명 세션으로 진행. |
| **전환 시점 인증** | **OAuth 간편가입 의무** — (a) 상담 전환, (b) 리드 생성, (c) 리포트 저장/공유 시점에서만 게이트. |
| **OAuth provider** | **`google` · `naver` · `kakao` 3종 고정** — Postgres ENUM `external_sso_provider` 봉인. |
| **자체 비밀번호** | **영구 금지** — `users` 등 어떤 인증 테이블에도 password/hash/salt 컬럼 없음. 모델 메타데이터 테스트로 가드. |
| **데이터 모델** | `anonymous_users` + `users` + `external_sso_accounts` + `terms_consents` 4 테이블 분리. |
| **OAuth state store** | **Redis** (≤10분 TTL). 메모리 단일 인스턴스 정합. |
| **익명 식별자 보관소** | 브라우저 `localStorage.jippin_anonymous_user_id` (서버 발급 UUID v4). |
| **계정 자동 병합** | **금지.** 동일 이메일 + 다른 provider 는 별개 user 로 유지. 사용자 명시 흐름이 있어야 통합. |
| **Kakao Sync 약관** | **별도 source 저장** — `terms_consents.source = 'kakao_sync'`. 내부 약관 화면은 Google/Naver 만 통과. |
| **약관 동의 화면** | Google/Naver 는 내부 약관 동의 화면 강제. Kakao 는 Kakao 자체 화면을 신뢰하고 source 만 기록. |

---

## 1. 결정 컨텍스트

### 1.1 무엇을 결정해야 하는가

기존 명세서 4종 (`docs/명세서/`) 은 **“사용자는 카카오·구글·네이버 계정으로 로그인해야 서비스를 이용할 수 있다”** 를 전제로 한다 (기능명세서 `AUTH-001`, 기술명세서 §7.1, SDD §AUTH 책임). 이 전제 위에서 INPUT/CHAT/REPORT 가 모두 `user_id` 키로 설계되어 있다.

그러나 CEO 가 CMP-557 본문에서 **비회원 사전검토 허용 + 전환 시점 간편가입 의무** 로 정책을 명문화했다. 명세서 4종을 직접 리비전하기 전에, 본 ADR 이 정책을 봉인 정본으로 발행하고 후속 트랙(B/C/D)이 데이터 모델·핸들러·UX 를 구현한다.

### 1.2 평가 기준

1. **사용자 마찰 최소화** — 도면 1장 올려보고 결과를 보고 싶은 신규 사용자를 가입 게이트로 막지 않는다 (B2C 무료 사전검토 모델 정합).
2. **PII 노출 최소화** — 사전검토 단계에서는 OAuth 식별 정보를 수집하지 않는다.
3. **상담/리드 품질 보호** — 사업자에게 전달되는 리드는 식별 가능한 user 이어야 한다.
4. **공격 표면 최소화** — 자체 비밀번호 보관 = 자체 비밀번호 사고. 영구 금지.
5. **계정 탈취 방어** — 동일 이메일 자동 병합은 단일 provider 탈취가 계정 전체 탈취로 이어지는 벡터. 금지.

### 1.3 외부 제약

- ADR-0001 §4 — Neon Postgres 봉인. ENUM·외래키 자유롭게 사용 가능.
- ADR-0001 §5 — Redis 7.4-alpine 컨테이너. OAuth state store 로 사용.
- ADR-0001 §6 — Cloudflare R2. 익명 세션의 도면도 R2 에 저장하며, `anonymous_users.id` 로 경로 네임스페이스를 분리한다.
- AGENTS.md §4.4 시크릿 정책 — 본 ADR 이 정의하는 환경변수는 이름만 `.env.example` 에 둔다.

---

## 2. 결정

### 2.1 데이터 모델 (정본)

> **생성 순서 주의 (PostgreSQL).** `anonymous_users.converted_user_id` 는 `users(id)` 를 참조하므로 `users` 를 먼저 만든 뒤 `anonymous_users` 를 만든다. Alembic 작업자는 본 순서를 그대로 따른다 (반대 순서로 적용하면 FK 검증에서 실패).
>
> **타입 선택.** `email` / `provider_email` 은 `TEXT NULL` 을 사용한다. CMP-557 본문의 `email TEXT NULL` 과 정합하고, `citext` extension 의존을 피한다. 대소문자 무시 매칭이 필요한 쿼리는 `LOWER(email)` 의 functional index 로 처리한다 (필요해질 때 트랙 B 모델 PR 에서 추가). `CITEXT` 로 회귀하려면 마이그레이션에 `CREATE EXTENSION IF NOT EXISTS citext;` 를 명시하는 새 ADR 이 필요하다.

```sql
-- 1) Provider ENUM — 봉인. 신규 provider 추가 시 새 ADR + 마이그레이션.
CREATE TYPE external_sso_provider AS ENUM ('google', 'naver', 'kakao');

-- 2) 사용자 — password 컬럼 금지. email 은 TEXT NULL (provider 가
--    이메일을 제공하지 않을 수 있음. citext 의존 회피).
CREATE TABLE users (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email           TEXT NULL,
  display_name    TEXT,
  status          TEXT NOT NULL DEFAULT 'active', -- active | suspended | deleted
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_login_at   TIMESTAMPTZ
  -- 의도적으로 password/hash/salt 컬럼 없음. 모델 메타데이터 테스트가 가드.
);

-- 3) 익명 세션 — 비회원 사전검토 컨텍스트. users 가 먼저 존재해야 한다.
CREATE TABLE anonymous_users (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  ip_hash         BYTEA,         -- HMAC. 원본 IP 미저장.
  ua_hash         BYTEA,         -- User-Agent 해시.
  converted_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
  converted_at    TIMESTAMPTZ NULL
);

-- 4) 외부 SSO 계정 — (provider, provider_subject) 가 자연 PK.
--
--   - PRIMARY KEY (provider, provider_subject) : provider 측 subject 중복 차단.
--   - UNIQUE (user_id, provider) : 한 user 는 같은 provider 를 두 번 연결할 수
--     없다 (Kakao 1회, Google 1회, Naver 1회 max). 다른 provider 추가 연결은
--     허용되며 사용자 명시 “계정 통합” 흐름을 거쳐야 한다 (§2.3).
CREATE TABLE external_sso_accounts (
  user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider         external_sso_provider NOT NULL,
  provider_subject TEXT NOT NULL,
  provider_email   TEXT,
  linked_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (provider, provider_subject),
  UNIQUE (user_id, provider)
);

-- 5) 약관 동의 — source 분리 저장.
CREATE TABLE terms_consents (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  term_id     TEXT NOT NULL,     -- e.g. tos_v1, privacy_v2, marketing_optin
  version     TEXT NOT NULL,
  source      TEXT NOT NULL,     -- 'internal_signup' | 'kakao_sync'
  agreed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

> 실제 마이그레이션은 CMP-557 트랙 B (모델 PR) 에서 Alembic 으로 작성한다. 본 ADR 은 형상만 봉인한다.

### 2.2 OAuth 라우트 + 콜백 흐름 (정본)

**정본 라우트.**

- `POST /auth/{provider}/start` — OAuth 시작. `{provider}` ∈ `{google, naver, kakao}`. 요청 헤더 `x-jippin-anon-id: <uuid>` 로 익명 세션 식별자를 받는다. 응답: `{"authorize_url": "<provider authorize URL>"}` (JSON). **GET 으로 동작하지 않는다.** 이유: top-level `<a href>` / `window.location` 네비게이션은 `localStorage` 값을 읽지 않고 `x-jippin-anon-id` 같은 커스텀 헤더도 보내지 않기 때문에, anon → user claim 을 OAuth state 에 묶을 수 없다. **클라이언트(Next.js) 가 `fetch` 또는 axios 로 `POST` 한 뒤 `window.location.assign(authorize_url)` 로 이동한다.**
- `GET /auth/callback/{provider}` — provider 가 Authorization Code 와 함께 리다이렉트해 오는 콜백 엔드포인트. provider 측 등록 redirect URI 와 정확히 일치해야 하므로 GET 유지.
- `POST /auth/refresh` — access token 갱신.
- `POST /auth/logout` — refresh token 무효화 (Redis 블랙리스트).

> Codex auto-review #6 (CMP-558) 대응: `/auth/{provider}` 라우트는 사용하지 않는다. 후속 구현자는 `/auth/{provider}/start` 만 만든다.

**콜백 흐름.**

```
[비회원]                                            [Provider]
  │  1) 익명 진입 → 서버가 anonymous_users.id (UUID v4) 발급
  │     브라우저 localStorage.jippin_anonymous_user_id 저장
  │  2) (전환 시점) 클라이언트가 POST /auth/{provider}/start
  │     헤더: x-jippin-anon-id: <uuid>
  │     서버: state/nonce/code_verifier 발급
  │            Redis 에 oauth_state:<state> = {anon_id, provider, ...}
  │                                                    (TTL ≤10분)
  │     응답: { "authorize_url": "<provider authorize URL>" }
  │  3) 클라이언트: window.location.assign(authorize_url)       ───▶
  │                                                          [User consents]
  │  4) GET /auth/callback/{provider}?code=...&state=...   ◀─
  │     서버: Redis 에서 oauth_state:<state> 검증·소비, code 교환
  │  5) provider=kakao :
  │       - Kakao Sync 약관 동의 결과를 함께 받아 단일 트랜잭션에서
  │         users upsert + external_sso_accounts upsert
  │         + terms_consents(source='kakao_sync') insert
  │         + anonymous_users claim 갱신.
  │       - 내부 약관 화면은 생략 (Kakao 가 표시 책임).
  │     provider in (google, naver) :
  │       - provider userinfo(subject, email 등) + anon_id + state 키를
  │         pending_signup:<token> 으로 Redis 에 짧은 TTL(≤10분)로 보관.
  │       - 내부 약관 동의 화면으로 리다이렉트 — 이 시점에는 users 미생성.
  │       - 사용자가 약관에 동의하면, 단일 트랜잭션에서
  │         users upsert + external_sso_accounts upsert
  │         + terms_consents(source='internal_signup') insert
  │         + anonymous_users.converted_user_id / converted_at 갱신.
  │         (terms_consents.user_id NOT NULL 정합. 부분 커밋 금지.)
  │       - 사용자가 약관을 거부하면 pending_signup 폐기, users 미생성,
  │         익명 세션 유지. TERMS_DECLINED 응답.
  │  6) JWT 발급 → 서버가 FRONTEND_AUTH_SUCCESS_URL 로 302.
  │     실패 시 FRONTEND_AUTH_FAILURE_URL 로 302 (사유는 query string).
```

> **API 가 redirect 의 owner.** 콜백은 API 가 처리하고 JWT 발급 후 프론트로 redirect 하므로, `FRONTEND_AUTH_SUCCESS_URL` / `FRONTEND_AUTH_FAILURE_URL` 정본은 **`apps/api/.env.example`** 에 둔다. `apps/web/.env.example` 의 `NEXT_PUBLIC_FRONTEND_AUTH_SUCCESS_URL` / `NEXT_PUBLIC_FRONTEND_AUTH_FAILURE_URL` 은 SPA 측 라우팅 표시용 보조 표기이며 값이 두 곳에서 어긋나면 API 측이 정본이다.

실패·예외 코드 (SDD §AUTH 와 정합):

- `OAUTH_FAILED` — provider 응답 실패.
- `OAUTH_STATE_INVALID` — Redis state 만료/불일치.
- `TERMS_DECLINED` — 내부 약관 미동의 (가입 미완료, 익명 세션 유지).
- `TOKEN_INVALID` / `TOKEN_EXPIRED` / `REFRESH_EXPIRED` — JWT 수명주기.

### 2.3 자동 병합 금지

같은 `provider_email` 이 카카오/구글/네이버에서 각각 가입되어도 별개 user 로 둔다. 이메일 매칭으로 자동 linking 하지 않는다. 사용자가 “계정 통합” 흐름을 명시적으로 호출해야만 `external_sso_accounts` 에 두 번째 provider row 가 같은 `user_id` 로 추가된다.

> **근거.** 자동 병합은 단일 provider 탈취가 모든 provider 의 데이터로 권한 상승되는 벡터다. CEO 정책이 명시적으로 금지했다.

### 2.4 비밀번호 컬럼 영구 금지 — 가드

- 모델 메타데이터 단위 테스트 (`apps/api/tests/auth/test_no_password_columns.py`) 가 다음을 회귀로 잠근다:
  - 어떤 SQLAlchemy 모델에도 `password`, `password_hash`, `passwd`, `salt`, `secret` 컬럼이 존재하지 않음.
  - Alembic autogenerated diff 에 위 컬럼이 등장하면 CI 실패.
- 위 테스트의 정본 구현은 CMP-557 트랙 B 모델 PR 에 포함.

---

## 3. 대안과 기각 사유

| 대안 | 기각 사유 |
|---|---|
| **로그인 필수 유지 (기존 명세서)** | CEO 정책 결정. 비회원 사전검토 게이트가 전환율을 떨어뜨린다는 가설. |
| **자체 비밀번호 + OAuth 혼합** | 비밀번호 보관 = 비밀번호 사고. 운영 부담 (회전·해시 정책·리커버리). MVP B2C 무료 모델에서 이득 없음. |
| **OAuth provider 4종 이상** (Apple, GitHub, Facebook 등) | 한국 사용자 도달율·약관·UX 부담 대비 이득 부족. 새 provider 는 ADR 로 추가. |
| **provider 식별을 VARCHAR(20)** (기존 기술명세서) | 런타임 string drift 위험. ENUM 으로 봉인하면 DB 레벨 가드. |
| **동일 이메일 자동 병합** | 단일 provider 탈취 → 계정 전체 탈취 벡터. 금지. |
| **OAuth state 를 메모리/DB 에 저장** | Redis 가 이미 단일 인스턴스 정합. TTL 자동 만료가 안전. |
| **익명 식별자를 쿠키** | 쿠키는 동의·SameSite·secure 부담. `localStorage` 가 가벼움. |
| **Kakao 내부 약관 화면 중복 노출** | Kakao Sync 약관이 이미 일치 + 신뢰 가능. UX 부담만 증가. source 분리 저장으로 감사성 충족. |

---

## 4. 결과 (Consequences)

### 4.1 긍정적

- 신규 사용자의 사전검토 진입 마찰 0 (도면 1장 → 결과까지 무가입).
- 전환 시점에서만 OAuth 게이트 → 가입 완료 user 의 의도가 명확 (리드 품질 ↑).
- password 컬럼 부재 → OWASP A07 (인증 실패) 일군의 사고 표면 제거.
- ENUM provider + Redis state → DB·메모리 레벨 가드가 코드 검증보다 강함.

### 4.2 부정적 / 비용

- 익명 세션 데이터 (도면, 판단 결과) 의 만료·정리 정책이 별도로 필요 (후속 운영 런북).
- `anonymous_users` 와 `users` 두 키 체계가 공존 → INPUT/CHAT/REPORT 가 union 컨텍스트 (`actor: AnonymousActor | UserActor`) 를 처리해야 함. Architecture Lead 공통 컨트랙트 갱신 필요.
- Kakao Sync 약관 source 분리 저장은 운영팀 약관 동의 감사 절차에 한 줄 추가.
- 명세서 4종 다음 리비전 부담 (요구·기능·기술·SDD 각 1 PR 권고).

### 4.3 후속 (자식 이슈 권고)

| # | 자식 이슈 (제목 패턴) | 주 오너 | 트리거 |
|---|---|---|---|
| 1 | `[AUTH][MODEL] anonymous_users / users / external_sso_accounts / terms_consents 모델 + Alembic + password 컬럼 가드 테스트` | Python Backend Engineer | 본 ADR Accepted |
| 2 | `[AUTH][HANDLER] OAuth Authorize / Callback / 약관 동의 / JWT 발급 라우터 + Redis state store` | Python Backend Engineer | 본 ADR Accepted |
| 3 | `[AUTH][WEB] 익명 세션 식별자 / 전환 시점 인터셉트 / 내부 약관 동의 UX` | React Engineer | 본 ADR Accepted |
| 4 | `[SPEC] 명세서 4종 다음 리비전 — AUTH 정책 정렬 (CFLT-001/003/004/005 해소)` | Architecture Lead | 본 ADR Accepted |
| 5 | `[OPS] 익명 세션 데이터 만료·정리 런북 (anonymous_users + R2 prefix 청소)` | Cloud Engineer | 트랙 1·3 머지 후 |

---

## 5. 봉인 표

| 키 | 값 | 비고 |
|---|---|---|
| `external_sso_provider` (PG ENUM) | `google | naver | kakao` | 신규 provider 추가 = 새 ADR + 마이그레이션 |
| `users.password*` | 컬럼 없음 | 모델 메타데이터 테스트 가드 |
| `users.email` / `external_sso_accounts.provider_email` | `TEXT NULL` | citext 의존 회피, CMP-557 정합. 회귀 시 새 ADR + `CREATE EXTENSION` |
| OAuth start route | `POST /auth/{provider}/start` | 클라이언트가 `x-jippin-anon-id` 헤더와 함께 호출, 응답 `authorize_url` 로 `window.location.assign` |
| OAuth callback route | `GET /auth/callback/{provider}` | provider 측 redirect URI 와 정확히 일치 |
| `anonymous_users` localStorage 키 | `jippin_anonymous_user_id` | 서버 발급 UUID v4 |
| 익명 세션 전달 헤더 | `x-jippin-anon-id` | 정본 변수 = `apps/api/.env.example::ANON_SESSION_HEADER` |
| OAuth state store | Redis 컨테이너 (ADR-0001 §5) | TTL ≤10분, key prefix 분리 (`oauth_state:*`, `pending_signup:*`) |
| Refresh token TTL | 7일 (604800s) | security-policy POL-AUTH-002 정합. CFLT-006. |
| 자동 병합 | 금지 | 사용자 명시 통합 흐름만 허용 |
| Kakao 내부 약관 화면 | 생략 | source 분리 저장으로 감사 |
| Google/Naver 내부 약관 화면 | 필수 | `terms_consents.source='internal_signup'` |

---

## 6. 변경 절차

- 본 ADR 은 CEO 정책 (CMP-557) 의 구현 정본이다. 정책 자체 변경은 새 CEO 결정 + 새 ADR.
- 운영 중 발견되는 모순/예외는 `docs/명세서-모순.md` 에 우선 등록하고, 명세서 다음 리비전 또는 후속 ADR 로 해소한다.
- 모든 갱신은 gitmoji `📝 docs:` 와 PR 본문에 영향 범위 명시.

---

## 7. 결정 트레일

| 시각 | 행위자 | 행위 |
|---|---|---|
| 2026-05-XX | CEO | CMP-557 본문에서 정책 결정 (비회원 사전검토 + 전환 시점 OAuth 간편가입 + password 금지 + Kakao Sync source 분리). |
| 2026-05-29 | Backend Lead (`1e359a75`, CMP-558) | 본 ADR-0003 `Accepted` 발행 + AGENTS.md §4.7 + `docs/명세서-모순.md` CFLT-001~005 등록 + `.env.example` 변수명 초안. |
| _pending_ | Python Backend Engineer (CMP-557 트랙 B/C) | 모델·핸들러 구현. |
| _pending_ | React Engineer (CMP-557 트랙 D) | 전환 시점 인터셉트 + 약관 UX 구현. |

— 끝 —

# ADR 0004 — Neon → Supabase 전환 (DB / Auth) + ADR-0003 부분 supersede

- **상태**: **Proposed (2026-05-29, rev2 2026-06-01, rev3 2026-06-01, rev4 2026-06-01, rev5 2026-06-01, rev6 2026-06-01, rev7 2026-06-01)** — CEO 결정 일부 확정(§2.4 Manual only). 나머지 §7.1 (리전·Storage) + §7.2 사용자 콘솔 작업 대기. **rev7** 에서 rev6 push 직후 Codex 가 단 신규 review threads 6건 (모두 P2) 처리: (a) §2.3 환경변수 블록의 `NAVER_OAUTH_*` 3종 + `OAUTH_STATE_REDIS_URL` / `OAUTH_STATE_TTL_SECONDS` 를 “폐기” → “Naver Custom OAuth PoC 결과 미확정 동안 보존” 으로 정정 (Codex P2 line 286). (b) §2.5 Naver fallback 에 **anon id ↔ OAuth state binding 봉인** 신설 — Naver top-level OAuth redirect 가 `Authorization` 헤더를 실어주지 않으므로 server-side state store (ADR-0003 §2.2 Redis `naver_oauth_state:<state> = anon_user_id` 패턴 그대로) 로 anon id 를 묶음 (Codex P2 line 343 #1). (c) §2.5 Naver fallback 의 “`supabase.auth.admin.linkIdentity()`” 참조를 **제거** — Auth Admin SDK 에 admin 변형이 존재하지 않으므로 `SECURITY DEFINER` Postgres 함수 (`public.fn_link_naver_identity`) 호출로 직접 `auth.identities` INSERT (Codex P2 line 343 #2). (d) `POST /api/auth/terms-accept-finalize` 의 가드를 `require_permanent_user` 가 아닌 신규 **`require_permanent_user_no_consent_check`** 로 분리 — consent 누락 자체를 관측·알람하는 라우트인데 consent 존재 가드를 적용하면 본 목적이 차단됨 (Codex P2 line 256). (e) `auth.users` AFTER UPDATE kakao_sync 트리거에 **required term tags 검증 의무** 추가 — provider='kakao' 만으로 consent row 자동 생성 금지, `kakao_sync_required_term_tags` 매칭 시에만 insert, 미매칭은 `consent_promotion_audit` 에 별도 기록 (Codex P2 line 229). (f) `require_permanent_user` 와 RLS 술어를 단순 `EXISTS terms_consents` 가 아닌 **`policy_current_required_terms` 의 모든 (term_id, version) 셋 매칭** 으로 정정 — 약관 개정 후 옛 동의 row 만 있는 사용자가 통과하던 우회 차단 (Codex P2 line 390). **rev6** 에서 rev5 push 직후 Codex PR review threads 3건 추가 처리 (P1×1 / P2×2): (a) §4.5.2 PoC 실패 fallback 의 단순 “콜백 복귀 후 클라이언트 POST” 패턴을 **금지** — Kakao OAuth 콜백 시점에 `auth.users.is_anonymous=false` 가 이미 commit 되므로 탭 종료 / 네트워크 단절 시 `source='kakao_sync'` 영구 누락. fallback 을 **server-side post-create reconciliation** (3종 옵션 A/B/C) 으로 봉인 (Codex P1 line 424). (b) §2.3 에 **No-session bootstrap 봉인** 신설 — `linkIdentity()` 는 활성 세션 전제 API 이므로 익명 세션이 없는 사용자가 provider 버튼 누르면 실패. `getSession() → 없으면 signInAnonymously() → linkIdentity()` 3단계 패턴을 자식 §5.3 #6 web 자식 이슈가 봉인 (Codex P2 line 208). (c) §4.3 에 **Postgres JWT claims 전파 봉인** 신설 — apps/api 는 PostgREST 가 아닌 SQLAlchemy + psycopg 직접 연결이므로 `auth.uid()` / `auth.jwt()` 가 자동 fire 안 함. `authenticated` role connection + `SET LOCAL "request.jwt.claims"` 패턴 + 통합 테스트 의무를 자식 §5.3 #4 PR 이 봉인 (Codex P2 line 390). **rev5** 에서 Codex PR review threads 5건 처리 (P1×2 / P2×3): (a) §2.3 step 1 의 `signInAnonymously()` 호출에 §4.5.3 + 자식 §5.3 #10 의 4종 abuse control gate 를 다이어그램 안에서 직접 cross-ref (Codex P1 line 152). (b) §2.3 step 2 intent body 의 `target_provider: 'google'|'naver'` → `'google'|'custom:naver'` 로 §2.5 SSOT 와 1:1 정합 (Codex P2 line 165). (c) §2.5 PoC 실패 fallback 에 “anonymous ownership 보존 봉인 (`auth.admin.createUser` 금지, `admin.updateUserById` in-place 영구화 1순위 + 도메인 FK 재할당 트랜잭션 2순위)” 신설 (Codex P2 line 329). (d) §2.3 환경변수 블록에서 `SUPABASE_JWKS_URL` 을 1순위로 신설 + `SUPABASE_JWT_SECRET` 을 2순위 legacy fallback 으로 격하 (Codex P2 line 259). (e) §2.3 라우트 표 `/auth/{provider}/start` 행에 server-side intent enforcement 3중 방어 (trigger no-promote → require_permanent_user 403 → 선택 BEFORE UPDATE trigger RAISE) 봉인 (Codex P1 line 242). **rev4** 에서 보드 추가 리뷰 5건 반영하여 본 ADR 전반에 일관성 봉인 강화: (a) 약관 동의 commit SSOT 행을 §0 결정 요약에 신설 — `auth.users` AFTER UPDATE Postgres trigger 가 identity link 성공을 commit boundary 로 원자 promote, 클라이언트 `terms-accept-finalize` 는 관측/재시도 idempotent only 임을 §0/§2.3/§5.3/§6/§8 에서 1:1 봉인. (b) anonymous → permanent 전환의 provider 버튼은 `linkIdentity()` only — `signInWithOAuth()` 사용 금지를 §0/§2.3/§5.3 #6/§6/§8 라인까지 끝까지 정리. (c) §5.3 #10 production rollout gate 를 “CAPTCHA + rate limit + 익명 row 정리 잡 + Auth MAU 가시성 4종 모두 머지” 로 명문화. (d) §5.3 #11 conversion-only 라우트 매핑을 “상담 신청 / 리드 생성 / 리포트 저장·공유 / 결제 / 일정 예약” 으로 구체화 + RLS 술어 가드 (`auth.jwt() ->> 'is_anonymous' = 'false'`) + `public.terms_consents` 존재 술어 봉인. (e) §6 supersede 표 §2.2 행에 `custom:naver` provider 식별자 + `linkIdentity()` only 봉인. rev3 에서 CEO 2026-06-01 결정 ("Manual identity linking only — automatic linking 허용 안 함") 반영 + 보드 코드 리뷰 P1×4 / P2×1 처리. rev2 에서 보드 코드 리뷰 4건 반영 (refresh/session 정책 분리, anonymous upgrade Manual Linking 봉인, 약관 동의 게이트 순서 재설계, Kakao Sync 저장 경로 정정).
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
| **자동 병합 (동일 이메일)** | **자동 병합 금지** — 단일 provider 탈취 벡터 (CEO 정책 / ADR-0003 §2.3) | **자동 병합 금지 유지 — CEO 2026-06-01 결정 확정.** Supabase Auth `Allow account linking` 의 automatic 토글은 **OFF**. Manual linking (`supabase.auth.linkIdentity()`) 만 enable. 다중 provider 통합은 별도 UX/감사/보안 이슈로 분리. | **ADR-0003 §2.3 + AGENTS.md §4.7 #9 보존 (supersede 안 됨)** |
| **OAuth provider** | `google` · `naver` · `kakao` 3종 ENUM 고정 (자체 콜백) | **Google / Kakao**: Supabase built-in provider. **Naver**: Supabase Custom OAuth/OIDC provider — provider identifier 는 `custom:naver` 로 봉인 (client call · callback 검증 · `auth.identities.provider` 비교 · DB trigger 조건 SSOT 1:1, §2.5 / §8). | ADR-0003 §2.2 (라우트 정본) supersede — 우리 측 `/auth/{provider}/start` · `/auth/callback/{provider}` 폐기 후보 |
| **Anonymous → permanent 전환 OAuth 호출 (rev4 신설)** | (해당 없음 — 자체 콜백 라우트 사용) | **`supabase.auth.linkIdentity({ provider })` only.** `signInWithOAuth({ provider })` 사용 금지 — anonymous 세션을 새 provider-backed user 로 갈아치워 익명 도면·리포트의 in-place claim 을 깨므로 비회원 사전검토 흐름 전체에서 금지. 일반 (anonymous 세션 없는) 신규 가입도 본 MVP 범위에서는 동일하게 `linkIdentity()` 흐름. | §2.3 / §5.3 #6 / §8 1:1 정합 |
| **약관 동의 commit SSOT (Google/Naver, rev4 신설)** | 자체 callback 핸들러가 `terms_consents` 직접 insert | **`auth.users` AFTER UPDATE Postgres trigger (`SECURITY DEFINER`) 가 identity link 성공을 commit boundary 로 `terms_consent_intents → terms_consents` 원자 promote.** 클라이언트 `POST /api/auth/terms-accept-finalize` 는 trigger fire 관측 + 누락 알람용 idempotent 후처리 only — 정합 path 가 아님. 호출 누락 (브라우저 종료 / 네트워크 단절 / POST 실패) 시에도 `terms_consents` row 는 trigger 가 이미 보장. | ADR-0003 §2.2 정합 + 본 ADR §2.3 / §5.3 #6 / §6 / §8 1:1 봉인 |
| **OAuth state store** | Redis `oauth_state:*` / `pending_signup:*` TTL ≤10분 | **Supabase 측이 PKCE state · 약관 동의 → 가입 완료 사이 상태를 관리** | ADR-0003 §2.2 supersede — 자체 Redis state store 폐기. Redis 자체는 채팅·세션 캐시로 잔존. |
| **Access Token / Refresh + Session 수명** | 자체 JWT `AUTH_JWT_ACCESS_TTL_SECONDS` + `AUTH_JWT_REFRESH_TTL_SECONDS=604800` (7일) 단일 환경변수 봉인 | **Supabase Auth 가 두 축으로 분리 운영**. ① Access token TTL = `Authentication → Settings → JWT Expiry` (기본 1h). ② 우리 7일 정책에 대응하는 정본은 `Authentication → Sessions → Session lifetime` + `Inactivity timeout` + `Refresh token reuse interval` (refresh rotation/reuse detection 포함). **JWT Expiry 만으로 7일 정책을 표현할 수 없다.** | ADR-0003 §봉인표 + 보안 런북 POL-AUTH-002 재정렬 필요 |
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

- ADR-0003 §2.2 의 **자체 콜백 라우트** (`POST /auth/{provider}/start` + `GET /auth/callback/{provider}`). Supabase Auth 가 PKCE state 와 약관 동의 후 user upsert 까지 1:1 대체한다.
- ADR-0001 §4 의 **Neon 봉인**. Supabase 도 PostgreSQL 이지만 호스팅 사업자가 다르고 마이그레이션·branching 패턴이 다르다 (§4.1).

> **자동 병합 금지 정책은 포기하지 않는다.** CEO 가 2026-06-01 결정으로 ADR-0003 §2.3 + AGENTS.md §4.7 #9 의 “동일 이메일 + 다른 provider 자동 병합 금지” 원칙을 유지하기로 확정했다. 본 ADR 은 Supabase Auth 의 `Allow account linking (automatic)` 토글을 **OFF** 로 봉인하고, **Manual linking** (`supabase.auth.linkIdentity()`) 만 enable 한다. Manual linking 은 anonymous → permanent 흐름 (§2.3) 의 토대이므로 옵션이 아닌 운영 조건이다 (§2.4.1).

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
- `docs/runbooks/security-policy.md` POL-AUTH-002 (refresh 토큰 7일) — Supabase 에서 동등한 수명 정책은 단일 “JWT Expiry” 가 아니라 **Session lifetime + Inactivity timeout + Refresh token reuse interval (rotation 포함)** 3종이다. 정렬 절차는 §4.4 에서 명문화.

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

**새 흐름 (Proposed, rev3).** 약관 동의 게이트는 `linkIdentity()` **이전** 으로 둔다. 사용자가 약관 거부·이탈해도 anonymous 세션만 유지되고 `auth.users` 변형은 일어나지 않는다 (ADR-0003 / AGENTS.md §4.7 #2: “미동의 시 익명 세션 유지” 보존). **동의 commit 은 서버 측 정합(Postgres trigger + `auth.users` AFTER UPDATE) 으로 원자화** 한다 — 클라이언트의 후속 POST 가 누락되어도 `terms_consents` row 가 빠지지 않는다 (Codex P1 line 174 처리).

**Google / Naver — 우리 측 약관 동의가 먼저.**

```
[브라우저]                                              [Supabase Auth]                    [DB]
  │  1) 익명 진입
  │     supabase.auth.signInAnonymously({                   ────▶
  │       options: { captchaToken } })   ※ abuse control gate
  │       ① CAPTCHA/Turnstile token 의무 (§4.5.3, 자식 §5.3 #10).
  │       ② Supabase Anonymous rate limit (§4.5.3).
  │       ③ 정리 잡 + Auth MAU 알람 (§4.5.3).
  │       ⛔ 자식 §5.3 #10 의 4종 산출물이 모두 머지·운영
  │          가시화되기 전에는 본 호출의 production 노출 금지 (§9).
  │                                                  auth.users row 생성
  │                                                  (is_anonymous=true)
  │                                                  Supabase JWT 발급      ◀────
  │  2) (전환 시점) 사용자가 “Google/Naver 로 계속” 클릭
  │     ⛔ 아직 linkIdentity 호출하지 않음.
  │     우리 측 약관 동의 모달 노출 (브라우저 내, anonymous JWT 상태)
  │       ├── 거부 / 이탈 → anonymous 세션 그대로 유지. linkIdentity 호출 안 함.
  │       │                  auth.users / auth.identities 어디에도 row 변형 없음.
  │       └── 동의 → 우리 서버에 동의 의도(intent) 전달:
  │                  POST /api/auth/terms-accept-intent
  │                    body: { term_id, version, source='internal_signup',
  │                            target_provider: 'google'|'custom:naver' }
  │                    Authorization: Bearer <anonymous Supabase JWT>
  │                  ※ target_provider 는 §2.5 의 Supabase Custom OAuth SSOT 와
  │                    동일 문자열만 허용. 'naver' (built-in) 는 거부.
  │                  서버: anonymous JWT 검증 (sub = anon auth.users.id)
  │                        → public.terms_consent_intents 에 row 1행 insert
  │                          (user_id=anon.id, term_id, version, source,
  │                           target_provider, agreed_at, expires_at = now() + 30min)
  │  3) intent 가 서버에 기록된 직후에만 클라이언트가
  │     supabase.auth.linkIdentity({ provider })             ────▶
  │                                                  provider OAuth 진행
  │                                                  콜백 → auth.identities row 추가
  │                                                  auth.users.is_anonymous=false
  │                                                  (동일 row 승격 — claim 자동)        ◀────
  │                                                                                    │
  │                                                  ┌─ DB: auth.users AFTER UPDATE   ▼
  │                                                  │   Postgres trigger (SECURITY DEFINER) 가
  │                                                  │   is_anonymous: true → false 전이 시
  │                                                  │   같은 user_id 의 유효(미만료) intent 행을
  │                                                  │   public.terms_consents 로 원자 promote.
  │                                                  │   (직전 linked provider 와 intent.target_provider
  │                                                  │    일치 + UNIQUE 가드)
  │                                                  └─ trigger 가 동의 row 보장 →
  │                                                     클라이언트 후속 commit 호출은 idempotent 후처리.
  │  4) (idempotent 후처리, 선택) 클라이언트가 복귀 후 호출:
  │     POST /api/auth/terms-accept-finalize
  │       Authorization: Bearer <permanent Supabase JWT>
  │     서버: permanent JWT 검증 + auth.users.is_anonymous=false 확인
  │            + terms_consents 존재 여부 점검. 없으면 trigger 누락 알람 (관측 가드).
  │     ⚠ 이 호출은 정합 path 가 아니다.
  │       브라우저 종료 / 네트워크 단절 / POST 실패로 호출이 누락되어도
  │       step 3) 의 DB trigger 가 이미 terms_consents row 를 보장한다.
  │       finalize 의 유일한 역할은 trigger 가 실제로 fire 했는지 관측 + 재시도 신호.
  │  5) 익명 세션의 도면·리포트는 같은 auth.users.id 를 그대로 사용 → claim 자동.
```

> **서버 측 동의 commit 정합 (Codex P1 처리).** 클라이언트 측 `terms-accept-commit` POST 에만 의존하면, OAuth redirect 복귀 직후 브라우저 종료 / 네트워크 단절 시 `auth.users.is_anonymous=false + auth.identities row + terms_consents row 없음` 의 invariant 위반 상태가 발생한다. 따라서 **`terms_consents` 의 promotion 은 `auth.users` AFTER UPDATE Postgres trigger 가 원자적으로 수행** 한다. 클라이언트의 후속 `terms-accept-finalize` 는 idempotent 관측 가드 (trigger 가 실제로 fire 했는지 확인) 이지 정합 path 가 아니다. intent 행에는 30분 TTL 을 두어 OAuth 단계 이탈 시 자동 정리한다.

> **Manual linking 봉인 (Codex P1 line 221 처리).** Google/Naver/Kakao 의 “계속” 버튼은 **반드시 `supabase.auth.linkIdentity({ provider })`** 를 호출한다. `signInWithOAuth({provider})` 는 anonymous 세션을 새 provider-backed user 로 갈아치워 익명 도면·리포트의 자동 claim 을 깨므로 **본 ADR 의 비회원 사전검토 흐름에서는 사용 금지**. 일반 (anonymous 세션 없는) 신규 가입에서도 본 MVP 범위에서는 동일하게 `linkIdentity()` 흐름을 따른다 (전환 시점 OAuth — AGENTS.md §4.7 #2). 별도 “provider 만 바로 가입” UX 는 §5.3 신설 #12 (다중 provider 통합 UX) 에서 검토.

> **No-session bootstrap 봉인 (Codex P2 line 208 처리, rev6 신설).** `supabase.auth.linkIdentity()` 는 **로그인된 사용자 (anonymous 또는 permanent) 세션을 전제** 하는 API 다. 따라서 사용자가 anonymous 세션 없이 (예: localStorage 삭제, 직접 가입/상담 링크 진입, 시크릿 모드) provider 버튼을 누르면 호출이 실패한다. 자식 §5.3 #6 (web 자식 이슈) 가 이를 다음 패턴으로 봉인한다. **모든 provider 버튼은 클릭 직후 (1) `supabase.auth.getSession()` 으로 활성 세션 유무를 검사 → (2) 세션이 없으면 `signInAnonymously({ options: { captchaToken } })` 를 동기 await 으로 먼저 호출 (자식 §5.3 #10 의 abuse control gate 통과 필수) → (3) 그 직후에만 `linkIdentity({ provider })` 를 호출** 한다. (2) 단계는 익명 세션이 이미 있으면 idempotent 로 skip 한다. 이 패턴은 §2.3 의 “익명 세션의 도면·리포트는 같은 auth.users.id 를 그대로 사용 → claim 자동” invariant 를 보존한다. **`signInWithOAuth()` 우회 사용 금지** 는 그대로 — 직접 가입 링크에서도 (2)+(3) 의 2단계로 anonymous-then-link 흐름을 강제한다. 별도 “세션 없이 바로 provider 가입” UX 는 §5.3 #12 (다중 provider 통합 UX) 에서 검토.

**Kakao — Kakao Sync 약관 화면이 게이트.**

```
[브라우저]                                              [Supabase Auth + Kakao]
  │  1) 익명 진입 (동일)
  │  2) (전환 시점) 사용자가 “카카오로 계속” 클릭
  │     supabase.auth.linkIdentity({ provider: 'kakao' })   ────▶
  │                                                  Kakao 인증 화면 + Kakao Sync 약관
  │                                                    ├── 거부 → Kakao 가 error 로 복귀.
  │                                                    │           auth.identities row 미생성,
  │                                                    │           anonymous 세션 유지.
  │                                                    └── 동의 → 콜백 → auth.identities 추가
  │                                                                auth.users.is_anonymous=false  ◀────
  │  3) Supabase DB 측에서 Postgres trigger 가 auth.users AFTER UPDATE
  │     (is_anonymous=true → false) 를 감지하면, 직전에 auth.identities 에
  │     추가된 provider 가 'kakao' 인 경우 한정으로 public.terms_consents
  │     (source='kakao_sync', term_id=정책 정본 id, version=정본 버전)
  │     row 를 SECURITY DEFINER 함수로 insert.
  │     — 또는 Database Webhook 으로 우리 FastAPI 의
  │       POST /api/auth/kakao-sync-consent-ingest 를 호출하여 동일 작업 수행.
```

> Kakao Sync 의 약관 동의는 카카오 콘솔에 등록한 약관 메타데이터(노출 문구·버전)에 사용자가 동의했음을 카카오가 보증하는 흐름이다. 우리는 사용자 동작이 카카오 측에 기록되어 있음을 신뢰하고, DB 측 트리거 또는 Database Webhook 으로 우리 도메인에 동일한 의미의 row 를 후속 저장한다.

**3개 흐름 공통 — 익명 세션 유지 보장.**

| 시점 | 사용자 행동 | `auth.users.is_anonymous` | `auth.identities` | `public.terms_consents` |
|---|---|---|---|---|
| 진입 | 익명 시작 | true (신규 row) | (없음) | (없음) |
| Google/Naver 약관 거부 | 모달 닫기 | true (보존) | (없음) | (없음) |
| Google/Naver 약관 동의 후 OAuth 거부 / 이탈 | OAuth 화면 닫기 | true (보존) | (없음) | intent row 만 (TTL 만료) |
| Google/Naver 정상 가입 | OAuth 완료 | false | provider row 1 추가 (`google` 또는 `custom:naver`) | source='internal_signup' (trigger 가 intent 를 atomic promote) |
| Kakao Sync 거부 | 카카오 측에서 reject | true (보존) | (없음) | (없음) |
| Kakao Sync 정상 가입 | 카카오 측 동의 완료 | false | kakao row 1 추가 | source='kakao_sync' (trigger/webhook) |

**API 라우트 변화.**

| 기존 (ADR-0003 §2.2) | 본 ADR (Proposed) |
|---|---|
| `POST /auth/{provider}/start` | **폐기.** 클라이언트가 `supabase.auth.linkIdentity({ provider })` 직접 호출 (anonymous 세션의 in-place 승격 보장). `signInWithOAuth({provider})` 는 새 user 로 갈아치우므로 **사용 금지**. **서버측 intent 강제 (Codex P1 line 242 처리, rev5 봉인)**: 브라우저가 우리 서버를 거치지 않고 Supabase 로 `linkIdentity()` 를 직접 호출하므로, intent POST 누락 시 사용자가 permanent 로 전이되어도 consent 가 없는 상태가 발생할 수 있다. 이를 두 단계로 방어한다. ① **`auth.users` AFTER UPDATE trigger 가 매칭되는 유효 intent 가 없으면 `terms_consents` 를 생성하지 않는다** — 즉 intent 누락은 “permanent 이지만 consent 없음” 상태로 귀결된다. ② **§4.3 의 `require_permanent_user` 가드 + RLS 술어 (`EXISTS terms_consents`) 가 consent 없는 permanent user 의 모든 conversion-only 라우트 호출을 403** 으로 거부. ③ 선택 추가 방어 (자식 §5.3 #3 의 trigger PR 에서 결정): `auth.users` **BEFORE UPDATE** trigger 가 `is_anonymous: true → false` 전이 시 매칭 intent 가 없으면 `RAISE EXCEPTION` → 전이 자체를 거부. ①+② 가 운영상 충분하면 ③ 는 생략 가능. |
| `GET /auth/callback/{provider}` | **폐기.** Supabase 가 콜백 호스팅. Supabase 콜백 → 우리 프론트 redirect URL 로 복귀. |
| `POST /auth/refresh` | **폐기.** Supabase JS SDK 가 자동 refresh. |
| `POST /auth/logout` | **폐기.** `supabase.auth.signOut()` 사용. Redis 블랙리스트 불필요. |
| (신규) `POST /api/auth/terms-accept-intent` | **신설.** Google/Naver `linkIdentity()` **이전** 에 anonymous JWT 컨텍스트에서 사용자의 약관 동의 의도를 `public.terms_consent_intents` (TTL ≈ 30분, `target_provider` 포함) 에 기록. Supabase JWT 를 `Authorization: Bearer` 로 검증. 익명 JWT 가드는 `require_anonymous_or_permanent_user` (§4.3). |
| (신규) `POST /api/auth/terms-accept-finalize` | **신설 (idempotent 관측 가드).** OAuth 콜백 복귀 후 permanent JWT 컨텍스트에서 `terms_consents` row 가 실제로 존재하는지 점검. 누락 시 trigger 미발화 알람 emit. **정합 path 가 아님** — `terms_consents` 의 진짜 promotion 은 §2.3 의 Postgres trigger 가 원자적으로 수행. **가드 (rev7 정정 — Codex P2 line 256)**: 본 라우트는 “consent row 가 없는 상태” 자체를 관측·알람하기 위한 라우트이므로 `require_permanent_user` (= consent 존재 술어 포함) 를 적용하면 가드가 라우트의 목적을 차단한다. 따라서 별도 가드 **`require_permanent_user_no_consent_check`** (§4.3 신설) 를 사용한다 — JWT 검증 + `is_anonymous=false` 만 강제하고 `terms_consents` 존재는 검사하지 않는다. consent 누락 시 본 라우트가 trigger 미발화 알람을 emit 한다 (그게 본 라우트의 유일한 책임). |
| (신규) `auth.users` AFTER UPDATE Postgres trigger (`SECURITY DEFINER`) — **internal_signup 정합용** | **신설 (정합 정본).** `is_anonymous: true → false` 전이 + 직전에 `auth.identities` 에 추가된 provider 가 `'google'` 또는 `'naver'`/`'custom:naver'` 인 경우, 같은 `user_id` 의 유효(미만료) `terms_consent_intents.target_provider` 와 매칭되는 행을 `public.terms_consents (source='internal_signup')` 로 1행 promote insert. UNIQUE 가드로 중복 방지. |
| (신규) `auth.users` AFTER UPDATE Postgres trigger (`SECURITY DEFINER`) — **kakao_sync 정합용** | **신설 (1순위).** `is_anonymous: true → false` 전이 + provider 가 `'kakao'` 이면 `public.terms_consents (source='kakao_sync')` 1행 insert. Supabase 가 노출하는 표준 메커니즘. `before_user_created` / `after_user_created` Auth Hook 은 **사용하지 않는다** — 전자는 `auth.users` row commit 전이라 FK 위반, 후자는 현재 Supabase Auth Hook 카탈로그에 존재하지 않음. 위 두 트리거는 단일 `auth.users` AFTER UPDATE 함수에서 source 분기로 구현해도 무방. **rev7 정정 (Codex P2 line 229) — required term tags 검증 의무**: provider='kakao' 만으로 consent row 를 자동 생성하면 안 된다. Kakao 사용자가 Kakao Sync 약관 화면을 거치지 않은 일반 Kakao OAuth 로 진입했거나 Kakao 앱이 잘못 구성되어 필수 약관 tag 가 누락된 경우에도 트리거가 `source='kakao_sync'` audit row 를 만들어 법적으로 부정확한 감사 흔적이 남는다. 따라서 트리거는 `auth.identities.identity_data` (Kakao userinfo) 의 약관 동의 tag 목록을 `public.policy.kakao_sync_required_term_tags` (정책 정본 테이블) 와 **모두 매칭** 하는지 검증한 뒤에만 insert. 매칭 실패 시 (a) consent row 미생성 + (b) `public.consent_promotion_audit` 에 “Kakao Sync 약관 미충족 — provider=kakao 이나 required_term_tags 누락” row 를 별도 기록하여 운영팀이 사용자에게 약관 재요청 UX 를 띄울 수 있도록 한다. 자식 §5.3 #3 (트리거 PR) 가 이 검증 SQL 을 봉인. |
| (신규) `POST /api/auth/kakao-sync-consent-ingest` + Supabase Database Webhook | **대체 경로 (2순위).** 트리거 채택이 운영상 부담스러우면 `auth.users` UPDATE 이벤트를 Database Webhook 으로 우리 FastAPI 에 전달. 서버에서 Supabase admin SDK 로 `auth.identities` 의 provider 를 확인 후 `terms_consents` insert. PoC §4.5 범위. internal_signup 정합도 동일 webhook 으로 처리 가능 (intent → consent promotion). |

**환경변수 변화 (정본은 `.env.example` PR 에서 봉인).**

```env
# 신설 (Supabase)
SUPABASE_URL=                       # https://<project-ref>.supabase.co
SUPABASE_ANON_KEY=                  # 브라우저 측 (anon role)
SUPABASE_SERVICE_ROLE_KEY=          # 서버 측만 (admin/RLS bypass) — 절대 브라우저에 노출 금지
SUPABASE_JWKS_URL=                  # 1순위 — 우리 API 의 Supabase JWT 검증 정본 (asymmetric keys via JWKS endpoint).
                                    # 예: https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json
                                    # 키 회전이 무중단 (Supabase 가 발급한 새 키도 endpoint 가 즉시 노출).
SUPABASE_JWT_SECRET=                # 2순위 (legacy fallback only). 신규 프로젝트는 JWKS 사용. 본 ADR §4.3 가드는
                                    # JWKS 검증 path 를 1순위로 구현하고, JWT_SECRET 은 HS256 fallback 만 둔다.
                                    # 본 변수가 비어 있어도 JWKS_URL 만으로 검증이 동작해야 한다.
SUPABASE_PROJECT_REF=               # 마이그레이션 CLI 용
DATABASE_URL=                       # Supabase pooler / non-pooler — Neon 자리 대체

# 폐기 (ADR-0003 환경변수)
KAKAO_REST_API_KEY=                 # → Supabase Dashboard / Auth Providers 콘솔로 이전
KAKAO_CLIENT_SECRET=
KAKAO_REDIRECT_URI=
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URI=
NAVER_OAUTH_CLIENT_ID=              # ⚠ rev7 정정: §2.5 Naver Custom OAuth PoC 가 실패해 자체 OAuth fallback (§2.5) 으로 전환되면 이 3종 변수가 다시 필요하다.
NAVER_OAUTH_CLIENT_SECRET=          # 따라서 폐기는 **PoC 성공 + Custom OAuth 채택이 확정된 시점에만**. PoC 결과 미확정 동안에는 보존 (자식 §5.3 #5 정본).
NAVER_OAUTH_REDIRECT_URI=
OAUTH_STATE_REDIS_URL=              # ⚠ rev7 정정: §2.5 Naver fallback 이 사용 (anon id ↔ OAuth state 결합용 — Codex P2 line 343 처리). Redis 자체는 채팅·세션·Naver fallback state store 로 잔존.
OAUTH_STATE_TTL_SECONDS=            # 동일 — Naver fallback 채택 시 보존. Google/Kakao 는 Supabase 가 state 관리.
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

### 2.4 Identity Linking 정책 — Manual only 확정 (CEO 2026-06-01 결정)

**기존 정본 (ADR-0003 §2.3 + AGENTS.md §4.7 #9).**

> 같은 `provider_email` 이 카카오/구글/네이버에서 각각 가입되어도 별개 user 로 둔다. 이메일 매칭으로 자동 linking 하지 않는다. … 자동 병합은 단일 provider 탈취가 모든 provider 의 데이터로 권한 상승되는 벡터.

**본 ADR 결정 (Proposed, rev3 확정).** CEO 가 2026-06-01 결정으로 **Manual identity linking only** 를 확정했다 (CMP-572 결정 + CMP-573 wake 코멘트 5dca4b42). ADR-0003 §2.3 + AGENTS.md §4.7 #9 의 “동일 이메일 + 다른 provider 자동 병합 금지” 원칙은 **보존** 한다.

| 항목 | 결정 |
|---|---|
| Supabase `Authentication → Settings → Allow account linking` (manual) | **ON (무조건)** — anonymous → permanent 전환 (§2.3) 의 `supabase.auth.linkIdentity()` 가 의존. |
| Supabase `Authentication → Settings → Allow account linking` (automatic) | **OFF** — 동일 verified email 자동 병합 금지. CEO 결정 봉인. |
| 이미 가입된 영구 user 가 두 번째 provider 를 추가하려는 경우 | **우리 측 명시 UX 호출** 로만 처리. 사용자가 “계정 통합” 흐름을 명시 트리거해야 `supabase.auth.linkIdentity()` 가 실행되어 추가 row 가 들어간다. 그 UX 설계 / 감사 로그 / 보안 검토는 **별도 후속 이슈 §5.3 신설 #12** 로 분리 (본 ADR 범위 외). |
| ADR-0003 §2.3 supersede | **없음** — 정책 보존. 본 ADR §6 supersede 표에서도 §2.3 행은 “보존” 으로 표기. |
| AGENTS.md §4.7 #9 supersede | **없음** — 정책 보존. 자식 이슈 §5.3 #1 의 §4.7 갱신 범위에서 #9 제외. |

> **권한 상승 벡터 보존.** Manual only 봉인은 ADR-0003 §2.3 의 탈취 벡터 분석을 그대로 보호한다. 단일 provider 탈취 시 다른 provider 의 데이터에 권한 상승되지 않는다. Supabase 채택 이득의 일부 (가입 마찰 절감) 는 의도적으로 포기.

#### 2.4.1 Manual Linking 활성화 — Anonymous Upgrade 의 무조건 운영 조건

§2.4 의 “자동 병합 금지” 정책과 별개로, **anonymous → permanent 전환** (본 ADR §2.3 의 핵심 흐름) 은 `supabase.auth.linkIdentity()` 를 사용하며, 이 API 는 Supabase Auth 의 **Manual Linking** 설정이 **enable** 되어 있어야만 동작한다.

| Supabase 설정 | API | 본 ADR 의존도 |
|---|---|---|
| `Authentication → Settings → Allow account linking` (manual) | `supabase.auth.linkIdentity()` | **무조건 ON** — anonymous upgrade 흐름 전체가 이 API 위에 있다. |
| `Authentication → Settings → Allow account linking` (automatic) | 동일 이메일 자동 병합 (가입 시점 자동 처리) | **OFF (§2.4 확정)**. |

**봉인.** 두 토글을 분리 운영. **Manual 을 끄면 §2.3 흐름이 무너지고, Automatic 을 켜면 §2.4 정책 위반이다.** 사용자 콘솔 작업 (§7.2.5) 에서 두 토글을 분리하여 정확히 위 상태로 설정.

### 2.5 OAuth Provider 매핑

| Provider | Supabase 채택 방식 | 콘솔 작업 책임 |
|---|---|---|
| **Google** | Supabase built-in provider. `Authentication → Providers → Google` 에 OAuth client id/secret 등록. | 사용자 — Google Cloud Console 에서 OAuth client 생성 + redirect URI 에 Supabase callback (`https://<project-ref>.supabase.co/auth/v1/callback`) 등록. |
| **Kakao** | Supabase built-in provider. `Authentication → Providers → Kakao` 에 REST API key + client secret 등록. | 사용자 — Kakao Developers 콘솔에서 앱 생성 + redirect URI 등록 + Kakao Sync 약관 노출 설정. |
| **Naver** | **Supabase Custom OAuth/OIDC provider — PoC 필요.** Naver 는 built-in 미지원. Supabase Custom OAuth 로 우회. **Provider identifier 는 `custom:naver` 로 봉인** (Supabase docs: custom provider 는 반드시 `custom:` prefix 로 호출. built-in 처럼 `naver` 단독 호출 시 정상 동작하지 않음). 클라이언트 호출, 콜백 검증, `auth.identities.provider` 비교, §2.3 트리거의 provider 일치 조건 모두 **`custom:naver`** 문자열을 1:1 사용한다. | 사용자 — Naver Developers 콘솔에서 앱 생성 + redirect URI 등록. CTO/Backend Lead — PoC 후속 이슈 (§5.3 #5). |

**PoC 성공 기준 (Naver).**
- `supabase.auth.linkIdentity({ provider: 'custom:naver' })` 로 Naver authorize → Supabase callback → `auth.identities` row 생성 (`provider = 'custom:naver'`) 까지 정상 동작.
- `auth.users.email` 이 Naver userinfo 의 검증된 이메일을 정확히 받는다.
- §2.3 의 `auth.users` AFTER UPDATE Postgres trigger 가 `provider IN ('google','custom:naver')` 조건으로 `public.terms_consents (source='internal_signup')` 를 원자 promote insert 한다.

**PoC 실패 시 fallback.** Naver 만 자체 OAuth 코드 (ADR-0003 §2.2 의 `/auth/{provider}/start` + `/auth/callback/{provider}`) 패턴을 유지한다. 이 경우 본 ADR 의 §2.3 흐름은 Google/Kakao 에만 적용되고, Naver 측 약관 동의 commit 은 우리 측 callback 핸들러가 직접 수행한다. **단 anonymous 세션 ownership 보존 봉인 (Codex P2 line 329 + P2 line 343 처리, rev5+rev7)**: 사용자가 이미 익명 세션 (`auth.users.is_anonymous=true`) 에서 도면·리포트를 만든 상태로 Naver 로 전환하는 경우, **`auth.admin.createUser()` 로 새 user 를 만들면 안 된다** — 새 user 의 id 가 익명 도면·리포트 FK 와 불일치하여 ownership 이 끊긴다.

> **anon id ↔ OAuth state binding (rev7 신설 — Codex P2 line 343).** Naver 가 브라우저를 **top-level OAuth redirect** 로 우리 callback 에 보내므로 SPA 가 설정한 `Authorization: Bearer <anonymous Supabase JWT>` 헤더는 callback request 에 실리지 않는다. 따라서 anon `auth.users.id` 를 callback 시점에 식별하려면, `/auth/naver/start` 가 OAuth `state` 파라미터를 생성할 때 **server-side state store** (ADR-0003 §2.2 의 Redis `naver_oauth_state:<state> = anon_user_id` 패턴 그대로, TTL ≤ 10분) 에 anon id 를 묶고, `/auth/callback/naver` 가 state 로 anon id 를 lookup 한다. start route 는 사용자가 anonymous 세션을 갖고 있을 때만 호출되며 (없으면 §2.3 No-session bootstrap 봉인 → `signInAnonymously()` 선행 → 그 다음 start 호출), start 핸들러가 Supabase JWT 를 검증한 anon id 를 state 에 저장.

이후 callback 핸들러는 state 로 식별한 anon id 에 대해 다음 1순위 / 2순위 경로 중 하나를 채택한다. **1순위 (rev7 정정 — admin SDK 메서드 오기재 제거)**: callback 핸들러가 (i) `supabase.auth.admin.updateUserById(anonId, { email, email_confirm: true })` 로 익명 row 를 in-place 영구화 (`is_anonymous=false` 전이) + (ii) `auth.identities` 에 `(user_id=anonId, provider='custom:naver', identity_data={...Naver userinfo}, email=<verified email>)` row 를 **`SECURITY DEFINER` Postgres 함수** (`public.fn_link_naver_identity(anon_id uuid, identity jsonb)`) 호출로 직접 INSERT (Supabase Auth Admin SDK 의 `linkIdentity()` 는 user-scoped 흐름이며 admin 변형이 존재하지 않으므로 어떤 admin SDK 호출도 끌어다 쓰지 않는다 — Codex P2 line 343 의 “admin linkIdentity 미존재” 지적 반영). UNIQUE `(provider, provider_id)` 가드 + 트랜잭션. **2순위**: 그 admin path 가 운영상 불가하면 callback 핸들러가 (a) 새 user 를 만들고 (b) **anon row 의 도메인 FK 를 새 user.id 로 일괄 재할당하는 트랜잭션** 을 명시적으로 실행한 뒤 (c) anon row 를 삭제. 둘 다 anonymous 도면·리포트의 ownership 을 끊지 않는 것이 본 fallback 의 필수 invariant. 자식 §5.3 #5 (Naver PoC) 가 PoC 실패 분기를 PR 로 만들 때 위 1순위/2순위 중 어느 쪽으로 구현할지 봉인.

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

### 4.3 우리 측 API ↔ Supabase JWT 검증 + 익명/영구 가드 분리

- FastAPI 의존성을 **3종으로 분리** 봉인한다. `signInAnonymously()` 가 발급한 JWT 도 정상 검증을 통과하므로 (`sub = auth.users.id`, `role = authenticated`), 단일 `get_current_user` 만 쓰면 익명 사용자가 가입 전용 라우트를 통과한다 (Codex P1 line 345). AGENTS.md §4.7 #2 (전환 시점 OAuth 의무) 정합을 위해 다음 분리가 필요하다.

| FastAPI 의존성 | 검증 조건 | 사용처 |
|---|---|---|
| `get_current_user` | Supabase JWT 서명 + exp 검증. `auth.users.id` 만 반환. | 내부 helper. 라우트 직접 사용 금지 (의도 표현 약함). |
| `require_anonymous_or_permanent_user` | JWT 검증 + (`is_anonymous=true` 또는 `false`) 둘 다 허용. | 비회원 사전검토 (도면 업로드, 사전 리포트 조회 등 AGENTS.md §4.7 #1 허용 범위) + `POST /api/auth/terms-accept-intent`. |
| `require_permanent_user` | JWT 검증 + **`is_anonymous=false` 강제 + 현재 정본 약관에 대한 `public.terms_consents` 매칭 row 존재 확인** (rev7 정정 — Codex P2 line 390. 단순 `EXISTS terms_consents` 가 아니라 `(term_id, version)` 이 `policy.current_required_terms` 셋에 모두 포함되는지 검증). 위반 시 403. | 상담 신청, 리드 생성, 리포트 저장/공유, 결제 등 AGENTS.md §4.7 #2 의 “전환 시점 OAuth 의무” 라우트 전부. |
| `require_permanent_user_no_consent_check` (rev7 신설 — Codex P2 line 256) | JWT 검증 + **`is_anonymous=false` 만 강제. `terms_consents` 존재는 검사하지 않는다.** | **`POST /api/auth/terms-accept-finalize` 전용**. 본 라우트는 “consent 누락 자체를 관측·알람” 하는 책임이므로 consent 존재 가드를 적용하면 본 목적을 차단. 이 가드는 본 finalize 라우트 외 다른 라우트에서 사용 금지. |

- **RLS 정책도 동일 가드를 DB 레벨에서 중복 봉인** 한다. 예: `lead` 테이블의 `INSERT` RLS 는 (a) `auth.jwt() ->> 'is_anonymous' = 'false'` 술어 + (b) **현재 정본 약관 매칭 술어** (rev7 정정 — Codex P2 line 390): `(SELECT bool_and(EXISTS (SELECT 1 FROM public.terms_consents tc WHERE tc.user_id = auth.uid() AND tc.term_id = rt.term_id AND tc.version = rt.version)) FROM public.policy_current_required_terms rt)`. 즉 `policy_current_required_terms` 가 명시하는 모든 (term_id, version) 셋에 대해 사용자의 동의 row 가 모두 존재해야 통과. 단순 `EXISTS terms_consents` 는 약관 개정 후 옛 동의 row 만 있는 사용자도 통과하므로 **사용 금지**. 의존성 누락 시 RLS 가 2차 가드. 정확한 라우트별 매핑은 자식 이슈 §5.3 #11 (require_permanent_user 가드 PR) 가 정본.
- **Postgres 측 JWT claims 전파 봉인 (Codex P2 line 390 처리, rev6 신설).** `apps/api` 는 SQLAlchemy + psycopg 로 Supabase Postgres 에 **직접 연결** 한다 (PostgREST 가 아니다). 그러므로 Supabase 가 PostgREST 경로에서 자동으로 채워주는 `auth.uid()` / `auth.jwt()` helper 는 우리 트랜잭션 안에서 **자동으로 fire 하지 않는다**. RLS 술어 (`auth.uid() = user_id`, `auth.jwt() ->> 'is_anonymous' = 'false'`) 가 사용자 컨텍스트 없이 평가되어 모두 false / NULL 이 되거나, 우리가 `service_role` 로 연결한 경우 RLS 가 통째로 우회된다. 따라서 다음 패턴을 봉인한다. (1) **FastAPI 의 DB connection pool 은 기본적으로 `authenticated` role 로 연결** 한다 (`service_role` 은 마이그레이션·관리 작업 전용으로 별도 pool 분리). (2) 각 request 의 트랜잭션 시작부에 FastAPI 의존성 / SQLAlchemy event listener 가 다음을 실행한다 — `SET LOCAL role 'authenticated'; SET LOCAL "request.jwt.claims" = <검증된 JWT payload JSON>;`. 이로써 `auth.uid()` / `auth.jwt()` 가 트랜잭션 범위 안에서 실제 사용자 컨텍스트를 반환. (3) 마이그레이션 / DDL / 운영 잡 등 RLS 우회가 필요한 작업만 별도 `service_role` connection pool 로 분리. **이 패턴은 자식 §5.3 #4 (FastAPI Supabase JWT 의존성 + RLS 정책 초안) PR 이 봉인** 하고, **통합 테스트 (`tests/auth/test_rls_claims_propagation.py`) 가 다음을 보장**: ① anonymous JWT 가 propagate 된 트랜잭션에서 `lead` INSERT 가 RLS 로 거부됨. ② permanent JWT 가 propagate 된 트랜잭션에서 동일 INSERT 가 통과. ③ JWT propagation 자체가 누락된 트랜잭션 (e.g., 의존성 미주입) 에서도 INSERT 가 거부됨 (RLS evaluate against NULL claims = denied). 자식 §5.3 #11 의 RLS 가드 (`auth.jwt() ->> 'is_anonymous' = 'false'` + `EXISTS terms_consents`) 는 이 propagation 위에서만 의미를 갖는다.
- 자체 JWT 발급 코드 제거 (ADR-0003 §2.2 의 access/refresh TTL 환경변수 폐기와 연동).
- Refresh 는 SDK 측 자동 처리. 서버 측 블랙리스트 불필요.

### 4.4 Refresh / Session 수명 — 보안 런북 POL-AUTH-002 정합 (SSOT 분리 이동)

Supabase Auth 에서 “토큰 수명” 은 **두 축으로 분리** 운영된다. 본 ADR 은 POL-AUTH-002 의 7일 정책을 단일 “JWT Expiry” 로 옮기지 않고, 의미가 같은 3종 설정으로 분리 봉인한다.

| 정책 의미 | Supabase 정본 위치 | 본 ADR 정렬 값 (POL-AUTH-002 7일 정책 대응) |
|---|---|---|
| **Access token TTL** (단기 베어러 수명) | `Authentication → Settings → JWT Expiry` | Supabase 기본값(1h) 유지. 우리 7일 정책의 대상이 **아님**. |
| **세션 최대 수명** (재로그인 강제까지의 절대 한계) | `Authentication → Sessions → Session lifetime` (a.k.a. `Time-box user sessions`) | **7일 (604800s)** — POL-AUTH-002 의 본래 의도. |
| **세션 비활성 만료** (마지막 활동 후 자동 만료) | `Authentication → Sessions → Inactivity timeout` | **7일 이하** — Session lifetime 보다 짧거나 같게. 운영 협의로 결정 (예: 14일 정책 외 시 7일 그대로). |
| **Refresh token 회전 / 재사용 탐지** | `Authentication → Sessions → Refresh token reuse interval` (rotation 포함) | reuse interval ≤ 10s (기본값) 유지 + reuse detection enable. 회전 보안 정본. |

- 본 ADR Accepted 시 보안 런북 POL-AUTH-002 의 “환경변수 정본” 줄은 `apps/api/.env.example::AUTH_JWT_REFRESH_TTL_SECONDS` → **`Supabase Dashboard → Authentication → Sessions → Session lifetime` (+ `Inactivity timeout`, + `Refresh token reuse interval` 회전 정책)** 로 정정한다. **`JWT Expiry` 단독으로 옮기지 않는다 — 이는 access token TTL 만 의미하므로 7일 refresh/session 정책을 표현할 수 없다.**
- `docs/명세서-모순.md` CFLT-006 의 “Resolved (7일/604800s)” 결론은 유지하되 SSOT 위치만 위 표대로 이동.
- 보안 런북 후속 작업은 자식 이슈 §5.3 #9 가 처리. 본 ADR 자체는 위치 이동 사실만 봉인한다.

### 4.5 PoC — Naver Custom OAuth + Kakao Sync 후속 저장 경로

본 ADR Accepted 시 가장 먼저 풀어야 할 기술 리스크.

**4.5.1 Naver Custom OAuth/OIDC PoC.** Supabase Dashboard 의 Custom OAuth provider 로 Naver 가 §2.5 PoC 성공 기준을 통과하는지 검증. 실패 시 §2.5 fallback.

**4.5.2 Kakao Sync source 분리 저장 PoC.** **Auth Hook 가정 금지** — 현재 Supabase Auth Hook 카탈로그에는 `after_user_created` 가 존재하지 않으며, `before_user_created` 는 `auth.users` row commit 이전이라 `terms_consents.user_id` FK insert 가 불가능하다. 대신 다음 2개 경로 중 하나를 채택한다.

| # | 경로 | 메커니즘 | 평가 축 |
|---|---|---|---|
| **1순위** | **Postgres trigger on `auth.users` AFTER UPDATE** | `SECURITY DEFINER` 함수로 `is_anonymous: true→false` 전이 + 직전 `auth.identities` provider='kakao' 조건일 때 `terms_consents` 1행 insert. Supabase 가 `auth` 스키마 트리거 작성을 허용 (RLS 우회는 `SECURITY DEFINER` + `search_path` 봉인). | 트랜잭션 정합 ✅, 외부 호출 비용 0, 운영 가시성은 DB 로그 의존. |
| **2순위** | **Supabase Database Webhook → 우리 FastAPI** | `auth.users` UPDATE 이벤트를 Supabase Database Webhook 으로 우리 FastAPI `/api/auth/kakao-sync-consent-ingest` 에 push. 서버에서 Supabase admin SDK 로 provider 확인 + `terms_consents` insert. | 운영 가시성 ✅ (FastAPI 로그·메트릭), 실패 시 webhook 재시도 정책 의존, 트리거 대비 1-RTT 지연. |

**PoC 성공 기준 (Kakao Sync).** 트리거(또는 webhook) 가 Kakao 정상 콜백 직후 1회만 fire 되고 동일 `(user_id, term_id, version, source='kakao_sync')` UNIQUE 제약을 위반하지 않는다. Naver / Google 콜백에서는 fire 되지 않거나 동일 가드로 silent skip.

**PoC 실패 시 fallback (Codex P1 line 424 처리, rev6 정정).** 트리거·webhook 둘 다 PoC 실패 시 단순 “콜백 복귀 후 클라이언트 POST” 패턴은 **사용 금지**. 이유: Kakao OAuth 콜백 시점에 이미 `auth.users.is_anonymous=false` 가 commit 되어 영구 user 로 전이되는데, 그 직후 사용자가 탭을 닫거나 네트워크가 끊기면 `source='kakao_sync'` 동의 row 가 영구 누락되어 §2.3 의 “Kakao Sync 시 반드시 source='kakao_sync' row 존재” invariant 가 깨진다. 따라서 fallback 도 **server-side post-create reconciliation** 으로 봉인한다. 다음 3종 중 하나를 자식 §5.3 #5 (Kakao Sync PoC fallback) PR 이 채택한다. **fallback-A**: Supabase Database Webhook 대신 우리 측 주기 reconciliation 잡 (예: 분당 1회) 이 `auth.users WHERE is_anonymous=false AND EXISTS (auth.identities WHERE provider='kakao') AND NOT EXISTS (public.terms_consents WHERE source='kakao_sync' AND user_id=...)` 를 스캔 → Supabase admin SDK 로 Kakao 약관 동의 메타데이터 재확인 (또는 Kakao open-id token 의 scope 확인) → `terms_consents` insert. **fallback-B**: Supabase Auth 의 OAuth provider `Send Auth Hook` (사용 가능 시) 에 우리 측 endpoint 를 등록하여 token 발급 시점에 server-to-server 로 동의 row 를 insert. **fallback-C**: Supabase 측 Edge Function 을 Kakao 콜백 redirect URL 로 등록하여 Supabase 콜백 chain 안에서 server-to-server 로 `terms_consents` insert 후 우리 프론트로 redirect. **공통 invariant**: 클라이언트 POST 에만 의존하지 않는다. 사용자 탭 종료 / 네트워크 단절이 동의 row 누락을 만들지 않는다.

**4.5.3 익명 abuse control (Codex P1 line 149 처리).** `signInAnonymously()` 는 PII 없이도 영구 `auth.users` row 를 생성한다. Supabase docs 가 명시한 경고: 스크립트형 클라이언트가 무제한 호출하면 (1) Auth MAU 가 폭증해 요금 곡선이 깨지고, (2) `auth.users` row 가 정리 자동화 없이 누적되어 DB 가 비대화된다. 본 ADR §2.3 의 비회원 사전검토 흐름은 이 위험을 정면으로 안고 가므로 다음을 **자식 이슈 §5.3 #10 (Anonymous abuse control)** 로 분리 봉인한다.

| 가드 | 정본 위치 | 비고 |
|---|---|---|
| **CAPTCHA / Cloudflare Turnstile** | `signInAnonymously()` 호출 전 클라이언트 검증 → Supabase Auth 의 `captchaToken` 옵션으로 전달. Supabase Dashboard `Authentication → Attack Protection → CAPTCHA Protection` 활성화. | Turnstile / hCaptcha 중 선택은 자식 이슈에서 결정. CEO 콘솔 작업 항목 §7.2 에 추가. |
| **Rate limiting** | Supabase Dashboard `Authentication → Rate Limits → Anonymous sign-ins` (IP/시간당 N회). 우리 측 FastAPI `/api/auth/*` 라우트는 Caddy/proxy 단에서 추가 rate limit (자식 이슈 결정). | 기본값은 Supabase rate limit 표 확인 후 봉인. |
| **익명 row 정리 잡** | `auth.users WHERE is_anonymous=true AND created_at < now() - interval '30 days' AND NOT EXISTS (관련 도면/리포트 FK)` 패턴의 cron job. Supabase Edge Function 또는 우리 FastAPI 의 `apscheduler`/별도 워커. | 30일은 잠정값. 사용자 결과 화면 재방문 패턴 보고 조정. 자식 이슈에서 SLA 결정. |
| **Auth MAU 가시성** | Supabase Dashboard `Reports → Auth` 의 MAU/DAU 라인을 운영 대시보드에 미러링. 임계치 초과 시 알람. | Supabase 요금 곡선 보호. |
| **`X-Forwarded-For` / IP 헤시 로깅** | `signInAnonymously()` 직후 우리 측 `/api/auth/anon-bootstrap-ping` (선택) 으로 IP 해시 + UA 를 기록 → 동일 IP/UA 의 익명 row 폭증 탐지. | PII 정책 검토 필요. 자식 이슈에서 결정. |

**본 ADR 의 본문 봉인 효과.** 위 가드들이 자식 이슈 §5.3 #10 에서 구현될 때까지, 본 ADR 의 §2.3 흐름은 **개발/스테이징에서만 시연** 가능하며 production rollout 의 전제조건이다. §9 변경 절차에 “§5.3 #10 미완 시 본 ADR 의 production 적용 금지” 줄 추가.

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
- **익명 sign-in 의 신규 abuse 벡터** — `signInAnonymously()` 가 PII 없이 영구 `auth.users` row 를 만든다. CAPTCHA + rate limit + 정리 잡 (§4.5.3 / 자식 §5.3 #10) 으로 봉인하지만, 운영 부담이 ADR-0003 의 `anonymous_users` 테이블 대비 ↑ (Auth MAU 요금 곡선까지 신경 필요).
- **가입 마찰 (자동 병합 금지 유지 비용)** — CEO Manual only 결정으로 동일 이메일이라도 provider 가 다르면 별개 계정. 사용자가 “다른 provider 로 한 번 더 가입” 시 자동 통합 UX 가 없으므로 별도 명시 통합 UX (자식 §5.3 #12) 가 필요.
- **마이그레이션 도구 SSOT 재정의** — Alembic 유지/폐기 결정 + 기존 마이그레이션의 Supabase `auth` 스키마 호환 검증 부담.
- **lock-in 거리** — `auth.users` + RLS 패턴은 Supabase 의존. 빠질 경로(self-hosted) 가 있긴 하나 운영 부담 ↑.
- **보안 런북 POL-AUTH-002 SSOT 이동** — refresh TTL 정본이 환경변수에서 Supabase Dashboard 로 이동. 회전·감사 절차 갱신 필요.

### 5.3 후속 (Accepted 시 자식 이슈)

| # | 자식 이슈 (제목 패턴) | 영향 범위 | 트리거 |
|---|---|---|---|
| 1 | `[SUPABASE][ADR-FOLLOWUP] AGENTS.md §4.7 (#4·#5·#7·#10) + docs/명세서-모순.md 갱신 (CFLT-001/003/005 supersede 정렬). §4.7 #9 (자동 병합 금지) 는 보존.` | DOCS | 본 ADR Accepted |
| 2 | `[SUPABASE][INFRA] Supabase 프로젝트 생성 + GitHub Actions preview branching + .env.example 변수 봉인` | DEVOPS / INFRA | 본 ADR Accepted + §7 사용자 결정 |
| 3 | `[SUPABASE][AUTH][MODEL] public.users / public.terms_consents / public.terms_consent_intents 재정의 + auth.users FK + Alembic vs Supabase CLI 결정 + AFTER UPDATE 트리거 (internal_signup + kakao_sync)` | DB / API | 본 ADR Accepted |
| 4 | `[SUPABASE][AUTH][HANDLER] FastAPI Supabase JWT 의존성 (get_current_user / require_anonymous_or_permanent_user / require_permanent_user) + RLS 정책 초안 + ADR-0003 §2.2 라우트 폐기` | API | 자식 #3 머지 후 |
| 5 | `[SUPABASE][AUTH][POC] Naver Custom OAuth/OIDC provider (custom:naver) PoC + Kakao Sync 후속 저장 트리거/webhook PoC` | API / DEVOPS | 본 ADR Accepted |
| 6 | `[SUPABASE][WEB] @supabase/supabase-js 클라이언트 + signInAnonymously (CAPTCHA token) + linkIdentity UX + 약관 모달 + terms-accept-intent/finalize 호출`. **rev4 봉인 (review #2/#1)**: anonymous → permanent 전환의 모든 provider 버튼 (Google · Kakao · Naver `custom:naver`) 은 `supabase.auth.linkIdentity({ provider })` **only**. `supabase.auth.signInWithOAuth({ provider })` 는 anonymous 세션을 새 provider-backed user 로 갈아치워 익명 도면·리포트 in-place claim 을 깨므로 **본 자식 이슈가 web 코드 측에서 사용 금지 lint/CI 가드를 봉인** (ESLint custom rule 또는 grep CI step). `POST /api/auth/terms-accept-finalize` 호출은 OAuth 콜백 복귀 후 trigger fire 관측 + 누락 알람용 **idempotent 후처리 only — 정합 path 가 아니므로 호출 누락 시 fallback 으로 우리 측에서 `terms_consents` 직접 insert 하지 않는다** (§2.3 trigger 가 SSOT). | WEB | 자식 #4 머지 후 |
| 7 | `[SUPABASE][SPEC] 명세서 4종 다음 리비전 — Supabase Auth + manual linking 반영 (CFLT-001/003/005 재정렬, §4.7 #9 보존)` | DOCS | 자식 #3·#4 머지 후 |
| 8 | `[SUPABASE][OPS] R2 유지 결정 명문화 + Supabase Storage 채택 가부 별도 ADR 또는 후속 이슈로 큐잉` | OPS | 본 ADR Accepted |
| 9 | `[SUPABASE][SEC] 보안 런북 POL-AUTH-002 정본 SSOT 이동 + Session lifetime / Inactivity / Refresh reuse Dashboard 운영 절차` | SEC / DOCS | 자식 #2 머지 후 |
| **10** | `[SUPABASE][SEC] 익명 abuse control — CAPTCHA/Turnstile + Supabase Anonymous rate limit + 익명 row 정리 잡 + Auth MAU 가시성 (§4.5.3 정본)`. **rev4 봉인 (review #3) — production rollout gate 4종 명문화**: 본 자식 이슈는 다음 4개 산출물을 **모두** 머지·운영 가시화한 시점에만 closed/done 처리한다. ① CAPTCHA/Turnstile site key 발급 + `signInAnonymously({ options: { captchaToken } })` 봉인 + Supabase Dashboard `Authentication → Attack Protection → CAPTCHA Protection` ON. ② Supabase Dashboard `Authentication → Rate Limits → Anonymous sign-ins` IP/시간당 N회 + Caddy/proxy 단 추가 rate limit. ③ `auth.users WHERE is_anonymous=true AND created_at < now() - interval '30 days' AND NOT EXISTS (관련 도면·리포트 FK)` 정리 잡 (Supabase Edge Function 또는 `apscheduler`). ④ Supabase Reports → Auth 의 MAU/DAU 미러링 + 임계치 알람 (Slack/Email). **4종 중 하나라도 미완이면 본 ADR §2.3 anonymous sign-in 흐름의 production 노출은 §9 변경 절차로 차단**. 개발/스테이징 시연 한정. | SEC / DEVOPS / API | 본 ADR Accepted. **§9 변경 절차에 의해 production rollout 의 전제조건.** |
| **11** | `[SUPABASE][AUTH][GUARD] require_permanent_user FastAPI 의존성 + RLS 술어 가드 적용 라우트 매핑 (상담/리드/리포트 저장·공유/결제) — AGENTS.md §4.7 #2 정합`. **rev4 봉인 (review #4) — conversion-only API 매핑**: 다음 라우트는 **반드시** `Depends(require_permanent_user)` 의존성으로 보호 (익명 Supabase JWT 통과 차단 + `public.terms_consents` 존재 술어 강제). ① **상담 신청** (`POST /api/consultations`, `PATCH /api/consultations/*`). ② **리드 생성·갱신·삭제** (`POST/PATCH/DELETE /api/leads/*`). ③ **리포트 저장·공유 링크 발급** (`POST /api/reports`, `POST /api/reports/*/share`, `PATCH /api/reports/*`). ④ **결제 / 청구 라우트** (`POST /api/payments/*`, `POST /api/subscriptions/*`). ⑤ **일정 예약 / 알림 설정** (`POST /api/appointments`, `POST /api/notifications/preferences`). **RLS 술어 가드 (DB 레벨 2차 가드)**: 위 라우트가 INSERT/UPDATE 하는 테이블의 RLS 정책에 `auth.jwt() ->> 'is_anonymous' = 'false'` 술어 + **현재 정본 약관 매칭** 술어 (rev7 정정 — Codex P2 line 390: 단순 `EXISTS terms_consents` 는 약관 개정 후 옛 동의 row 만 있는 사용자도 통과시키므로 금지. `policy_current_required_terms` 의 모든 (term_id, version) 셋 매칭 술어를 사용 — §4.3 의 정의 참조) 를 모든 write policy 에 추가. FastAPI 의존성과 RLS 가 동일 invariant 를 2중 봉인. **테스트 가드**: anonymous Supabase JWT 로 위 라우트 호출 시 403 + RLS 가 INSERT 거부됨을 보장하는 통합 테스트 의무 (`tests/auth/test_anonymous_blocked_on_conversion_routes.py`). | API / SEC | 자식 #4 머지 후 |
| **12** | `[SUPABASE][AUTH][UX] 이미 가입된 영구 user 의 추가 provider 통합 (Manual linkIdentity 명시 UX) + 감사 로그 + 보안 검토 — CEO 2026-06-01 결정으로 본 ADR 범위 외 분리` | WEB / API / SEC | 자식 #4 머지 후 |

> CEO 2026-06-01 결정 (Manual only) 으로 자식 #1 의 §4.7 #9 supersede 라인은 **제외** 한다. 자동 병합 금지 정책은 그대로. 자식 #12 는 “이미 가입된 user 의 추가 provider 통합” 의 UX/감사/보안만 다루며, 이 통합도 자동이 아닌 사용자 명시 호출 (`supabase.auth.linkIdentity()`) 기반이다.

---

## 6. Supersede 대상 목록 (정본)

본 ADR 이 Accepted 되는 시점에 다음 정본을 부분 supersede 한다. **본 ADR 이 Proposed 인 동안에는 supersede 가 발효되지 않는다.**

| 정본 위치 | 절 | supersede 범위 | 정본을 이동하는 곳 |
|---|---|---|---|
| `docs/adr/0001-stack-reevaluation.md` §4 (T3 — Neon Postgres) | 전체 | DB 호스팅을 Neon → Supabase Postgres 로 변경. branching·pooler·HNSW 패턴은 Supabase 대응으로 재정렬. | 본 ADR §2.1 + §4.1 |
| `docs/adr/0003-anon-user-and-sso.md` §2.1 (데이터 모델) | `users`, `anonymous_users`, `external_sso_accounts` 테이블 정의 | 우리 도메인은 `public.users` (auth.users FK) + `public.terms_consents` 만 남음. ENUM `external_sso_provider` 봉인 폐기. | 본 ADR §2.2 |
| `docs/adr/0003-anon-user-and-sso.md` §2.2 (OAuth 라우트 + 콜백) | 전체 | 자체 콜백 라우트 폐기, Supabase Auth + `supabase.auth.signInAnonymously` / `linkIdentity` 가 대체. **rev4 봉인 (review #5 + #2)**: anonymous → permanent 전환 OAuth 호출은 `supabase.auth.linkIdentity({ provider })` **only** — `signInWithOAuth({ provider })` 금지. Naver provider 식별자는 `'custom:naver'` (Supabase Custom OAuth/OIDC 봉인) — client call · callback 검증 · `auth.identities.provider` 비교 · DB trigger 조건 모두 동일 SSOT 문자열 사용. Built-in 처럼 `'naver'` 단독 호출 시 Supabase 측에서 정상 동작하지 않음. | 본 ADR §2.3 + §2.5 + §8 |
| `docs/adr/0003-anon-user-and-sso.md` §2.3 (자동 병합 금지) | 전체 | **보존 (supersede 안 됨)** — CEO 2026-06-01 결정 (Manual only). Supabase Auth `Allow account linking (automatic)` OFF. ADR-0003 §2.3 의 탈취 벡터 분석을 그대로 따른다. | 본 ADR §2.4 (rev3 확정) |
| `docs/adr/0003-anon-user-and-sso.md` §봉인표 (Refresh Token TTL 등) | refresh TTL · OAuth start route · state store · localStorage 키 · 헤더 이름 | Supabase 정본으로 일괄 이동. 환경변수 폐기 목록은 본 ADR §2.3 환경변수 표. | 본 ADR §2.3 + §4.4 |
| `AGENTS.md §4.7` (사용자 식별 정책) | #1~#10 중 #2 (전환 시점 OAuth) 는 유지, #3 (비밀번호 금지) 는 유지, **#9 (자동 병합 금지)** 도 **보존 (CEO 2026-06-01 결정)**. **#4 (provider ENUM 봉인)**, **#5 (Kakao Sync source 분리 — Auth Hook 으로 자동화 가능 여부)**, **#7 (localStorage 식별자)**, **#10 (Redis state store)** 가 본 ADR 의 영향권. | 자식 이슈 §5.3 #1 에서 §4.7 본문 직접 갱신 (#9 제외). | 본 ADR 봉인표 |
| `docs/명세서-모순.md` CFLT-001 (로그인 필수 vs 사전검토 허용) | Status | 본 ADR 채택 시점에 CFLT-001 의 “새 정본” 줄이 ADR-0003 + ADR-0004 로 갱신. | 자식 이슈 §5.3 #1 |
| `docs/명세서-모순.md` CFLT-003 (ENUM vs VARCHAR) | Status | ENUM 봉인 폐기로 row 가 Resolved → Reframed (Supabase Auth 가 provider 식별 정본). | 자식 이슈 §5.3 #1 |
| `docs/명세서-모순.md` CFLT-005 (localStorage 식별자) | Status | Supabase Anonymous Sign-In 의 JWT 가 localStorage 키를 대체. row 가 Resolved → Reframed. | 자식 이슈 §5.3 #1 |
| `docs/명세서-모순.md` (신규 CFLT-007) | — | **CEO 2026-06-01 결정 정본 row 신설** — “자동 병합 금지 유지 (Manual identity linking only). Supabase 채택 후에도 ADR-0003 §2.3 + AGENTS.md §4.7 #9 보존. 이미 가입된 user 의 추가 provider 통합 UX 는 자식 이슈 §5.3 #12 가 정본.” | 자식 이슈 §5.3 #1 |
| `docs/runbooks/security-policy.md` POL-AUTH-002 | 환경변수 정본 위치 | `apps/api/.env.example::AUTH_JWT_REFRESH_TTL_SECONDS` → `Supabase Dashboard → Authentication → Sessions → Session lifetime` + `Inactivity timeout` + `Refresh token reuse interval (rotation)`. **`JWT Expiry` 는 access token TTL 만 의미하므로 7일 정책의 SSOT 가 아니다.** | 자식 이슈 §5.3 #9 |
| `.github/workflows/neon-pr-branch.yml`, `.github/workflows/ci.yml` (`migrate-check`), `.github/workflows/deploy.yml` (`release-migrate`) | Neon 전제 | Supabase Branching 또는 Supabase CLI 기반 워크플로우로 1:1 재작성. | 자식 이슈 §5.3 #2 |

---

## 7. 미해결 — CEO 결정 + 사용자 콘솔 작업

본 ADR 이 Proposed → Accepted 되려면 다음 항목을 사용자(CEO 권한) 가 결정·이행해야 한다.

### 7.1 정책 결정 (CEO)

1. **Identity linking 정책 — ✅ 확정 (2026-06-01)**
   - **결정: Manual only.** Supabase Auth `Allow account linking (automatic)` = OFF, manual = ON.
   - ADR-0003 §2.3 + AGENTS.md §4.7 #9 (자동 병합 금지) 보존.
   - 이미 가입된 user 의 추가 provider 통합은 별도 UX/감사/보안 후속 이슈 §5.3 #12 로 분리.

2. **데이터 주권 / 리전 — 결정 대기**
   - Supabase 프로젝트 리전 — Seoul (`ap-northeast-2`) vs Singapore (`ap-southeast-1`).
   - CEO 권고 — Seoul (한국 사용자 PII 잔존, 약관·법무 측면 단순).

3. **Storage 전환 시점 — 결정 대기**
   - 본 ADR 은 R2 유지. Supabase Storage 채택은 별도 ADR.
   - CEO 결정 — R2 유지 vs 향후 Supabase Storage 검토 큐잉.

### 7.2 콘솔 작업 (사용자)

본 ADR 은 어떤 시크릿도 코드/문서/이슈/PR 본문에 적지 않는다. 사용자가 다음 콘솔 작업을 직접 수행한다.

1. **Supabase 프로젝트 생성** — 조직/리전(§7.1.2) 선택, 프로젝트 ref 발급.
2. **`SUPABASE_URL` / `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_JWT_SECRET` / `SUPABASE_PROJECT_REF` / Supabase Postgres `DATABASE_URL`** 발급 → 운영 시크릿 매니저 (or `.env`). **본 ADR / 자식 이슈 / PR 본문에는 변수명만 둔다.**
3. **Authentication → Providers → Google / Kakao 활성화** — 각 사 콘솔에서 client id/secret 발급, Supabase callback URL (`https://<project-ref>.supabase.co/auth/v1/callback`) 등록.
4. **Authentication → Providers → Naver (Custom OAuth)** — PoC (§4.5). 실패 시 fallback (§2.5).
5. **Authentication → Settings → Account Linking** — CEO 2026-06-01 결정 봉인:
   - **Manual linking = ON (무조건)** — §2.3 anonymous → permanent 흐름이 `supabase.auth.linkIdentity()` 에 의존.
   - **Automatic linking = OFF** — 자동 병합 금지 정책 보존 (ADR-0003 §2.3 + AGENTS.md §4.7 #9).
6. **Authentication → Settings + Sessions — 토큰 수명 정합** (§4.4 표대로):
   - **JWT Expiry** = Supabase 기본값(1h) 유지 (= access token TTL). 7일 정책 적용 대상 아님.
   - **Sessions → Session lifetime** = 7일 (604800s) — POL-AUTH-002 본래 의미.
   - **Sessions → Inactivity timeout** = 7일 이하로 정렬.
   - **Sessions → Refresh token reuse detection** = ON, reuse interval 기본값 유지.
7. **Authentication → Attack Protection → CAPTCHA Protection** — Turnstile / hCaptcha 선택 후 enable. site key + secret 발급 → 운영 시크릿 매니저. §4.5.3 / 자식 #10 정합.
8. **Authentication → Rate Limits → Anonymous sign-ins** — Supabase 기본값 확인 후 자식 #10 의 결정대로 조정 (예: IP 당 시간당 N회).
9. **GitHub Actions secrets / variables** 갱신 — `NEON_*` 시리즈를 `SUPABASE_*` 로 1:1 교체.

> 위 항목 중 어느 하나라도 미정이면 본 ADR 은 Accepted 될 수 없다. 본 ADR 을 들고 구현을 시작하는 자식 이슈 (§5.3 #2~#9) 도 동일하게 Accepted 를 의존.

---

## 8. 봉인 표 (Proposed)

| 키 | 값 | 비고 |
|---|---|---|
| Supabase 채택 표면 | DB + Auth | Realtime / Edge Functions / Storage 는 보류 (§2.1) |
| 인증 SSOT | `auth.users` | `public.users` 는 프로필 테이블 (FK only) |
| 비회원 사전검토 | `supabase.auth.signInAnonymously()` + `is_anonymous` flag | `anonymous_users` 테이블 폐기 |
| 자체 OAuth 콜백 | 폐기 | `supabase.auth.linkIdentity()` 가 대체 (비회원 사전검토 흐름에서는 `signInWithOAuth` 사용 금지 — §2.3) |
| Manual Linking | **ON (무조건)** — anonymous → permanent 흐름 (§2.3 / §2.4.1) | `supabase.auth.linkIdentity()` 가 활성화되어야 함 |
| Automatic Identity Linking | **OFF — CEO 2026-06-01 결정 (Manual only) 확정** | ADR-0003 §2.3 + AGENTS.md §4.7 #9 보존. 이미 가입된 user 의 추가 provider 통합 UX 는 자식 §5.3 #12 |
| 약관 동의 게이트 순서 (Google/Naver) | `linkIdentity()` **이전** — intent → OAuth → **DB trigger 가 atomic promote** → finalize ping (§2.3) | 약관 거부 시 `auth.users` 변형 없이 anonymous 세션 유지. 클라이언트 후속 commit 누락에도 trigger 가 consent row 보장 |
| 약관 동의 게이트 (Kakao) | Kakao Sync 약관 화면 자체가 게이트. 후속 저장은 `auth.users` AFTER UPDATE Postgres trigger 1순위, Database Webhook 2순위 (§2.3 / §4.5.2) | `before/after_user_created` Auth Hook 사용 금지 |
| Anonymous → permanent OAuth 호출 | **`supabase.auth.linkIdentity({ provider })`** 만 사용. `signInWithOAuth({provider})` 는 anonymous 세션을 새 user 로 갈아치우므로 **금지** | `provider` 값: `'google'`, `'kakao'`, `'custom:naver'` |
| Naver provider identifier | **`custom:naver`** (Supabase Custom OAuth 봉인) | 클라이언트·콜백·`auth.identities.provider`·DB trigger 조건 모두 동일 문자열 |
| FastAPI 의존성 가드 | `get_current_user` / `require_anonymous_or_permanent_user` / **`require_permanent_user`** 3종 분리 (§4.3) | 익명 JWT 가 permanent 라우트 통과 차단. RLS 술어 가드 중복 (자식 §5.3 #11) |
| 익명 abuse control | CAPTCHA/Turnstile + Anonymous rate limit + 익명 row 정리 잡 + Auth MAU 알람 (§4.5.3) | 자식 §5.3 #10. **production rollout 의 전제조건 (§9).** |
| OAuth provider 콘솔 | Supabase Dashboard | 사용자 콘솔 작업 (§7.2.3·4) |
| OAuth state store | Supabase | Redis `oauth_state:*` / `pending_signup:*` 폐기. Redis 자체는 채팅·세션 캐시로 잔존. |
| Access Token TTL | Supabase `Authentication → Settings → JWT Expiry` (기본 1h) | 7일 정책 대상 아님 |
| Session lifetime + Inactivity + Refresh reuse | Supabase `Authentication → Sessions` 3종 — POL-AUTH-002 정합 = 7일 | 환경변수 정본 폐기. SSOT 가 단일 “JWT Expiry” 가 아님을 §4.4 에서 봉인 |
| 약관 동의 모델 | `public.terms_consents` 유지, `user_id` → `auth.users(id)` | source 분리 보존 |
| 객체 스토리지 | Cloudflare R2 유지 | ADR-0001 §6 보존 |
| AI / LLM | SAM2 + OpenAI + LangChain 유지 | ADR-0001 §7 보존 |
| 앱 배포 | Lightsail 그대로 | Supabase 는 FastAPI / AI 서버 호스팅처 아님 |
| 마이그레이션 도구 | Alembic 유지 + Supabase CLI 로 `auth`·RLS 정책 관리 (잠정) | 자식 이슈 §5.3 #3 에서 최종 결정 |
| 한국 리전 | Seoul (`ap-northeast-2`) — 사용자 결정 대기 (§7.1.2) | — |

---

## 9. 변경 절차

- 본 ADR 은 CEO 정책 결정 (§7.1.2·§7.1.3) + 사용자 콘솔 작업 (§7.2) 이 모두 완료된 시점에만 Accepted 로 승급된다. 그 전까지 어떤 구현 PR 도 본 ADR 을 근거로 들 수 없다 (§7.1.1 identity linking 정책은 2026-06-01 확정).
- **Production rollout 의 전제조건**: 자식 §5.3 #10 (Anonymous abuse control — CAPTCHA + cleanup + rate limit) 가 머지되기 전에는 본 ADR §2.3 의 anonymous sign-in 흐름을 production 에 노출하지 않는다. 개발/스테이징 시연 한정.
- Naver Custom OAuth PoC (§4.5) 가 실패하면 §2.5 fallback 으로 ADR 본문을 보강하거나 본 ADR 을 supersede 하는 새 ADR 을 발행한다.
- ADR-0001 §4 (T3 Neon) supersede 는 본 ADR 의 정본 채택 시 ADR-0001 상단에 `supersededBy: ADR-0004 §2.1 (T3 만)` 짧은 줄을 추가하는 방식으로만 흔적을 남긴다 (ADR-0001 본문 직접 재작성 금지).
- ADR-0003 의 부분 supersede 도 마찬가지로 ADR-0003 상단에 `partiallySupersededBy: ADR-0004 §2.2·§2.3` 만 추가하고 본문은 보존. **§2.3 (자동 병합 금지) 는 supersede 대상에서 제외** (CEO 2026-06-01 결정).

---

## 10. 결정 트레일

| 시각 | 행위자 | 행위 |
|---|---|---|
| 2026-05-29 | 사용자 (CEO 권한 행사) | CMP-573 본문에서 Neon → Supabase 전환 발의. |
| 2026-05-29 | CTO (`4edca504-...`, CMP-573) | 본 ADR-0004 `Proposed` 초안 발행. ADR-0003 부분 supersede 범위 + 자동 병합 정책 옵션 A/B 회부 + Naver PoC 큐잉. |
| 2026-06-01 | CTO (`4edca504-...`, CMP-573) | rev2 — 보드 코드 리뷰 4건 반영. (1) Refresh/Session SSOT 를 `JWT Expiry` 단독 → `Session lifetime + Inactivity timeout + Refresh token reuse interval` 3종으로 분리 (§0/§1.3/§4.4/§6/§7.2/§8). (2) Anonymous → permanent 흐름의 Manual Linking enable 운영 조건을 §2.4.1 신설로 봉인 (옵션 A/B 무관). (3) Google/Naver 약관 동의 게이트를 `linkIdentity()` **이전** 으로 이동, intent → OAuth → commit 2-단계로 재설계, 약관 거부 시 anonymous 세션 유지 보장 (§2.3). (4) Kakao Sync 후속 저장 경로를 `auth.users` AFTER UPDATE Postgres trigger 1순위 + Database Webhook 2순위로 정정 (§2.3 표/§4.5.2). `before_user_created`/`after_user_created` Auth Hook 가정 제거. |
| 2026-06-01 | CEO (local-board 코멘트 5dca4b42, CMP-572 결정 기반) | **Identity linking 정책 확정 — Manual only.** 동일 verified email 자동 병합 허용 안 함. ADR-0003 §2.3 + AGENTS.md §4.7 #9 보존. 다중 provider 통합 UX/감사 로그/보안 검토는 별도 후속 이슈로 분리. |
| 2026-06-01 | CTO (`4edca504-...`, CMP-573) | rev3 — CEO Manual only 결정 반영 + Codex P1×4 / P2×1 처리. (1) §2.4 옵션 A/B 표 제거 → Manual only 단일 정책 확정 (§2.4 / §6 / §7.1.1 / §8). (2) §2.3 서버측 정합 강화 — `terms_consents` promotion 은 `auth.users` AFTER UPDATE 트리거가 원자적으로 수행, 클라이언트 finalize 는 idempotent 관측 가드로 격하 (Codex P1 line 174). (3) §2.3 라우트 표에서 `signInWithOAuth` → `linkIdentity` 봉인 (Codex P1 line 221). (4) §4.5.3 신설 — 익명 abuse control (CAPTCHA + cleanup + rate-limit + MAU 가시성), 자식 §5.3 #10 으로 큐잉, production rollout 의 전제조건 (Codex P1 line 149). (5) §4.3 — `get_current_user` / `require_anonymous_or_permanent_user` / `require_permanent_user` 3종 분리, 자식 §5.3 #11 (Codex P1 line 345). (6) §2.5 — Naver provider identifier 를 `custom:naver` 로 봉인, 트리거 조건도 동일 문자열로 정렬 (Codex P2 line 297). (7) §5.3 자식 이슈에 #10/#11/#12 추가. |
| 2026-06-01 | CTO (`4edca504-...`, CMP-573) | rev4 — 보드 코드 리뷰 5건 반영. **이번 리비전은 신규 정책 결정이 아니라 rev3 에서 점적으로 봉인한 5개 항목을 본 ADR 전반 (§0 / §2.3 / §5.3 / §6 / §8) 에 일관성 봉인 강화한 것**. (1) review #1 (Google/Naver 약관 동의 commit 봉인 강화) — §0 결정 요약 표에 “약관 동의 commit SSOT” 행 신설 (`auth.users` AFTER UPDATE Postgres trigger 가 identity link 성공을 commit boundary 로 원자 promote, 클라이언트 finalize 는 관측/재시도 idempotent only); §2.3 다이어그램 step 4 에 “정합 path 아님 — trigger 가 이미 보장” 한 단락 추가. (2) review #2 (anonymous upgrade 의 `signInWithOAuth` 금지 일관성) — §0 결정 요약 표에 “Anonymous → permanent 전환 OAuth 호출” 행 신설; §5.3 #6 web 자식 이슈 본문에 ESLint custom rule 또는 grep CI step 으로 web 코드 측 사용 금지 가드 봉인; §6 supersede 표 §2.2 행에 동일 봉인 명시. (3) review #3 (anonymous abuse control production gate 명문화) — §5.3 #10 자식 이슈 본문에 4종 산출물 모두 머지·운영 가시화 후에만 closed 처리 명문화, “4종 중 하나라도 미완이면 §9 변경 절차로 production 노출 차단”. (4) review #4 (conversion-only API permanent user guard 강제) — §5.3 #11 자식 이슈에 conversion-only 라우트 5종 (상담/리드/리포트 저장·공유/결제/일정 예약) 매핑 + RLS 술어 가드 (`auth.jwt() ->> 'is_anonymous' = 'false'` + `EXISTS terms_consents`) + anonymous JWT 통합 테스트 의무 봉인. (5) review #5 (Naver `custom:naver` provider identifier 봉인 일관성) — §0 결정 요약 표 OAuth provider 행에 `custom:naver` 1:1 봉인 명시; §6 supersede 표 §2.2 행에 동일 SSOT 문자열 봉인. |
| 2026-06-01 | CTO (`4edca504-...`, CMP-573) | rev5 — Codex PR #44 review threads 5건 처리 (P1×2 / P2×3). (1) **P1 line 152** — §2.3 step 1 의 `signInAnonymously()` 호출 다이어그램 안에 §4.5.3 + 자식 §5.3 #10 의 4종 abuse control gate (CAPTCHA + rate limit + 정리 잡 + MAU 알람) 를 직접 cross-ref + production 노출 차단 봉인 (§9). (2) **P2 line 165** — §2.3 step 2 intent body 의 `target_provider` 를 `'google'|'custom:naver'` 로 §2.5 Supabase Custom OAuth SSOT 와 1:1 정렬. (3) **P2 line 329** — §2.5 PoC 실패 fallback 에 anonymous ownership 보존 봉인 신설: `auth.admin.createUser()` 금지, 1순위 `supabase.auth.admin.updateUserById(anonId, ...)` 로 anon row 의 in-place 영구화 + `auth.identities` 직접 INSERT (SECURITY DEFINER), 2순위 도메인 FK 재할당 트랜잭션 + anon row 삭제. (4) **P2 line 259** — §2.3 환경변수 블록에 `SUPABASE_JWKS_URL` 1순위 신설 + `SUPABASE_JWT_SECRET` 을 2순위 legacy fallback 으로 격하 (HS256 → asymmetric JWKS 우선, 키 회전 무중단). (5) **P1 line 242** — §2.3 라우트 표 `/auth/{provider}/start` 행에 server-side intent enforcement 3중 방어 봉인: ① trigger 가 매칭 intent 없으면 `terms_consents` 미생성 → ② `require_permanent_user` + RLS 술어가 consent 없는 permanent user 403 → ③ (선택) `auth.users` BEFORE UPDATE trigger 가 intent 없으면 RAISE EXCEPTION. ①+② 가 운영 충분하면 ③ 생략 가능, 자식 §5.3 #3 PR 에서 결정. |
| 2026-06-01 | CTO (`4edca504-...`, CMP-573) | rev6 — rev5 push 직후 Codex PR #44 review threads 3건 처리 (P1×1 / P2×2). (1) **P1 line 424** — §4.5.2 PoC 실패 fallback 의 단순 클라이언트 POST 패턴 **금지** + server-side post-create reconciliation 3종 옵션 (주기 reconciliation 잡 / Send Auth Hook / Edge Function callback chain) 봉인. Kakao OAuth 콜백 시점에 `auth.users.is_anonymous=false` 가 이미 commit 되므로 탭 종료 / 네트워크 단절 시 `source='kakao_sync'` 영구 누락 위험을 차단. (2) **P2 line 208** — §2.3 에 No-session bootstrap 봉인 신설. `linkIdentity()` 는 활성 세션 전제 API 이므로 익명 세션이 없는 사용자 (localStorage 삭제, 직접 가입/상담 링크, 시크릿 모드) 가 provider 버튼 누르면 실패. 자식 §5.3 #6 web 자식 이슈가 `getSession() → 없으면 signInAnonymously({ captchaToken }) → linkIdentity()` 3단계를 봉인. (3) **P2 line 390** — §4.3 에 Postgres JWT claims 전파 봉인 신설. apps/api 는 PostgREST 가 아닌 SQLAlchemy + psycopg 직접 연결이므로 `auth.uid()` / `auth.jwt()` helper 가 자동 fire 안 함 → RLS 술어가 NULL 평가되어 우회 가능. `authenticated` role connection pool + 트랜잭션 시작부 `SET LOCAL role 'authenticated'; SET LOCAL "request.jwt.claims" = <JWT>` + `service_role` 별도 pool 분리 + 통합 테스트 의무 (`tests/auth/test_rls_claims_propagation.py`) 를 자식 §5.3 #4 PR 이 봉인. |
| 2026-06-01 | CTO (`4edca504-...`, CMP-573) | rev7 — rev6 push 직후 Codex 가 단 review threads 6건 (모두 P2) 처리. (1) **P2 line 286** — §2.3 환경변수 블록 `NAVER_OAUTH_*` + `OAUTH_STATE_REDIS_URL` / `OAUTH_STATE_TTL_SECONDS` 를 “폐기” → “PoC 결과 미확정 동안 보존” 으로 정정. (2) **P2 line 343 #1** — §2.5 Naver fallback 에 anon id ↔ OAuth state binding 봉인 신설 (Redis state store 패턴). (3) **P2 line 343 #2** — `supabase.auth.admin.linkIdentity()` 참조 제거, `SECURITY DEFINER` 함수로 `auth.identities` 직접 INSERT 봉인. (4) **P2 line 256** — `terms-accept-finalize` 가드를 `require_permanent_user_no_consent_check` (신규) 로 분리 → consent 누락 관측 가능. (5) **P2 line 229** — kakao_sync 트리거에 `kakao_sync_required_term_tags` 매칭 검증 의무 + 미매칭 시 `consent_promotion_audit` 별도 기록 봉인. (6) **P2 line 390** — `require_permanent_user` 와 RLS 술어를 `policy_current_required_terms` 의 모든 (term_id, version) 셋 매칭으로 정정 (단순 `EXISTS terms_consents` 금지). |
| _pending_ | CEO | §7.1.2 (리전) + §7.1.3 (Storage) 결정. |
| _pending_ | 사용자 | §7.2 콘솔 작업 + 시크릿 발급 + CAPTCHA 활성화. |
| _pending_ | CTO | 위 두 단계 완료 시 본 ADR 을 `Accepted` 로 승급. 자식 이슈 §5.3 #1~#12 일괄 발행. |

— 끝 —

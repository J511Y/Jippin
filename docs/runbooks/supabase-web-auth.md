# Runbook — Next.js Supabase Auth 전환 설계 (CMP-577)

- 작성자: Frontend Lead (`60ef2b0f`)
- 작성일: 2026-05-29
- 상태: **Design (Draft)** — 본 문서는 설계 정본이다. 실제 Supabase 콘솔 세팅 / 라이브 로그인 검증은 후속 트랙이 별도로 수행한다.
- 관련 이슈: **CMP-577** (`[SUPABASE][WEB] Next.js Supabase Auth client/session adapter 전환 설계`)
- 의존 트랙: Backend/Auth Supabase JWT 검증 트랙 (별도 CMP-* 이슈 — `apps/api` 가 Supabase JWKS 또는 공유 비밀로 access token 을 검증하는 흐름이 합의되어야 본 설계가 닫힌다)
- 정본 종속: `docs/adr/0003-anon-user-and-sso.md` (익명 + OAuth 정책), `docs/brief/CEO_PROJECT_BRIEF.md`, `AGENTS.md §4.4` (시크릿 봉인), **CMP-572 CEO 결정 — MVP linking 정책** (아래 §0.0 callout).
- 비목표: 실제 Supabase project URL / `anon` key / `service_role` key / OAuth client secret 의 본 문서 기재. 본 문서는 **변수명과 보관 위치만** 명시한다.

---

## 0.0 MVP linking 정책 (CMP-572 CEO 결정 — 2026-06-01)

> 출처: CMP-572 wake comment `1a0c6c7a-49cd-477d-a160-d1816db3c942` (board user `local-board`, 2026-06-01T00:33Z). 본 절은 인용이며 **본 runbook 의 모든 후속 절은 본 정책을 위반할 수 없다.**

1. **MVP 는 Manual identity linking 우선** — 모든 익명→실명 전환은 사용자가 명시적으로 OAuth 버튼을 누른 시점에만 발생한다.
2. **동일 verified email 기반 automatic identity linking 금지** — Supabase 콘솔의 "Link accounts with same email" / "Auto-link verified emails" 기능은 **OFF 로 봉인**한다. 켜진 상태로 라이브가 가면 본 정책 위반이며 ADR-0003 §2.3 위반과 동일.
3. **익명 사전검토 사용자의 conversion 경로 = `linkIdentity()` 기반 manual linking** — 상담 / 저장 / 공유 전환 진입은 §4.2.1 의 익명-분기 (linkIdentity) 로만 처리.
4. **이미 다른 user 에 연결된 provider identity 의 익명 세션 연결 시도** — 자동 병합 금지. §4.2.2 fallback ladder 가 정한 "기존 계정 로그인 + 데이터 이관 안내 UX" 분기를 강제. 침묵 fallback 또는 자동 merge 는 본 정책 위반.

본 정책의 enforcement 분담:

- **Web 트랙 (본 runbook)** — `linkIdentity()` 만을 manual conversion 경로로 사용, fallback ladder 의 "기존 계정 로그인 + 이관" 분기 UI 제공, raw `signInWithOAuth` 를 익명 세션에서 호출 금지 (기존 실명 user 또는 미로그인 사용자만 허용).
- **Supabase 콘솔 트랙** — Account Linking = **manual only**, Email/Phone provider OFF, Identity Linking 기능 ON, "verified email auto-link" 비활성. §8 입력 항목 표가 SSOT.
- **Backend/Auth 트랙** — 콘솔 설정이 잘못 켜져 있어도 같은 user 가 두 identity 를 보유하게 되는 경우를 backend webhook / DB invariants 로 거부.

위 셋 중 하나라도 깨지면 정책 위반이며, 위반을 발견한 트랙은 즉시 본 이슈 (또는 CMP-572) 에 코멘트 + 라이브 차단.

---

## 0. TL;DR

| 항목 | 결정 |
|---|---|
| **세션 1차 소스** | Supabase Auth session (`supabase.auth.getSession()`). 자체 JWT / 자체 메모리 토큰 / 자체 `jippin_session` 쿠키 폐기. |
| **클라이언트 라이브러리** | `@supabase/supabase-js` + `@supabase/ssr` (Next.js 16 App Router · Edge proxy / Route Handler / Server Component cookie 통합). |
| **익명 흐름** | `supabase.auth.signInAnonymously()` — 페이지 첫 진입 시 세션이 없으면 1회 호출. Supabase user `id` 가 익명/실명 user 의 단일 키. **단계적 폐기.** 기존 `localStorage.jippin_anonymous_user_id` 와 `POST /auth/anonymous-users` 는 **ADR-0003 §2 supersede 가 Accepted 되기 전까지 코드에서 제거하지 않는다** (§9 Phase 표 / [§6 Phase Gate](#6-트랙-간-의존--연결점) 참조). Phase 1 에서는 dual-write 로 양쪽을 동시에 갱신하고 도면/리포트 claim 경로를 끊지 않는다. |
| **전환 시점 CTA** | 익명 세션 존재 시 1) `supabase.auth.linkIdentity({ provider })` 시도 → 2) 실패(provider identity 가 다른 user 에 이미 연결)면 [§4.2.2 fallback ladder](#422-linkidentity-실패-fallback) 진입: 사용자에게 "익명 데이터를 기존 계정으로 이전하시겠습니까?" 명시 confirm → 수락 시 익명 데이터 merge 큐 enqueue + `supabase.auth.signOut()` → `signInWithOAuth`. 익명 세션이 아닌 비로그인 진입은 곧바로 `signInWithOAuth({ provider, options: { redirectTo } })`. 두 경로 모두 Supabase 가 hosted login page / provider redirect 를 owner 로 가진다. |
| **OAuth provider** | UI 노출 정본은 `google`, `kakao`, `naver` (ADR-0003 봉인). Supabase native = `google` + `kakao` (Supabase Auth 가 Kakao 를 built-in provider 로 지원). **Naver 만** Supabase Custom OAuth Provider 의 **OAuth2 모드 (not OIDC)** 로 등록하고 SDK 호출 시 `custom:naver` 식별자로 매핑한다 — UI provider id → Supabase provider id 변환은 [§4.2.3 provider mapping](#423-provider-id-매핑) 표 단일 SSOT 가 owner. Naver = OAuth2 봉인의 근거는 [§4.3.1](#431-naver--custom-oauth2-not-oidc-봉인-cmp-584). |
| **OAuth callback route** | provider redirect URL 은 `/auth/success` 가 아니라 **`/auth/callback?next=<원래 목적지>`**. 콜백 Route Handler 가 `exchangeCodeForSession(code)` 로 PKCE 코드를 세션 쿠키로 교환한 뒤 `next` 로 302. **failure redirect 는 query 비상속 fresh URL + sanitize 된 `reason` 만** — `?code=…` 가 `/auth/failure` URL / log / Referer 에 절대 남지 않게 한다. merge intent 쿠키 `jippin_merge_intent` 가 있으면 commit 후 1회용 expire. Supabase 콘솔 redirect allow list 도 `/auth/callback` 기준으로 등록한다 ([§4.7](#47-oauth-callback-route--exchangecodeforsession)). |
| **FastAPI 호출** | `Authorization: Bearer <session.access_token>` 헤더 주입. 자체 refresh 인터셉터 폐기 — Supabase SDK 의 토큰 자동 갱신을 신뢰. **API 측 anonymous 거부 계약.** Conversion-only 엔드포인트(상담 저장 / 리드 / 리포트 발급)는 token 의 `is_anonymous` claim 이 `false` 임을 강제하거나 backend 측 user state 로 거부한다 ([§4.4 anonymous gating contract](#44-anonymous-gating-contract-conversion-only-엔드포인트)). |
| **Edge proxy 가드** | `proxy.ts` 는 `jippin_session` 쿠키 대신 `@supabase/ssr` 의 `createServerClient` 로 세션을 읽고, anonymous user 도 비보호 경로(`/app/pre-review`)에 들어올 수 있게 한다. |
| **Kakao Sync 동의 audit** | Supabase hosted OAuth 가 사용자 동의 화면 owner. **Kakao 감지는 `app_metadata.provider` 단독 의존 금지** (익명→link 케이스 누락) — `lib/supabase/identities.ts` 의 `detectNewlyLinkedProvider(user, intendedProviderCookie)` 가 (1) `jippin_oauth_provider` flow context 쿠키 + (2) `user.identities[]` 두 신호로 판정 (§4.5.2.1). callback 이 `POST /auth/terms/kakao-sync` 로 보내는 payload 는 **`provider_access_token: session.provider_token`** (provider OAuth access token — `id_token` 아님). backend 는 이 토큰으로 Kakao `/v2/user/scopes` 재호출 후 `terms_consents.source='kakao_sync'` insert (§4.5.2.2). 실패 시 reconcile 잡 fallback. |
| **클라이언트 SSOT** | `apps/web/lib/supabase/` 디렉터리 신설 — `browser.ts`, `server.ts`, `proxy.ts` 3분할 + provider mapping (`providers.ts`). axios 인터셉터는 이 SSOT 가 발급한 token 만 읽도록 단방향 의존. |

---

## 1. 현 웹 인증 코드 인벤토리 (origin/dev `ad57caa1` 기준)

| 경로 | 책임 | 전환 후 처분 |
|---|---|---|
| `apps/web/proxy.ts` | `/app/consult`, `/app/leads`, `/app/reports` 진입 시 `jippin_session` 쿠키 존재 여부 가드. | **재작성.** Supabase 세션 기반으로 변경. matcher 와 prefix 정책은 유지. |
| `apps/web/lib/auth-token.ts` | 메모리 access token 저장 + listener. | **폐기.** Supabase SDK 가 세션을 관리. |
| `apps/web/lib/api-client.ts` | axios + `/auth/refresh` 401 인터셉터 + `Bearer <메모리 토큰>` 주입. | **재작성.** Supabase session 에서 token 을 읽어 주입. 401 refresh 큐 삭제 (SDK 가 처리). `withCredentials` 도 제거 가능 (쿠키 의존 종료). |
| `apps/web/lib/anonymous-user.ts` | `POST /auth/anonymous-users` 로 익명 ID 발급 + `localStorage.jippin_anonymous_user_id` 캐싱. | **Phase 1 유지 (dual-write).** ADR-0003 §2 가 정본인 동안에는 Supabase 익명 sign-in 과 병행해서 호출하여 기존 도면/리포트 claim 경로가 끊기지 않게 한다. **Phase 2 폐기** — ADR-0004 (Supabase Auth + anon 정책) Accepted 또는 ADR-0003 supersede 자식 이슈 완료 시점에 본 파일과 localStorage 키를 함께 제거한다 ([§9 Phase 표](#9-phase-별-전환-순서)). |
| `apps/web/lib/api-base-url.ts` | `NEXT_PUBLIC_API_BASE_URL` fallback. | **유지.** Supabase 와 무관. |
| `apps/web/lib/api/error.ts` | 백엔드 에러 정규화. | **유지.** `apiClient` 재작성 후에도 그대로 호출 가능. |
| `apps/web/app/(auth)/login/page.tsx` | "집핀 로그인" 소개 + provider 버튼 placeholder. | **부분 유지.** 카피만 갱신 (§5.2). 페이지 구조는 동일. |
| `apps/web/app/(auth)/login/login-buttons.tsx` | `GET /auth/{provider}/start?return_url=...&anonymous_user_id=...` 로 브라우저 redirect. | **재작성.** 클라이언트는 Supabase SDK 를 직접 호출하지 않고 `GET /auth/oauth/start?provider=<ui>&intent=<link\|signin>` BFF 로 navigate (§4.2.1). BFF 가 `linkIdentity` / `signInWithOAuth` 분기 + flow context 쿠키 발급 + 서버측 OAuth URL 생성 + 302. `linkIdentity` 실패 fallback ladder (§4.2.2) 는 클라이언트 모달 후 BFF 의 `?intent=link-merge` 모드로 재진입하여 merge intent + signOut + signInWithOAuth 를 서버측에서 일괄 처리. `redirectTo` 는 항상 `/auth/callback?next=...` 절대 URL. anonymous_user_id 쿼리는 Phase 2 시점에 폐기 (Phase 1 는 dual-write 위해 호출 유지). |
| `apps/web/app/auth/test/page.tsx` + `auth-test-panel.tsx` | CMP-557 통합 검증 페이지 — anonymous ID / `/auth/me` / link / terms / logout. | **재작성.** Supabase session / linkIdentity / sign-out 으로 교체. 약관 동의는 백엔드에 남기되 호출 방식은 §4.4 참조. |
| `apps/web/app/layout.tsx` | 루트 layout + `Providers` 마운트. | **유지.** `Providers` 내부에 Supabase session listener 만 추가. |
| `apps/web/lib/providers.tsx` | React Query Provider. | **확장.** Supabase Session Provider 를 wrap. |
| `apps/web/.env.example` | `NEXT_PUBLIC_API_BASE_URL`, success/failure URL, `AUTH_COOKIE_NAME`. | **확장.** Supabase env 추가 (§3). `AUTH_COOKIE_NAME` 은 Supabase 의 자체 쿠키 이름 정책으로 대체되며 표기 변경. |

> **추가 폐기 후보 (API 측 — Backend/Auth 트랙 owner).** `POST /auth/anonymous-users`, `GET /auth/{provider}/start`, `GET /auth/callback/{provider}`, `POST /auth/refresh`, `POST /auth/logout`, `POST /auth/sso-accounts/{provider}/link`. Backend 트랙이 ADR-0003 의 OAuth 핸들러를 Supabase 로 대체하는 별도 이슈에서 판단한다. **본 웹 트랙은 폐기를 강제하지 않는다.** 단지 웹이 더 이상 호출하지 않을 뿐이며, API 측 cleanup 일정은 트랙 간 합의 후 별도 이슈로 끊는다.

---

## 2. 패키지 / 디렉터리 도입

### 2.1 의존성 (Phase 1 (a) 자식 이슈 설치 예정 — 본 절은 설계 정본)

> **상태 (review item 5 정합).** 본 절은 **설계 의도** 이며 `apps/web/package.json` 에 두 패키지가 아직 추가되지 않았다. 실제 install 은 Phase 1 (a) 자식 이슈 (Supabase 클라이언트 도입 / SSR cookie adapter — CMP-580 계열) 에서 수행한다. 본 runbook 의 §2.2 / §4.1 / §4.2 의 의사 코드는 모두 본 패키지가 설치된 시점을 가정한 설계이며, Phase 1 (e) 코드 (provider 화이트리스트 + Naver 어댑터) 는 Supabase SDK 를 직접 호출하지 않으므로 본 패키지 부재와 무관하게 supabaseScopeed pure 모듈로 봉인되어 있다.

`apps/web/package.json` `dependencies` 에 **Phase 1 (a) 시점에** 추가:

```json
"@supabase/supabase-js": "^2.45.0",
"@supabase/ssr": "^0.5.0"
```

> 정확한 minor 는 설치 시점에 lockfile 로 봉인한다. Major 만 `^2` / `^0` 으로 명시. Next.js 16 App Router 와 `@supabase/ssr` 의 cookie 통합은 v0.5+ 가 안정 라인. 본 install PR 이 머지되기 전까지는 본 runbook 의 `@supabase/*` import 가 등장하는 코드 블록은 모두 의사 코드로 취급한다.

### 2.2 신설 SSOT 디렉터리

```
apps/web/lib/supabase/
├── browser.ts       # createBrowserClient — 클라이언트 컴포넌트 / hooks 용
├── server.ts        # createServerClient — Server Component / Route Handler 용 (cookies() 통합)
├── proxy.ts         # createServerClient(요청·응답 cookies 핸들러) — proxy.ts 가 import
├── env.ts           # NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY 단일 readers
├── providers.ts     # ADR UI provider id (google|kakao|naver) → Supabase provider id 매핑 SSOT
├── identities.ts    # user.identities[] + flow context cookie 로 신규 link provider 판정 (§4.5.2.1)
└── session.ts       # SessionUser 타입 정의 + 익명/실명 구분 헬퍼
```

추가로 다음 Route Handler / 헬퍼가 신설된다:

- `apps/web/app/auth/callback/route.ts` — OAuth provider redirect 1차 수신점 + `exchangeCodeForSession` + merge intent commit + Kakao Sync audit (§4.7).
- `apps/web/app/auth/oauth/start/route.ts` — OAuth 진입 BFF. provider 검증 + `jippin_oauth_provider` flow-context 쿠키 발급 + (필요 시) merge intent 쿠키 발급 + Supabase `signInWithOAuth({ skipBrowserRedirect: true })` 로 받은 URL 로 302 (§4.2.1 cookie 발급 단계 / §4.2.2 ladder step b·c).
- `apps/web/lib/safe-redirect.ts` — `isSafeNext(next)` allow list 검증 (§4.7.2).

- 모든 외부 호출은 위 디렉터리의 모듈 중 하나를 import 한다. `@supabase/supabase-js` / `@supabase/ssr` 직접 import 는 `lib/supabase/` 외에서 금지 (lint rule 후속 추가 권장).
- env reader 를 단일 모듈로 격리하는 이유: `NEXT_PUBLIC_*` 누락 시 SSR / 클라이언트 모두에서 동일한 명시적 에러를 던지도록 한다. fallback 금지 (라이브 URL/key 가 미설정이면 fail loud).
- provider mapping 을 SSOT 로 분리하는 이유: Naver 처럼 Supabase native 가 아닌 provider 는 `custom:naver` 형태가 되며, UI · 텔레메트리 · 분석 코드는 여전히 ADR-0003 의 `naver` 식별자를 그대로 쓰도록 변환 경계를 한 곳에 둔다.

### 2.3 SSR · 클라이언트 분리 원칙

- **Browser client** (`browser.ts`) — 매 호출마다 새 인스턴스를 만들지 말고 lazily 한 번만 생성. React Query 와 동일한 lifecycle.
- **Server client** (`server.ts`) — 매 요청에서 `cookies()` 핸들을 받아 새 인스턴스를 만든다. 토큰을 모듈 스코프에 캐시하면 요청 간 누설 위험.
- **Proxy / Edge client** (`proxy.ts`) — Next.js 16 proxy 의 `request.cookies` / `response.cookies` 시그니처에 맞춘 어댑터. `@supabase/ssr` 의 `createServerClient({ cookies: { get, set, remove } })` 패턴 그대로.

---

## 3. 환경변수 초안

`apps/web/.env.example` 에 추가 (실 값은 `.env.local` / 운영 시크릿 매니저).

| 변수 | 위치 | 책임 | 비고 |
|---|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | `apps/web/.env.example` | Supabase project URL. 브라우저 노출. | `https://<project-ref>.supabase.co` 형태. |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | `apps/web/.env.example` | Supabase `anon` (publishable) key. 브라우저 노출. | `service_role` key 는 절대 웹에 두지 않는다. |
| `SUPABASE_SERVICE_ROLE_KEY` | `apps/api/.env.example` (참조용 — 본 웹 트랙에서는 사용 금지) | API 서버 전용 admin key. | **웹은 import 금지.** Backend/Auth 트랙이 별도 봉인. |
| `SUPABASE_JWT_AUDIENCE` | `apps/api/.env.example` (참조) | API 측 JWT 검증 audience. | 웹은 무관. |
| `NEXT_PUBLIC_FRONTEND_AUTH_SUCCESS_URL` | 기존 유지 | **사용 변경.** 더 이상 `signInWithOAuth({ redirectTo })` 의 직접 인자로 쓰지 않는다. 인자는 항상 `/auth/callback?next=<SUCCESS_URL>` 절대 URL. SUCCESS_URL 자체는 callback 이후 302 목적지로만 쓰인다. | ADR-0003 정합. |
| `NEXT_PUBLIC_FRONTEND_AUTH_FAILURE_URL` | 기존 유지 | OAuth 실패 시 redirect 표시 경로. callback Route Handler 가 `exchangeCodeForSession` 실패 시 이 URL 로 302. | 정본은 `apps/api/.env.example`. |
| `NEXT_PUBLIC_FRONTEND_AUTH_CALLBACK_URL` | **신설(선택)** | OAuth provider 가 redirect 해 오는 절대 URL. 미설정 시 코드가 `new URL('/auth/callback', window.location.origin)` 로 합성한다. Vercel preview 처럼 origin 이 동적인 환경에서 명시 봉인이 필요할 때만 설정. | Supabase 콘솔 redirect allow list 에도 동일 값을 등록한다. |
| `AUTH_COOKIE_NAME` | **폐기 후보 (Phase 2)** | 기존 `jippin_session` 가드용. Supabase 가 자체 쿠키 (`sb-<project-ref>-auth-token`) 를 발급하므로 web 쿠키 이름은 더 이상 의미가 없다. | Phase 1 에서는 dual-write 호환을 위해 라인을 주석으로 유지하고, proxy.ts 재작성 PR 머지 시점에 라인 제거. |
| `NEXT_PUBLIC_API_BASE_URL` | `apps/web/.env.example` (기존) | **server-to-server** 백엔드 base URL. Next.js SSR/Route Handler 의 server-side `fetch` 가 사용. Docker compose 의 내부 host (`http://api:8000`) 도 허용. | 브라우저 도달성 보장 안 함. browser-reachable 이 필요한 경로는 `API_PUBLIC_BASE_URL` 사용. |
| `API_PUBLIC_BASE_URL` | `apps/web/.env.example` (**신설 — CMP-584 round-3**) | **Browser-reachable** 백엔드 base URL (server-only env, `NEXT_PUBLIC_` prefix 없음). `/auth/oauth/start` 같은 BFF 가 302 `Location` 으로 사용. 미설정 시 `NEXT_PUBLIC_API_BASE_URL` 로 fallback 하되 Docker 내부 hostname (`api:`, `web:`, `app:`) 이면 500 `OAUTH_BASE_URL_MISCONFIGURED`. | `apps/web/lib/api-base-url.ts::publicApiBaseUrl()` 단일 SSOT. compose 환경에서는 별도 값 (예: `http://localhost:8000`) 으로 봉인. |

> 본 트랙은 변수명만 봉인한다. 실제 콘솔 세팅, redirect URL 화이트리스트, provider client ID / secret 입력은 Supabase 콘솔 운영자가 수행한다 (블로커 발생 시 §8).

---

## 4. 흐름 설계

### 4.1 익명 sign-in 호출 시점

- 진입 페이지: 모든 `app/*` 라우트의 첫 paint 직전. App Router 의 Root `layout.tsx` 에서 mounting 되는 client provider 가 다음을 수행:

  ```
  1) §4.1.1 OAuth-in-progress guard 확인 → guard 활성이면 anonymous bootstrap skip 후 listener 만 등록
  2) supabase.auth.getSession() → 세션 있음? then no-op
  3) 세션 없음 → supabase.auth.signInAnonymously()
  4) onAuthStateChange listener 등록 → React Query / UI 가 의존하는 SessionContext 업데이트
  ```

- **호출 보장.** 익명 sign-in 은 페이지 첫 진입 1회만 호출되어야 한다 (Strict mode, refresh, navigation 모두에서). 정합을 위해:
  - `getSession` 결과를 await 한 뒤에만 `signInAnonymously` 를 호출.
  - SSR 측 `server.ts` 에서도 동일하게 `getSession` 만 수행하고 익명 발급은 **클라이언트에서만** 한다 (Supabase 의 anonymous user 는 client SDK 가 anon key 로 발급하는 것이 표준).
  - SSR 단계에서 세션이 없는 사용자는 빈 user 컨텍스트로 렌더링되고, 클라이언트 hydration 직후 익명 세션이 생성된다.

#### 4.1.0 익명 bootstrap singleton — 동시 호출 race 차단

> **문제.** React 18 Strict mode 의 double-mount, 동시 페이지 전환, 또는 multi-tab 환경에서 SessionProvider 가 짧은 시간 안에 여러 번 mount 되면 `getSession` 이 모두 빈 결과를 반환한 직후 `signInAnonymously` 가 동시에 여러 번 fire 한다. 각 호출이 별개의 Supabase anonymous user 를 만들어 사용자의 pre-review 산출물 ownership 이 여러 anon id 로 갈라진다 (review item 6).

해결책 — `apps/web/lib/supabase/anonymous-bootstrap.ts` 가 **module-scope singleton promise** 를 owner 로 갖는다:

```ts
// apps/web/lib/supabase/anonymous-bootstrap.ts — module scope (브라우저 1 회 로드 = 1 인스턴스)
import type { SupabaseClient, Session } from '@supabase/supabase-js';

let inFlight: Promise<Session | null> | null = null;

export function ensureAnonymousSession(supabase: SupabaseClient): Promise<Session | null> {
  // 1) 이미 시도 중인 동일 promise 가 있으면 그것만 await — 동일 tick 안 중복 호출 흡수.
  if (inFlight) return inFlight;

  inFlight = (async () => {
    try {
      // 2) 다른 mount 가 만든 세션이 이미 있는지 race-free 확인.
      const { data: { session } } = await supabase.auth.getSession();
      if (session) return session;

      // 3) §4.1.1 OAuth-in-progress guard 가 활성이면 익명 발급 skip.
      if (typeof window !== 'undefined' &&
          window.sessionStorage.getItem('jippin_oauth_in_progress') === '1') {
        return null;
      }

      // 4) 실제 발급 — singleton 이므로 동시 호출 1 회로 수렴.
      const { data, error } = await supabase.auth.signInAnonymously();
      if (error) throw error;
      return data.session;
    } finally {
      // 5) 발급이 끝났든 실패했든 다음 시도가 가능하도록 lock 해제. 단, 1초 debounce 로 같은
      //    paint cycle 안 재시도는 막는다 (실패 후 무한 retry loop 방지).
      setTimeout(() => { inFlight = null; }, 1000);
    }
  })();
  return inFlight;
}
```

- SessionProvider 의 useEffect 는 `ensureAnonymousSession(supabase)` 만 호출한다 — 자체적으로 `getSession` / `signInAnonymously` 를 직접 호출하지 않는다.
- module-scope 변수이므로 같은 브라우저 탭의 모든 SessionProvider mount 가 동일 promise 를 공유. 다른 탭은 자체 module scope 이므로 별도 promise 를 갖지만, 탭마다 1 익명 user 는 정합 (multi-tab 시 backend 가 매핑 — Phase 2 ADR-0004 작업 범위).
- `onAuthStateChange` listener 안에서도 자체적으로 anonymous sign-in 을 호출하지 말고 본 헬퍼만 호출.
- 1초 debounce 는 `inFlight` 해제 후 잘못된 mount 가 즉시 또 fire 하는 corner case 를 막는다. paint cycle 안 race 흡수 + 사용자가 retry 버튼을 누르는 명시적 요청은 1초 후 통과.

##### singleton ↔ OAuth guard ↔ callback hop — 일관 설명 (review item 6 강화)

세 메커니즘이 협력하여 "익명 user 가 임의 시점에 중복 발급되거나, OAuth 왕복 중 추가 익명 세션이 끼어들지 않는다" 를 보장한다:

| 메커니즘 | 위치 | 책임 | 다른 메커니즘과의 관계 |
|---|---|---|---|
| singleton promise | §4.1.0 `lib/supabase/anonymous-bootstrap.ts` | 동시 호출 race 흡수 (tick scope). | 본 헬퍼의 (3) 단계에서 `jippin_oauth_in_progress` flag 활성이면 익명 발급 skip. |
| `sessionStorage.jippin_oauth_in_progress` guard | §4.1.1 `/auth/redirect` set + `/auth/callback-done` clear | OAuth 왕복 windows (수십초~수분) 동안 익명 bootstrap 정지. | singleton 이 매 호출 시 이 flag 를 1차 검사. callback-done page (§4.7.4 (d)) 가 clear. |
| callback hop chain | §4.7.4 (b) `/auth/oauth/start → provider → /auth/callback → /auth/callback-done → safeNext` | 각 hop 이 다음 hop 으로 안전하게 인계 (cookie / next / guard). | callback-done 가 guard clear 직후 router.replace 로 navigate — singleton 이 다음 mount 에서 정상 bootstrap. |

요약: singleton 이 **공간적** race (동시 호출) 를 흡수하고, guard 가 **시간적** race (OAuth 왕복 동안) 를 흡수하며, callback hop chain 이 두 메커니즘의 set/clear 시점을 정합으로 묶는다. 셋 중 하나가 빠지면 중복 익명 user / 끊어진 ownership 이 발생한다.


#### 4.1.1 `oauth_in_progress` guard — OAuth 왕복 중 bootstrap 중지

> **문제.** §4.2.2 fallback ladder 의 "예, 옮기고 로그인" 분기는 `signOut() → signInWithOAuth()` 순으로 진행된다. signOut 직후 SessionProvider 의 anonymous-bootstrap (`getSession` 결과가 비어 있으니 `signInAnonymously` 호출) 이 즉시 fire 하면, OAuth redirect 가 시작되기 직전에 새 익명 세션이 만들어져 ladder step c (`signInWithOAuth`) 가 또 다른 anonymous-link 사이클을 트리거할 수 있다. 결과적으로 merge intent 가 가리키는 `from_anon_user_id` 와 callback 시점의 anonymous user id 가 어긋나 데이터 이전이 끊긴다.

해결책 — **세션 변경에 둔감한 guard 플래그** 를 둔다:

- **저장 위치.** `sessionStorage.jippin_oauth_in_progress` (탭 한정 + 새로고침 생존). `localStorage` 는 다른 탭으로 누설되므로 부적합. 쿠키는 사용하지 않는다 (서버 side 의사결정에 들어가지 않음).
- **set 시점 — BFF.** `apps/web/app/auth/oauth/start/route.ts` 가 302 응답에 small inline HTML 또는 별도 redirect-via-page 를 통해 `sessionStorage.setItem('jippin_oauth_in_progress', '1')` 를 실행한 뒤 OAuth URL 로 navigate. 또는 BFF 가 302 직전에 `Location: /auth/redirect?to=<encoded-oauth-url>` 로 보내고, `/auth/redirect/page.tsx` 가 `useEffect` 에서 flag set 후 `window.location.assign(to)` 를 수행. **server-only 302 만으로는 sessionStorage 를 만질 수 없으므로 client-side 한 단계가 반드시 필요**하다.
- **clear 시점.** (1) callback Route Handler 의 redirect 목적지가 항상 `/auth/callback-done?next=<safeNext>` (small client page) 로 들어가고, 이 page 가 `sessionStorage.removeItem('jippin_oauth_in_progress')` **한 키만** 제거한 뒤 `next` 로 navigate. (2) 안전망으로 SessionProvider mount 시 flag 의 timestamp 가 10분 초과면 강제 clear.
- **금지 — `Clear-Site-Data` 헤더 (review item 2).** callback 응답에 `Clear-Site-Data: "storage"` 또는 `"*"` 를 부착하면 같은 origin 의 모든 storage 가 비워진다. Phase 1 dual-write 가 의존하는 `localStorage.jippin_anonymous_user_id` / Supabase 의 `sb-<ref>-auth-token` / React Query persist cache 까지 함께 사라져 사용자 데이터 / 세션이 손실된다. callback 의 cookie 정리는 §4.7.1 의 `response.cookies.set(..., { maxAge: 0 })` (개별 키 지정) 로만 한다. guard 정리도 위 callback-done page 의 `sessionStorage.removeItem` 단일 키 호출로 한정.
- **bootstrap 측 확인.** SessionProvider 가 `getSession()` 호출 전에 `sessionStorage.getItem('jippin_oauth_in_progress') === '1'` 이면 anonymous bootstrap 을 **완전히 skip** 하고 onAuthStateChange listener 만 등록. callback 이후 첫 navigation 에서 flag 가 clear 되어 다음 bootstrap (보통은 새 실명 세션이 이미 있으므로 no-op) 이 fire.
- **race-free 보장.** signOut 이 onAuthStateChange 를 통해 SessionProvider 의 callback 도 trigger 한다. 이 callback 안에서 다시 `signInAnonymously` 가 fire 하지 않도록, listener 콜백도 동일 guard 를 본다.

쉽게 깰 수 있는 함정:

- `localStorage` 로 저장하면 다른 탭의 SessionProvider 가 영영 anonymous bootstrap 을 못해 데드락. **반드시 `sessionStorage`** 사용.
- 사용자가 OAuth 진행 중 탭을 닫고 새 탭에서 들어오는 경우 — guard 가 없으므로 새 탭은 정상적으로 익명 sign-in. 본래 탭의 merge intent 는 callback 도착 시점에 cookie 가 살아 있는 한 정상 commit.
- guard 가 10분을 넘기면 stale 로 간주하고 강제 clear — 사용자가 OAuth provider 화면에서 멈춰 있는 동안 익명 흐름이 영구 차단되지 않도록 한다.

- **fail-soft + API 계약 정합 (review item 6).** `signInAnonymously` 실패 / Supabase 도달 불가 시 두 가지 행동을 동시에 적용한다:
  - **(A) Phase 1 동안 backend 가 legacy 익명 ID 호출을 받아들인다.** Phase 1 dual-write 가 살아 있는 동안 `/app/pre-review` 의 core run 호출 (`POST /pre-review/run` 등 공개/사전검토 분류) 은 **`Authorization: Bearer <supabase>` 가 없어도 `x-jippin-anon-id: <legacy uuid>` 헤더만으로 진입**할 수 있다. backend 의 §4.4 anonymous gating contract 가 "공개/사전검토" 분류에 한해 이 fallback 을 허용한다 — conversion-only 분류에는 절대 적용되지 않는다 (legacy anon id 로는 영구 데이터를 만들 수 없다). axios 인터셉터는 Supabase 토큰이 없으면 자동으로 supabase header 만 빼고 호출. ADR-0004 Accepted (Phase 2) 시점에 본 fallback 도 함께 폐기.
  - **(B) UI 가 fallback 도 실패한 경우의 disabled 상태를 명시.** Supabase 도달 + legacy header 둘 다 비어 있는 사용자는 (예: localStorage 차단 + Supabase 5xx) `/app/pre-review` 진입 시 "현재 비회원 모드로 진행할 수 없습니다. 다시 시도해 주세요" 카드만 노출하고 core run 버튼은 disabled. 비회원 데이터 손실보다 명시적 차단이 안전.
  - 재시도 버튼은 LegalNotice 또는 sticky toast 로 노출 (UX 트랙 후속).

- **Phase 1 dual-write 정합 (ADR-0003 supersede 전).** Phase 1 동안 SessionProvider 는 Supabase 익명 sign-in 직후, 기존 `getOrCreateAnonymousUserId()` 도 **함께** 호출하고 두 ID 를 모두 유지한다. 이유:
  - 기존 도면/리포트가 `localStorage.jippin_anonymous_user_id` 와 `anonymous_users.id` 외부 키로 보관되어 있으므로, ADR-0003 의 claim 경로 (콜백 트랜잭션의 `anonymous_users.converted_user_id` 갱신) 를 끊으면 사용자 데이터 손실.
  - dual-write 동안 Supabase user `id` 와 ADR-0003 익명 ID 의 매핑은 backend 가 supersede 이슈 (ADR-0004 자식) 에서 일괄 backfill 한다. 웹은 두 ID 를 모두 axios 호출 헤더에 실어 호환을 유지: `Authorization: Bearer <supabase access_token>` + `x-jippin-anon-id: <legacy uuid>`.
  - 본 dual-write 는 ADR-0003 이 supersede 되는 ADR-0004 Accepted 시점에 종료된다. 종료 시점에 `lib/anonymous-user.ts`, localStorage 키, 헤더 전송이 같은 PR 에서 일괄 제거된다 ([§9 Phase 표](#9-phase-별-전환-순서)).

### 4.2 로그인 / 전환 CTA — `linkIdentity` 와 `signInWithOAuth` 분기

ADR-0003 §2.2 의 "비회원 사전검토 → 전환 시점 OAuth" 정책을 유지하기 위한 분기.

#### 4.2.1 기본 분기

```
[CTA 클릭]
   │
   ├─ supabase.auth.getUser() → user.is_anonymous === true
   │      → supabase.auth.linkIdentity({
   │          provider: toSupabaseProviderId(uiProvider),   // §4.2.3 매핑
   │          options: { redirectTo: callbackUrl({ next: SUCCESS_URL }) }
   │        })
   │      ⇒ Supabase 가 provider 페이지로 redirect.
   │        성공 시 callback Route Handler 가 exchangeCodeForSession 후 동일 user id 유지, identities 가 추가됨.
   │        실패 시 §4.2.2 fallback ladder 로 진입.
   │
   └─ user 없음 / 이미 실명 user
          → supabase.auth.signInWithOAuth({
              provider: toSupabaseProviderId(uiProvider),
              options: { redirectTo: callbackUrl({ next: SUCCESS_URL }) }
            })
          ⇒ 신규 user 생성 또는 기존 로그인.
```

- **OAuth 진입 BFF — flow context cookie + intent dispatch + PKCE verifier.** 위 `linkIdentity` / `signInWithOAuth` 호출은 **클라이언트가 직접 부르지 않고** `apps/web/app/auth/oauth/start/route.ts` (GET, `?provider=<ui>&intent=link|signin|link-merge`) 를 거친다. 이 BFF 가 다음을 단일 응답으로 묶어 처리한다 — **모든 Set-Cookie 가 같은 `NextResponse` 객체에 부착되어야 PKCE / flow context / merge intent 가 함께 전달**된다 (review item 5).
  1. `toSupabaseProviderId(uiProvider)` 검증 (§4.2.3 매핑).
  2. `intent` dispatch — **익명 user id 보존 의무 (review item 1)**:

      | `intent` 값 | 진입 컨텍스트 | BFF 가 호출하는 Supabase SDK | 익명 user id |
      |---|---|---|---|
      | `link` | 익명 user 가 OAuth 버튼 클릭 (정상 conversion). | `supabase.auth.linkIdentity({ provider, options: { redirectTo, skipBrowserRedirect: true } })` | **유지** — link 후 동일 user id, identities 추가. |
      | `signin` | 비로그인 / 실명 user 가 다른 계정으로 로그인. | `supabase.auth.signInWithOAuth({ provider, options: { redirectTo, skipBrowserRedirect: true } })` | n/a (익명 세션 없음). |
      | `link-merge` | §4.2.2 fallback ladder 의 "예, 옮기고 로그인" 분기 (intent 가 이미 다른 user 에 연결되어 linkIdentity 실패한 직후). | `supabase.auth.signOut()` → `supabase.auth.signInWithOAuth({ provider, ... })`. **이 분기만 익명 세션 폐기.** | 폐기 (callback 이 merge intent cookie 로 이전). |

      `intent=link` 에서 잘못 `signInWithOAuth` 를 호출하면 익명 user id 가 사라지면서 pre-review 산출물의 ownership 이 끊긴다. 위 표는 그 회피의 SSOT.
  3. **PKCE verifier cookie (필수, review item 2·5 — `getAll`/`setAll` 패턴).** `@supabase/ssr` v0.5+ 는 cookie adapter 를 `get`/`set`/`remove` 개별 패턴에서 **`getAll` + `setAll` 배치 패턴**으로 옮겼다. server-side `linkIdentity` / `signInWithOAuth` 호출이 발급하는 모든 cookie (`sb-<ref>-auth-token-code-verifier` 등) 가 단일 `setAll(cookiesToSet)` 호출로 한 번에 도착하므로, 그 콜백이 같은 `NextResponse` 인스턴스에 모두 부착해야 PKCE 교환이 완료된다. 응답 객체를 만들고 나서 SDK 를 호출하거나, 새 `NextResponse.redirect()` 를 또 만들어 반환하면 verifier 가 손실되어 callback 이 `auth/missing-code-verifier` 에러로 실패한다.

      구체적 패턴 (의사 코드 — `getAll`/`setAll` 마이그레이션 후):

      ```ts
      // apps/web/app/auth/oauth/start/route.ts (요지)
      import { NextResponse, type NextRequest } from 'next/server';
      import { createServerClient } from '@supabase/ssr';

      export async function GET(request: NextRequest) {
        const url      = request.nextUrl;
        const uiProv   = url.searchParams.get('provider') as UiProvider;
        const intent   = (url.searchParams.get('intent') ?? 'link') as Intent;
        const sbProv   = toSupabaseProviderId(uiProv);

        // ★ Step 1 — 응답 객체를 먼저 만든다. setAll 콜백이 이 객체에 cookie 를 적용.
        const response = NextResponse.next();

        const supabase = createServerClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
          cookies: {
            // getAll: request 에 도착한 모든 cookie 를 반환.
            getAll() {
              return request.cookies.getAll().map(({ name, value }) => ({ name, value }));
            },
            // setAll: SDK 가 발급한 모든 cookie 를 단일 응답에 일괄 부착.
            // 본 콜백이 호출되는 시점에 PKCE verifier 가 같이 들어온다 → response 가 verifier 의 owner.
            setAll(cookiesToSet) {
              for (const { name, value, options } of cookiesToSet) {
                response.cookies.set({ name, value, ...options });
              }
            },
          },
        });

        // ★ Step 2 — flow context / merge intent cookie 발급 (Web origin, Path=/auth/callback).
        response.cookies.set('jippin_oauth_provider',
          signFlowContext(sbProv), COOKIE_OPTS);
        if (intent === 'link-merge') {
          const intentRow = await fetch(`${API_BASE}/auth/anon-merge-intents`, { /* ... */ })
            .then(r => r.json());                              // { signed_token, ... }
          response.cookies.set('jippin_merge_intent',
            intentRow.signed_token, COOKIE_OPTS);
        }

        // ★ Step 3 — intent dispatch (item 1). SDK 가 setAll 을 호출해 PKCE verifier 를 response 에 set.
        let urlResult;
        if (intent === 'link') {
          urlResult = await supabase.auth.linkIdentity({
            provider: sbProv,
            options: { redirectTo: CALLBACK_URL, skipBrowserRedirect: true },
          });
        } else {
          if (intent === 'link-merge') await supabase.auth.signOut();   // 익명 폐기. signOut 도 setAll 로 빈 cookie 부착.
          urlResult = await supabase.auth.signInWithOAuth({
            provider: sbProv,
            options: { redirectTo: CALLBACK_URL, skipBrowserRedirect: true },
          });
        }

        // ★ Step 4 — 새 NextResponse.redirect 를 만들지 말고, 누적된 response 의 headers 를
        //   그대로 사용하여 302 로 변환. Set-Cookie 헤더가 모두 보존됨.
        response.headers.set('Location', urlResult.data.url);
        return new NextResponse(null, {
          status: 302,
          headers: response.headers,    // PKCE verifier + flow context + merge intent + (필요 시) 그 외.
        });
      }
      ```

      위 패턴의 invariant: **`response` 객체 하나가 모든 Set-Cookie 의 owner** 이며, 마지막 단계가 그 객체의 headers 를 그대로 사용하여 302 를 만든다. `getAll`/`setAll` 은 v0.5+ 의 표준이며 deprecated `get`/`set`/`remove` 개별 콜백을 사용하면 cookie 누락 / 동시 set race 가 발생할 수 있어 금지. 본 패턴은 `lib/supabase/server.ts` / `proxy.ts` / `browser.ts` 의 모든 `createServerClient` 호출에 일관 적용한다.
  4. **자체 cookie 발급 — Web origin 필수 (review item 4).** 같은 `NextResponse` 에 다음 cookie 를 부착한다. 모두 `HttpOnly; Secure; SameSite=Lax; Path=/auth/callback; Max-Age=600`. API 가 다른 host/subdomain (예: `api.jippin.com`) 에 있으면 backend 의 `Set-Cookie` 는 `www.jippin.com/auth/callback` 에 도달하지 않으므로 **반드시 Web BFF 가 같은 origin 에서 발급**해야 한다.
     - `jippin_oauth_provider` — HMAC 서명된 `<supabase_provider>|<nonce>|<exp>` 토큰. callback §4.5.2.1 Kakao 감지가 1차 신호로 사용. (서명 키는 Web 와 Backend 가 공유하거나, Web 자체 키로 발급 후 callback 도 Web 가 검증.)
     - `intent=link-merge` 인 경우 추가로 `jippin_merge_intent` — backend 가 응답 본문으로 돌려준 서명 토큰 (`{ intent_id, nonce, exp, sig }`) 을 BFF 가 Set-Cookie 로 부착 (§4.2.2 step b 갱신).
  5. 응답 status `302`, `Location: <OAuth provider URL>` (`signInWithOAuth` / `linkIdentity` 가 반환).

  클라이언트 JS 가 직접 Supabase SDK 의 OAuth 함수를 호출하면 httpOnly 쿠키도 PKCE verifier 도 다 클라이언트 storage 로 가버려 SSR/Edge 보호가 깨진다 — BFF 경유는 review item 1·3·5 대응의 필수 조건.
- **`linkIdentity` 호출 권한.** Supabase 대시보드에서 `Auth → Identity Linking` 기능을 활성화해야 한다 (콘솔 세팅 트랙).
- **자동 병합 금지 — CMP-572 CEO 결정 (§0.0).** Supabase 의 기본 동작은 동일 verified 이메일에 대해 provider identities 를 같은 user 에 자동 link 한다. **MVP 에서는 이 기능을 OFF 로 봉인** 한다 — 콘솔 `Authentication → Settings → Account Linking = Manual only`, "Auto-link verified emails" / "Link accounts with same email" 끈 상태. 콘솔만으로 부족할 경우 backend webhook 으로 거부. 본 runbook 의 어떤 흐름도 자동 병합에 의존하지 않으며, 익명 세션에서 raw `signInWithOAuth` 를 호출하는 코드 경로는 본 정책 위반으로 reject 한다. 라이브 진입 시 §8 입력 항목 표가 체크 SSOT.
- **익명 세션에서는 `linkIdentity` 만 사용.** 익명 세션 (`is_anonymous=true`) 상태에서 `signInWithOAuth` 를 직접 호출하면 새 user 를 만들면서 익명 user 의 도면/리포트 ownership 이 끊긴다. §4.2.2 fallback ladder 의 "예, 옮기고 로그인" 분기가 유일한 합법 경로이며 그 안에서도 명시적 `signOut()` 후에만 `signInWithOAuth` 를 호출한다.
- **provider 화이트리스트.** UI 가 노출하는 provider 는 `kakao | naver | google` 로 고정 (ADR-0003 봉인). SDK 에 넘기는 식별자는 §4.2.3 매핑을 거친 결과이며 raw UI 값을 그대로 넘기지 않는다.

#### 4.2.2 `linkIdentity` 실패 fallback

`linkIdentity()` 는 provider identity 가 이미 다른 Supabase user 에 매핑된 경우 실패한다 (`identity_already_exists` 류 에러). 이 경우 익명 user 가 영원히 막히지 않도록 다음 ladder 를 적용한다.

> **§0.0 CMP-572 CEO 결정 정합.** 본 ladder 는 "이미 다른 user 에 연결된 provider identity 의 익명 세션 연결 시도" 케이스에서 자동 병합을 금지하고, 사용자에게 "기존 계정 로그인 + 데이터 이관" 또는 "익명 유지" 의 명시적 선택을 강제하기 위한 정본이다. 침묵 fallback, 자동 merge, 또는 "그냥 새 계정으로 로그인" 분기는 본 ladder 의 일부가 아니며 추가하면 정책 위반.

```
linkIdentity({ provider }) 실패
   │
   ├─ error.code/status 가 'identity_already_exists' 또는 동등 ⇒
   │      1) UI 모달 — "이 계정으로 이미 가입된 사용자가 있습니다.
   │                    지금까지 비회원으로 작성한 도면/리포트를 해당 계정으로 옮기시겠습니까?"
   │         · [예, 옮기고 로그인]
   │         · [아니오, 비회원으로 계속]
   │      2) "예" 선택 시:
   │         a) 익명 user id + ADR-0003 익명 ID(=Phase 1 dual-write) 를 백엔드의
   │            `POST /auth/anon-merge-intents` 큐에 enqueue (멱등).
   │            backend 응답 JSON: { intent_id, nonce, expires_at, signed_token }.
   │            signed_token = HMAC( intent_id | nonce | exp ) — backend 서명.
   │         b) BFF `GET /auth/oauth/start?provider=<ui>&intent=link-merge` 로 navigate.
   │            Web BFF (Next.js Route Handler) 가 같은 origin (`www.jippin.com`)
   │            에서 직접 Set-Cookie 발급 — `jippin_merge_intent=<signed_token>`,
   │            HttpOnly + Secure + SameSite=Lax + Path=/auth/callback + Max-Age=600.
   │            ※ API host 가 별도 subdomain (`api.jippin.com`) 인 경우 backend Set-Cookie
   │              는 callback path 에 도달하지 않으므로 반드시 Web origin 에서 발급해야 함
   │              (review item 4).
   │         c) BFF 가 server-side `supabase.auth.signOut()` (익명 세션 폐기) →
   │            `signInWithOAuth({ provider, options: { redirectTo, skipBrowserRedirect: true } })`
   │            로 OAuth URL 획득. 같은 NextResponse 에 PKCE verifier cookie + flow context
   │            cookie + jippin_merge_intent cookie 가 함께 부착된 채 302.
   │         d) (위 c 단계 안에서 처리되므로 별도 client 호출 없음.)
   │         e) callback Route Handler 가:
   │            · exchangeCodeForSession 으로 새 실명 세션 확보,
   │            · 요청 쿠키에서 `jippin_merge_intent` 추출 → backend `POST /auth/anon-merge-intents/{id}/commit`
   │              호출 (요청 본문 = { signed_intent_cookie_value }, Authorization = 새 user 의 access token).
   │            · backend 는 signature/nonce/만료를 검증하고 `from_anon_user_id` 와 새 `target_user_id`
   │              매핑이 정합하면 도면/리포트 ownership 을 단일 트랜잭션으로 이전 (audit log 포함).
   │            · 응답 Set-Cookie 로 `jippin_merge_intent` 즉시 expire 시켜 1회용 보장.
   │         f) 사용자에게 "이전 완료" toast (또는 부분 실패 시 fallback 안내).
   │      3) "아니오" 선택 시: 익명 세션 유지, login modal 닫기. 사용자는 다른 provider 로 재시도 가능.
   │
   └─ 그 외 일반 실패 (네트워크 / provider OAuth error) ⇒ §4.2.4 일반 에러 처리.
```

- **Backend/Auth 트랙 신설 라우트** — `POST /auth/anon-merge-intents` (큐 enqueue + signed_token 발급) 와 `POST /auth/anon-merge-intents/commit` (cookie 토큰 검증 + ownership 이전 단일 트랜잭션) 2개만 backend 가 owner. 본 트랙은 web 측 호출 계약과 payload 만 봉인한다.
- **쿠키 발급은 Web origin 에서만 (review item 4).** 기존 안의 `/bind-cookie` backend 라우트는 폐기 — API host 가 다른 subdomain 일 때 `Set-Cookie` 가 `www.jippin.com/auth/callback` 에 도달하지 않는 문제를 회피하기 위해 **Web BFF (`/auth/oauth/start`) 가 backend 가 발급한 `signed_token` 을 받아 같은 응답에 Set-Cookie 로 부착**한다 (§4.2.1 BFF 4번). 서명/검증 키는 Web↔Backend HMAC 공유 또는 Web 자체 키로 발급 후 backend 가 동일 키로 검증. 어느 경로든 쿠키 자체는 Web 가 발급.
- intent 큐는 멱등 키 (`from_anon_user_id + target_provider`) 로 중복 제출을 흡수한다. 사용자가 모달을 두 번 띄워도 데이터가 두 번 옮겨지지 않는다.
- **intent id 의 redirect 통과 — 쿠키 채택 사유.** Supabase 가 발급하는 hosted OAuth URL 은 `state` 파라미터를 owner 로 가지므로 우리가 임의 query 를 끼워 넣을 수 없고, provider redirect 후의 `next` 도 § 4.7.2 에 의해 상대 경로 + allow list 로 제한된다. 따라서 (a) URL query 에 intent id 노출 (open redirect / log 누설 위험), (b) localStorage (JS XSS 노출, signOut 이 같은 origin 의 일부 키를 비우기도 함), (c) httpOnly cookie 세 가지 옵션 중 (c) 만이 안전한 매체. 쿠키 토큰은 backend 가 HMAC 으로 서명 + 단명 nonce 결합으로 위조/재사용 모두 방어한다.
- **nonce 1회 사용.** backend 는 `commit` 성공 시 intent 의 nonce 를 즉시 회수해 같은 쿠키 값으로 두 번 commit 되지 않게 한다. 또한 응답 Set-Cookie 로 `Max-Age=0` 발급해 브라우저 측에서도 정리.
- **쿠키 미존재 fallback.** callback 이 `jippin_merge_intent` 쿠키 없이 도착하면 (사용자가 OAuth 진행 중 다른 탭으로 진입했거나 쿠키 만료) — merge 단계를 조용히 skip 하고 success redirect 만 수행. UI 가 후속에 "이전이 완료되지 않았습니다. 다시 시도해 주세요" 토스트 + 재시도 버튼 노출. 데이터가 잘못 옮겨지는 것보다 옮겨지지 않은 채 사용자가 인지하는 편이 안전하다.
- 모달 카피는 §5.2 카피 표에 후속 추가. UX 트랙이 다듬는다.

#### 4.2.3 provider id 매핑

`apps/web/lib/supabase/providers.ts` 가 단일 SSOT.

| UI provider (ADR-0003) | Supabase SDK 인자 (`signInWithOAuth` / `linkIdentity` 의 `provider`) | 비고 |
|---|---|---|
| `google` | `'google'` (native) | Supabase native. |
| `kakao` | `'kakao'` (native) | **Supabase Auth 는 Kakao 를 built-in provider 로 지원** (`Authentication → Providers → Kakao` 패널에서 직접 입력) — Custom OAuth provider 경로로 가지 않는다. Kakao Sync 동의 화면을 OAuth 화면에서 표시하려면 콘솔에서 `scope=profile_nickname,profile_image,account_email,gender,birthyear,birthday,terms_of_service` 등 명시적 입력 필요. |
| `naver` | **`'custom:naver'`** | Supabase 는 Naver native provider 를 제공하지 않으므로 **Custom OAuth Provider 의 OAuth2 모드 (not OIDC)** 로 등록한다 (§4.3.1 / §8 봉인). Naver 는 `id_token` 을 발급하지 않고 OIDC discovery URL (`.well-known/openid-configuration`) 도 노출하지 않으므로 콘솔에서 OIDC 모드로 등록하면 라이브에서 즉시 실패한다. **SDK 가 받는 canonical provider id 는 `custom:naver` (콘솔 등록 identifier `naver` + Supabase 가 부여하는 `custom:` prefix 의 합).** UI / 분석 / 텔레메트리 코드는 여전히 `'naver'` 식별자를 그대로 쓰며, **본 매핑 함수만이 SDK 경계에서 변환** 한다. |

매핑 함수 서명 (의사 코드):

```ts
// apps/web/lib/supabase/providers.ts
export type UiProvider = 'google' | 'kakao' | 'naver';
export type SupabaseProvider = 'google' | 'kakao' | `custom:${string}`;

const MAP: Record<UiProvider, SupabaseProvider> = {
  google: 'google',         // Supabase native.
  kakao:  'kakao',          // Supabase native (Auth → Providers → Kakao 패널). custom 경로 없음.
  naver:  'custom:naver',   // Supabase 가 Naver native 미지원 — Custom OAuth2 (not OIDC).
};

export function toSupabaseProviderId(ui: UiProvider): SupabaseProvider {
  return MAP[ui];
}
```

- 본 매핑을 거치지 않은 raw UI 식별자가 SDK 에 도달하면 `signInWithOAuth({ provider: 'naver' })` 가 Supabase 측에서 invalid provider 로 실패한다.
- **콘솔 identifier 일치 봉인 (review item 4 new).** `MAP.naver = 'custom:naver'` 의 `naver` 부분은 **Supabase 콘솔의 Custom OAuth Provider (OAuth2 모드) 등록 시 identifier 필드값과 정확히 일치** 해야 한다. 콘솔에서 `naver-prod` / `naver_kr` 같은 변형으로 등록하면 SDK 가 `signInWithOAuth({ provider: 'custom:naver' })` 를 호출했을 때 `provider_not_enabled` 에러가 난다. Supabase 가 콘솔 identifier `naver` 에 `custom:` prefix 를 자동으로 prepend 하여 SDK provider id `custom:naver` 를 만든다 — 콘솔에 직접 `custom:naver` 를 입력하면 결과 id 가 `custom:custom:naver` 로 이중 prepend 되므로 **콘솔 identifier 는 반드시 `naver` (prefix 없이) 입력**. §8 입력 항목 표가 콘솔 등록 identifier 의 SSOT.
- Custom Provider 등록 시 콘솔에서 부여하는 identifier 가 `naver` 가 아닌 다른 값으로 결정되면 (불가피한 사유) 본 매핑 함수의 `naver` 부분과 §8 입력 항목 표를 **같은 PR 에서** 한 줄씩 갱신하고 UI 는 손대지 않는다.
- Kakao 는 Supabase native provider 이므로 콘솔 identifier 일치 봉인이 별도로 필요하지 않다 — 콘솔의 `kakao` 패널 ON / 자격증명 입력 / scope 입력만 §8 가이드대로 따른다.

#### 4.2.4 일반 에러 처리 + `linkIdentity` 실패 UX 매트릭스 (review item 7 new)

`linkIdentity()` / `signInWithOAuth()` 호출이 실패할 때, error.code / status 별 UX 분기는 다음과 같다. `identity_already_exists` 한 케이스만 §4.2.2 fallback ladder 로 가고 나머지는 본 매트릭스가 SSOT.

| 분기 | 트리거 | UX | log/Sentry | merge intent cookie 처리 |
|---|---|---|---|---|
| `identity_already_exists` (또는 동등 — provider identity 가 이미 다른 user 에 연결) | linkIdentity | §4.2.2 fallback ladder 진입 (modal → "예/아니오"). | breadcrumb (warn). | ladder step b 에서 발급, callback 에서 1회용 expire. |
| `provider_oauth_cancelled` (사용자가 provider 화면에서 취소) | callback `?error=access_denied` | 익명 세션 유지, modal 닫음. `/auth/failure?reason=access_denied` → 한 줄 안내. | breadcrumb (info). | callback failureRedirect 에서 일괄 expire. |
| `provider_oauth_scope_denied` (필수 scope 거부) | callback `?error=access_denied` + scope 누락 | "필수 권한 동의가 없으면 진행할 수 없습니다. 다시 시도해 주세요" toast + retry CTA. | breadcrumb (warn). | callback failureRedirect 에서 일괄 expire. |
| `invalid_request` / `provider_not_enabled` / colsole identifier 불일치 (§4.2.3) | linkIdentity / signInWithOAuth 즉시 실패 | "일시적인 로그인 오류가 발생했습니다. 관리자에게 문의해 주세요" toast + Sentry. UI 가 provider 버튼을 잠시 disabled. | error (Sentry alert). | 발급 전 단계이므로 N/A. |
| `redirect_uri_mismatch` (콘솔 redirect allow list 누락) | linkIdentity / signInWithOAuth 즉시 실패 | 위와 동일. 콘솔 세팅 트랙에 즉시 보고. | error (Sentry alert + slack). | N/A. |
| 네트워크 / timeout / 일시 5xx | SDK 호출 / callback fetch | "잠시 후 다시 시도해 주세요" toast + 재시도 버튼. | breadcrumb (warn). | callback 진입했다면 expire, BFF 진입 전이면 N/A. |
| 기타 미분류 | 어디서든 | "로그인 중 문제가 발생했습니다" generic toast + Sentry full payload. | error (Sentry alert). | callback 도달 시 expire. |

- 모든 분기에서 raw `signInWithOAuth` 를 익명 세션에서 직접 호출하는 코드 경로는 추가되지 않는다 (§0.0 CMP-572 / §4.2.1).
- toast UX 카피는 §5.2 카피 표에 후속 추가 (UX 트랙).
- error.code 매핑은 `lib/supabase/oauth-errors.ts` (가칭) 단일 모듈에서 SDK 에러를 위 분기로 정규화 — 호출자가 raw error 객체를 분기 조건으로 쓰지 않는다.

기존 일반 에러 케이스 (보존):

- `redirectTo` 가 Supabase 콘솔의 redirect allow list 에 없으면 SDK 가 즉시 에러. 위 매트릭스의 `redirect_uri_mismatch` 분기로 처리.
- provider OAuth error (사용자 취소, scope 거부) 는 callback 에서 처리하여 `FAILURE_URL` 로 302 (§4.7).

#### 4.2.5 Provider 화이트리스트 정책 — email / passwordless 봉인 (CMP-584)

> **§0.0 CMP-572 CEO 결정 정합.** Provider 화이트리스트가 좁을수록 동일 verified email 자동 merge 우회로 / 비-OAuth 인증 우회로가 줄어든다. 본 정책은 "MVP 는 manual identity linking only" CEO 결정의 Phase 1 코드 봉인이다.

**정본.** `apps/web/lib/oauth-providers/index.ts` 의 `ALLOWED_PROVIDERS = ['google', 'kakao', 'naver'] as const` 단일 export 가 SSOT.

**Web 트랙 봉인 (CMP-584 Phase 1 (e) 산출물):**

| 경계 | 봉인 규칙 | 위반 시 동작 |
|---|---|---|
| **UI** — `apps/web/app/(auth)/login/login-buttons.tsx` | `ALLOWED_PROVIDERS` 에서만 버튼 라벨/순서를 derive. `<input type="email">` / `<input type="password">` / magic link / OTP / passwordless CTA 절대 노출 금지. | vitest unit test 가 `<input>` 0개 / form 0개를 강제 (`login-buttons.test.tsx`). |
| **BFF** — `apps/web/app/auth/oauth/start/route.ts` | `provider` 쿼리가 `ALLOWED_PROVIDERS` 밖이면 400 `PROVIDER_NOT_ALLOWED`. 화이트리스트 밖 query (`password`, `email`, `next` 등) 는 backend 로 forward 하지 않음. | vitest unit test 가 `provider=facebook` / `email` / `password` / `magic_link` / `otp` / missing 모두 400 확인 (`route.test.ts`). |
| **분석 / 텔레메트리** | provider 식별자 enum 은 `AllowedProvider` type 으로 지정. raw string 사용 금지. | TypeScript strict 가 컴파일 단계에서 차단. |
| **Supabase 콘솔** | Authentication → Providers 에서 **email / phone provider OFF** (§8 봉인). magic link / OTP / SMS 비활성. | §8 입력 항목 표가 콘솔 운영자의 SSOT — ON 인 채 라이브 가면 본 정책 위반 → 즉시 라이브 차단. |

**비-OAuth 경로 금지 (정책 사유):**

- 자체 가입 / 아이디 찾기 / 비밀번호 찾기는 ADR-0003 정본대로 존재하지 않는다.
- magic link / OTP / passwordless 는 (a) Supabase 콘솔에서 email provider 가 켜져야 하고, (b) email = 의 user 가 자동 link 되는 부수효과를 가질 수 있어 §0.0 CEO 결정 위반 위험.
- 본 봉인 이후 새 provider 추가 (Apple, GitHub 등) 는 별도 ADR / runbook 갱신 + 자식 이슈 분리.

**위반 케이스 — 즉시 reject 대상:**

- `ALLOWED_PROVIDERS` 외 provider id 를 raw string 으로 SDK / fetch / 분석 코드에 직접 쓰는 PR.
- login 페이지 (또는 그 외 경로) 에 `<input type="email">` / `<input type="password">` / magic link CTA 를 추가하는 PR.
- `/auth/oauth/start` BFF 의 화이트리스트 가드를 우회하거나 제거하는 PR.

### 4.3 FastAPI 호출 adapter

> §4.3 의 호출 어댑터 코드는 Backend/Auth 트랙이 §4.4 의 anonymous 거부 계약을 구현한 뒤에만 라이브 가능.

`apps/web/lib/api-client.ts` 재작성 (의사 코드):

```ts
import axios from 'axios';
import { getSupabaseBrowserClient } from '@/lib/supabase/browser';

const supabase = getSupabaseBrowserClient();

const client = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000',
  timeout: 15_000,
});

client.interceptors.request.use(async (config) => {
  const { data: { session } } = await supabase.auth.getSession();
  const token = session?.access_token;
  if (token) {
    config.headers.set('Authorization', `Bearer ${token}`);
  }
  return config;
});
```

**삭제 항목:**

- `lib/auth-token.ts` 의 메모리 토큰 저장 — Supabase SDK 가 localStorage / cookie 어느 한 쪽에 자동 보관 (SSR 분기는 `@supabase/ssr` 책임).
- 401 refresh 큐 — Supabase 의 `auth.refreshSession` 이 SDK 내부에서 처리. token 만료 직전이면 `getSession()` 자체가 갱신된 token 을 반환.
- `withCredentials: true` — 자체 `/auth/refresh` 쿠키 의존이 사라지므로 제거 (FastAPI 가 더 이상 자체 쿠키를 발급하지 않는 시점 기준).

**401 fallback (token revoke / 키 회전).** 백엔드가 token 검증 실패로 401 을 돌려주는 경우, SDK 의 자동 갱신과 무관한 영구 만료 / 키 회전 / revoke 시나리오가 있다. 그 시 한 번만 `supabase.auth.refreshSession()` 을 호출하고 재시도. 재시도까지 실패하면 client 상태를 logout 으로 전환하고 호출부에 propagate. 단 §4.4 의 403 `AUTH_ANONYMOUS_NOT_ALLOWED` 에는 본 fallback 을 적용하지 않는다 (refresh 해도 anonymous 인 사실은 바뀌지 않는다).

#### 4.3.1 Naver = Custom OAuth2 (not OIDC) 봉인 (CMP-584)

> **문제.** §4.2.3 매핑 표가 `naver` → `custom:naver` 로 표기하면서도 "OIDC Custom Provider" 라는 잘못된 표현이 round-9 까지 잔존했다. Naver 의 공식 인증 사양은 OAuth2 (authorize + token + user-info) 이며 OIDC discovery (`/.well-known/openid-configuration`) 와 `id_token` 발급을 지원하지 않는다. 콘솔에서 OIDC 모드로 등록하면 즉시 `provider_not_enabled` / discovery 실패.

**Web 트랙 봉인 (CMP-584 산출물):**

- `apps/web/lib/oauth-providers/naver.ts` — Naver Custom OAuth2 어댑터. `NAVER_PROTOCOL = 'oauth2' as const`. `NAVER_DEFAULT_ENDPOINTS` 가 authorize / token / user-info URL 3개를 명시.
- **변수명만 SSOT, 실값 금지** (AGENTS.md §4.7 + `apps/api/.env.example` + `apps/api/src/config.py` 정합): `NAVER_OAUTH_CLIENT_ID`, `NAVER_OAUTH_CLIENT_SECRET`, `NAVER_OAUTH_AUTHORIZE_URL`, `NAVER_OAUTH_TOKEN_URL`, `NAVER_OAUTH_USERINFO_URL`, (옵션) `NAVER_OAUTH_SCOPE`. 실값은 Supabase 콘솔 입력 또는 `.env.local`, **코드 / 문서 / 이슈 / PR 본문에 절대 기재 금지**.
- `assertNaverIsOAuth2()` — endpoint 가 `.well-known/openid-configuration` 패턴을 포함하면 throw. vitest unit test 가 default endpoints + 의도된 override + 잘못된 OIDC discovery URL 시나리오 모두 검증 (`naver.test.ts`).
- **`NAVER_DEFAULT_SCOPE = ''` (빈 문자열, round-4 봉인)** — Naver authorize endpoint 는 `scope` 쿼리 파라미터를 정식 사양에 두지 않으므로 Phase 1 은 scope 를 보내지 않는 것이 정본. `resolveNaverScope()` 가 `NAVER_OAUTH_SCOPE` env 가 있으면 그 값을, 없으면 빈 문자열을 반환. Supabase 콘솔 scope 필드도 비워두는 것을 권장.

**Scope 정책 (Phase 1, round-4 재서술):**

- Naver 의 공식 OAuth 2.0 가이드 (`https://developers.naver.com/docs/login/api/`) 는 authorize 요청에 `client_id` / `response_type` / `redirect_uri` / `state` 만 명시한다. **`scope` 파라미터는 사용하지 않는다** — `account` / `name` / `email` 등 미문서화 토큰을 보내면 Naver 가 `invalid_request` 로 거부하거나 무시할 수 있다.
- 사용자에게 보여줄 권한 범위 (이름 / 프로필 이미지 / 이메일 등) 는 **Naver Developers 콘솔의 "동의 항목" UI 에서 선언**한다. Phase 1 은 식별만 필요하므로 "필수 동의" 에서 최소 항목만 ON 으로 두고, "추가 동의" 의 `이메일` 항목은 비즈니스 앱 심사 통과 후에만 추가한다.
- 따라서 Supabase Custom OAuth Provider 의 `Scope` 필드는 **비워둔다 (default `''`)**. 정말 필요한 환경에서만 `NAVER_OAUTH_SCOPE` env 로 검증된 값 (예: 비즈니스 심사 통과 후 Naver 가 자체 검증한 토큰) 을 주입한다.
- email 동의 항목을 콘솔에 추가하면 user-info 응답에 `response.email` 이 포함되지만, 본 트랙은 그 변화를 강제하지 않으며 callback / backend sync 는 `response.email` 부재 가능을 가정으로 동작해야 한다 (§4.5.1 internal_signup 약관 화면이 email 을 user 입력으로 받는 분기 정합).
- 향후 명시 scope 가 필요해지면 별도 자식 이슈에서 (1) Naver 비즈니스 심사 통과 + 동의 항목 등록, (2) Naver 가 자체 검증한 정확한 토큰 문자열 확인, (3) `NAVER_OAUTH_SCOPE` env 갱신, (4) callback 분기 정리를 한 set 로 처리한다. raw scope 문자열을 코드에 hardcode 하는 PR 은 reject.

**Supabase 콘솔 봉인 (§8 보강 — 운영자 SSOT):**

- Authentication → Providers → Add custom OAuth provider → **`OAuth2 (Generic)`** 모드 선택 (OIDC 모드 절대 금지).
- 입력 필드: `Client ID` (= `NAVER_OAUTH_CLIENT_ID`), `Client Secret` (= `NAVER_OAUTH_CLIENT_SECRET`), `Authorize URL` (= `NAVER_OAUTH_AUTHORIZE_URL`), `Token URL` (= `NAVER_OAUTH_TOKEN_URL`), `User-Info URL` (= `NAVER_OAUTH_USERINFO_URL`), `Scope` = **비워둔다 (default `''`, round-4 봉인)** — Naver authorize 는 scope 파라미터 미사용. env override `NAVER_OAUTH_SCOPE` 는 Naver 비즈니스 심사 통과 후 자체 검증된 토큰을 강제해야 할 때만 사용. 사용자 동의 항목은 Naver Developers 콘솔 UI 에서 별도 선언.
- **`email_optional=true` 체크 (CMP-584 round-3 추가, 필수).** Phase 1 의 기본 scope 는 `account` 만 요구하므로 user-info 응답에 `response.email` 이 부재할 수 있다. Supabase Custom OAuth Provider 의 `email_optional` (또는 동등) 플래그를 **반드시 ON** 으로 등록해야 `auth.users` insert 가 email 부재로 실패하지 않는다. OFF 인 채 라이브 가면 Naver 로그인 시 `email_required` 류 에러 — 사용자가 가입 자체를 못 한다. 본 봉인은 Scope 정책 (위) 과 함께 1 set 로 결정한다. 향후 비즈니스 심사 통과 후 email scope 를 추가하면 이 플래그를 OFF 로 되돌릴지 별도 자식 이슈에서 결정.
- `provider identifier` 필드는 **반드시 `naver`** 로 (prefix 없이) 등록한다. Supabase 가 내부적으로 `custom:` prefix 를 prepend 하여 **SDK 가 보는 canonical provider id = `custom:naver`** 가 된다. 콘솔에 직접 `custom:naver` 를 입력하면 결과가 `custom:custom:naver` 로 이중 prepend 되어 SDK `signInWithOAuth({ provider: 'custom:naver' })` 호출 시 `provider_not_enabled`. §4.2.3 매핑 + §8 입력 항목 표가 SSOT.
- redirect allow list 에 `/auth/callback` 추가 (§4.7.2).

**사전 등록 가드 (signInWithOAuth 콜 전 운영 SSOT 확인):**

- `supabase.auth.signInWithOAuth({ provider: 'custom:naver' })` 또는 `linkIdentity({ provider: 'custom:naver' })` 호출은 Supabase 콘솔에 Custom OAuth Provider 가 등록되어 있어야 한다.
- **신규 환경 라이브 진입 전**: 운영자가 위 입력 필드 표 + `provider identifier=naver` + scope=`account` 가 모두 SSOT 와 일치하는지 §8 표를 보고 1회 수동 확인.
- 콘솔 등록 누락 / mismatch 시 §4.2.4 에러 매트릭스의 `provider_not_enabled` 분기로 빠진다 → 사용자에게 "일시적 로그인 오류" toast + Sentry alert + 5분간 Naver 버튼 disabled.
- 본 가드는 out-of-band SSOT (Supabase 콘솔) 이므로 코드 레벨에서 자동 검증 불가. naver.ts JSDoc 의 "사전 등록 가드" 단락이 코드 측 정본 주석이다.

**OIDC 와의 차이 (잘못 등록 시 증상):**

| 항목 | OAuth2 (정본) | OIDC (잘못된 등록) |
|---|---|---|
| 토큰 응답 | `access_token` + (optional) `refresh_token` | + `id_token` (JWT) |
| user 식별 | `userInfoUrl` 응답의 `response.id` | `id_token` 의 `sub` claim |
| Supabase 콘솔 입력 | authorize / token / user-info URL 3개 | OIDC discovery URL 1개 |
| Naver 지원 | ✅ 지원 | ❌ 미지원 (`/.well-known/openid-configuration` 부재) |

**위반 케이스 — 즉시 차단:**

- Naver provider 의 endpoints 변수에 `/.well-known/openid-configuration` URL 을 넣는 PR (`assertNaverIsOAuth2()` 가 throw).
- 콘솔에서 Naver 를 OIDC 모드로 등록한 채 라이브 진입.
- `id_token` 기반으로 Naver user 를 식별하려는 backend / web 코드.

### 4.4 anonymous gating contract (conversion-only 엔드포인트)

> **문제.** Supabase 익명 user 도 유효한 access token 을 받는다 (`is_anonymous=true` claim 포함). 백엔드가 token 검증 직후 `user.id` 만 신뢰하면 익명 access token 으로도 상담 저장 / 리드 / 리포트 발급을 호출할 수 있다 — ADR-0003 §2.2 "비회원은 사전검토만" 정책 위반.

본 트랙은 다음을 **web → backend 계약**으로 봉인한다 (실제 enforcement 는 Backend/Auth 트랙 owner — 별도 자식 이슈에서 단위 테스트로 강제):

| 엔드포인트 분류 | 예시 라우트 | 허용되는 인증 입력 | 거부 응답 |
|---|---|---|---|
| **공개 / 사전검토** (anonymous 허용) | `GET /catalog/*`, `POST /pre-review/run`, `GET /pre-review/{id}` | anonymous Supabase access token **OR** non-anonymous Supabase access token **OR** Phase 1 한정 `x-jippin-anon-id: <legacy uuid>` (Supabase 도달 실패 fallback — §4.1 fail-soft (A)). 셋 다 없으면 익명 핸들 발급 후 응답. | 401 만 비정상적 케이스 (legacy header 도 invalid format). |
| **terms submission — chicken-and-egg 면제 (item 3 new)** | `POST /auth/terms/accept`, `GET /auth/terms/pending` (약관 본문 조회 등 동의 화면 표시용) | **non-anonymous Supabase access token**. `terms_accepted_at` 검사 (검증 우선순위 #3) 에서 **면제**. anonymous 는 거부 (403 `AUTH_ANONYMOUS_NOT_ALLOWED`). | 401 / 403 `AUTH_ANONYMOUS_NOT_ALLOWED` |
| **conversion-only — 사용자 영속 데이터** | `POST /consults`, `GET /consults/{id}`, `POST /leads`, `POST /reports`, `GET /users/me` | **non-anonymous Supabase access token + `required_consent_set(now) ⊆ accepted_consents(user)`** (검증 우선순위 #3). legacy `x-jippin-anon-id` 헤더는 **절대 허용하지 않는다** — 영구 데이터를 만들 수 없으므로. | `403` + 본문은 repo 표준 envelope (§4.4.1) — `AUTH_ANONYMOUS_NOT_ALLOWED` (anonymous) / `AUTH_TERMS_NOT_ACCEPTED` (required 중 누락, `body.detail.missing` 에 누락 목록) |
| **conversion intent** | `POST /auth/anon-merge-intents`, `POST /auth/anon-merge-intents/commit` | anonymous **또는** non-anonymous (각각 from/target 측에서 호출) | 잘못된 단계의 token 은 422. |

검증 우선순위 (Backend/Auth 트랙 가이드 — web 트랙은 호출자 입장에서 신뢰):

1. JWT 서명 / `aud` / 만료 검증.
2. `is_anonymous` claim 추출. claim 이 없거나 `true` 이고 라우트가 conversion-only 분류면 즉시 403 `AUTH_ANONYMOUS_NOT_ALLOWED`.
3. **terms gate — required consent set 기준 (review item 3 + round-9 item 6 강화).** 단일 boolean (`users.terms_accepted_at IS NULL`) 이 아니라 **현 시점의 required consent set** 과 user 의 accepted set 을 비교한다. 약관이 v3 로 올라갔는데 user 가 v2 만 동의한 상태는 단일 boolean 으로 잡히지 않으므로.

    - **required consent set 정의.** `required_consent_set(now)` = 현 시점 활성화된 (`term_id`, `version`) 튜플 집합. 예: `{(tos, v3), (privacy, v2), (marketing, v1)}`. backend 가 admin 콘솔 / DB seed 로 관리하는 `required_terms` 테이블 (Backend/Auth 트랙 owner) 이 SSOT.
    - **user accepted set.** `accepted_consents(user_id)` = `terms_consents` 테이블의 (term_id, version) 튜플 집합. Kakao Sync (source='kakao_sync') 와 internal (source='internal_signup') 모두 합산. revoked 항목은 제외.
    - **gate 조건.** `required_consent_set ⊆ accepted_consents` 이 거짓이면 — 즉 required 중 하나라도 user 가 동의하지 않았으면 — conversion-only 분류 라우트에 403 `AUTH_TERMS_NOT_ACCEPTED` 반환. envelope 의 `body.detail.missing` 에 누락 (`term_id`, `version`) 목록을 담아 UI 가 동의 화면에 정확히 그 항목들만 노출하도록.
    - **terms submission 면제.** `POST /auth/terms/accept` / `GET /auth/terms/pending` 는 본 검사에서 면제. 동의 화면을 띄우려면 이 라우트는 약관 미동의 user 도 호출 가능해야 함 (chicken-and-egg 회피).
    - **UI / 인터셉터.** axios 인터셉터가 `AUTH_TERMS_NOT_ACCEPTED` 수신 시 `/auth/terms?missing=<인코딩된 누락 목록>` 으로 navigate (세션 유지). conversion-only 버튼은 `/users/me` 응답의 `required_terms_pending` 필드를 보고 disabled (§5.2).
    - **버전 변경 시 재게이트.** required 가 v2→v3 로 오르면 기존 user 들도 다음 conversion 요청에서 403 을 받고 동의 화면으로 navigate. boolean 컬럼 하나로는 이 시점에 모두 풀려버린다.
4. (선택) backend 의 `users` 테이블에 해당 user id 가 존재하고 `is_active=true` 인지 cross-check. Supabase 콘솔에서 admin 이 user 를 비활성화한 케이스 방어.

#### 4.4.1 응답 envelope — repo 표준 정합

> AGENTS.md §4.5 + `apps/api/src/errors.py::_envelope` + `apps/web/lib/api/error.ts::parseApiError` 가 SSOT. 본 트랙은 신규 envelope 을 만들지 않고 기존 표준을 그대로 사용한다.

응답 본문 (status `403`):

```json
{
  "error": {
    "code": "AUTH_ANONYMOUS_NOT_ALLOWED",
    "message": "이 작업은 로그인 후에 사용할 수 있습니다.",
    "request_id": "01HXYZ...",
    "timestamp": "2026-06-01T00:00:00Z"
  }
}
```

- `error.code` / `error.message` / `error.request_id` / `error.timestamp` 4개 키는 backend (`_envelope` helper) 가 모든 에러에 일관 부여하는 필드 (`apps/api/src/errors.py:39-47`).
- 라우팅 힌트 (`next: "/login"`) 같은 부가 정보가 필요하면 backend 가 `body.detail = { next: "/login" }` 으로 옆에 둔다 (envelope 자체에는 손대지 않는다). 이는 `ZippinException(details=...)` 가 이미 처리하는 패턴 (`apps/api/src/errors.py:62-63`).

웹 측 처리:

- axios 인터셉터는 `parseApiError(err)` (`apps/web/lib/api/error.ts:60-95`) 를 호출하여 위 envelope 을 `ApiError { code, message, requestId, timestamp, status, cause }` 로 정규화. 분기:
  - **`apiError.code === 'AUTH_ANONYMOUS_NOT_ALLOWED'`** → logout/login modal (자동 token 재시도 금지). 익명 사용자가 conversion-only 라우트를 깊은 링크로 호출한 케이스.
  - **`apiError.code === 'AUTH_TERMS_NOT_ACCEPTED'`** → `/auth/terms` (Google · Naver 내부 약관 화면) 로 navigate. 세션은 유지하고 약관 동의 (`POST /auth/terms/accept`) 후 다음 호출부터 정상 통과 (review item 3).
  flat body (`{ code, message }`) 를 직접 읽는 일이 없도록 모든 호출자가 `parseApiError` 를 거친다.
- 사용자가 비회원 상태에서 conversion-only 라우트를 직접 호출한 경우이므로 UI 단에서도 버튼을 disabled 로 두는 것이 정합이지만, 깊은 링크 / 캐시된 페이지를 통해 호출이 새는 경우의 안전망.
- `request_id` 는 toast / Sentry / log 컨텍스트에 함께 노출해 backend 에서 사용자 문의 트래킹이 가능하도록 한다 (이미 `ApiError.requestId` 로 노출).

> **금지.** 본 트랙에서 `{ code: ..., message: ..., next: ... }` 같은 flat body 를 새로 정의하지 않는다. 위 envelope 외 응답 형식을 본 PR 이 도입하면 repo 표준 (AGENTS.md §4.5) 위반.

### 4.5 약관 동의 / 추가 user metadata

ADR-0003 §2.2 의 `terms_consents` 흐름은 그대로 유지. 변경 포인트:

#### 4.5.1 Google · Naver — 내부 약관 화면 (`source='internal_signup'`)

- 약관 동의 화면 진입 트리거 — 더 이상 `GET /auth/me` 의 `missing_required_terms` 가 아닌, **백엔드가 `Authorization: Bearer <supabase_jwt>` 호출에 대해 `/users/me` (or 동등 엔드포인트) 응답에 포함시키는 동일 필드** 를 신뢰한다. 응답 구조는 그대로 둘 수 있으므로 web 측 컴포넌트는 백엔드의 새 path 만 가져다 호출.
- 약관 동의 제출은 `POST /auth/terms/accept` 그대로 (이름은 Backend 트랙이 변경 가능). Supabase user `id` 를 backend 가 token 에서 추출. `terms_consents` insert 시 `source='internal_signup'`.

#### 4.5.2 Kakao Sync — 동의 audit persistence (`source='kakao_sync'`)

> **문제.** 자체 라우터 시절에는 콜백 핸들러가 Kakao 응답 본문에서 `agreed_terms` payload 를 추출해 같은 트랜잭션 안에서 `terms_consents(source='kakao_sync')` insert 를 수행했다 (ADR-0003 §2.4). Supabase hosted OAuth 로 바뀌면 동의 화면 owner 가 Supabase 가 되어, Kakao 가 응답한 동의 payload 가 **백엔드까지 자연스럽게 도달하지 않는다**. 이 경로를 명시하지 않으면 AGENTS.md / ADR-0003 의 source 분리 저장 봉인이 깨진다.

본 트랙은 다음 셋 중 **하나의 경로를 라이브 전 반드시 봉인** 하도록 의무화한다 (web 트랙은 (a) 를 선호하며 그대로 설계한다 — Backend/Auth 트랙이 (b) / (c) 로 합의 변경 가능):

| # | 경로 | Owner | 장점 | 단점 |
|---|---|---|---|---|
| **(a)** | **Callback Route Handler 직후 backend sync** — `/auth/callback` 가 `exchangeCodeForSession` 성공 직후, Supabase session 의 provider id 가 카카오 (`'kakao'` Supabase native) 인 경우 `POST /auth/terms/kakao-sync` 호출. payload = `{ supabase_user_id, provider_access_token, raw_kakao_payload(있을 시) }` — **`provider_access_token` = `session.provider_token`** (Kakao OAuth access token, **`id_token` 아님** — §4.5.2.2 정합). backend 가 이 access token 으로 Kakao `/v2/user/scopes` 를 재호출하여 동의 항목을 audit 한 뒤 `terms_consents(source='kakao_sync')` 단일 트랜잭션 insert. | Web (호출 위치) + Backend (검증/저장) | 흐름이 명시적이고 추적 가능. Supabase webhook 의존 없음. | callback 가 실패하면 동의 기록이 누락 — fallback 필요 (§4.5.2 끝). |
| (b) | Supabase Auth Hook (Beta) — `auth.users` insert 시 trigger 가 fire → edge function 이 Kakao identity provider 의 payload 를 읽어 backend 로 forward. | Supabase / Backend | callback 누락에 강함 (서버 측 fire). | Supabase 기능 의존성 + provider raw payload 접근 가능 여부 검증 필요. |
| (c) | Postgres trigger on `auth.identities` insert — provider='kakao' 일 때 backend 의 별도 함수 호출. | DBA / Backend | DB level 보장. | Kakao 가 보낸 동의 payload 가 `auth.identities.identity_data` 에 들어오는지 콘솔 세팅과 함께 확인 필요. 가능하지 않으면 (c) 채택 불가. |

**경로 (a) 의 web 측 의사 코드** (`/auth/callback/route.ts` 발췌 — 전체 코드는 §4.7).

#### 4.5.2.1 신규 link 된 provider 가 Kakao 인지 판정

`app_metadata.provider` 만 보면 **익명 user 에 Kakao identity 를 `linkIdentity()` 로 추가** 한 경우를 놓친다 — 기본 primary 가 `anonymous` 로 남기 때문 (review item 3). 두 신호를 합쳐 판정한다:

```ts
// apps/web/lib/supabase/identities.ts
import type { User } from '@supabase/supabase-js';
import type { SupabaseProvider } from './providers';

// 결과: 사용자가 이번 callback 으로 새로 연결한 provider id (Supabase 식별자).
//       confidence 가 낮으면 null — Kakao Sync audit 를 건너뛰는 게 안전.
export function detectNewlyLinkedProvider(
  user: User,
  intendedProviderCookie: string | null,            // login-buttons 가 callback path 쿠키로 전달.
): SupabaseProvider | null {
  // 1) UI 의도 — flow context cookie (signed token, httpOnly·Secure·Path=/auth/callback·Max-Age=600).
  //    backend 가 동일 HMAC 으로 서명/검증한다고 가정.
  const intended = parseIntendedProvider(intendedProviderCookie);

  // 2) Supabase 가 보고하는 user.identities[]. 가장 최근에 link 된 identity 가 신뢰 가능한 신호.
  //    identities 가 'kakao' / 'custom:kakao' 를 포함하면 last_sign_in_at 이 가장 큰 항목으로 추정.
  const lastIdentity = pickLastLinkedIdentity(user.identities ?? []);
  const observed: SupabaseProvider | null = lastIdentity?.provider as SupabaseProvider | null;

  // 3) 정합 검증. 두 신호가 모두 존재하면 일치해야 한다. 충돌 시 null (skip + 로그) — fallback (a)
  //    의 reconcile 잡이 사후에 잡는다.
  if (intended && observed && intended !== observed) return null;
  return intended ?? observed ?? null;
}
```

- `intendedProviderCookie` 는 §4.2.1 login-buttons 가 OAuth 진입 직전에 발급한다: 값 = HMAC 으로 서명된 `provider|nonce|exp` 토큰. 쿠키 이름 `jippin_oauth_provider`, scope = `Path=/auth/callback; Max-Age=600; HttpOnly; Secure; SameSite=Lax`. 콜백이 끝나면 즉시 expire (callback 의사 코드 마지막 블록 참조).
- 신호 (1) 또는 (2) 중 하나만 존재하면 그 값을 사용. 둘 다 존재하고 충돌하면 `null` (skip) — fallback 의 reconcile 잡이 잡는다.
- 익명→link 케이스에서 신호 (2) 만 의존하면 `identities` 배열 정렬이 SDK 버전에 따라 다를 수 있어 미스 가능. 신호 (1) 을 항상 함께 본다.

#### 4.5.2.2 backend 로 보내는 payload — `provider_token` 의미

Supabase 의 session 필드 명세:

| 필드 | 정체 | 본 audit 에서의 용도 |
|---|---|---|
| `session.access_token` | Supabase 가 발급하는 자체 JWT (`is_anonymous` claim 포함). | backend 가 호출자 인증/인가 검증에 사용. |
| `session.provider_token` | **provider 의 OAuth access token** (예: Kakao access token). OIDC `id_token` 이 아니다. | Kakao user-info / scopes API 재호출용 — backend 가 동의 항목을 사후 조회. |
| `session.provider_refresh_token` | provider refresh token (지원되는 경우만). | provider access token 만료 시 갱신. 본 audit 흐름은 callback 직후 1회만 호출하므로 일반적으로 불필요. |
| (없음) | OIDC raw `id_token` 은 SDK 가 노출하지 않음. Custom OAuth provider 가 OIDC 모드이고 Supabase 가 raw JWT 를 보관해 줘야 접근 가능. | 사용 안 함. 의존 금지. |

즉 **runbook 이전 안 (`id_token: session.provider_token`) 은 의미가 틀린다** (review item 4). 올바른 payload:

```ts
// apps/web/app/auth/callback/route.ts 내부의 persistKakaoSyncConsent 헬퍼 (의사 코드).
async function persistKakaoSyncConsent(
  session: Session,
  linkedProvider: 'kakao' | 'custom:kakao',
) {
  await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/auth/terms/kakao-sync`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      // Supabase 가 발급한 자체 JWT. backend 가 호출자 인증/인가 검증에 사용.
      Authorization: `Bearer ${session.access_token}`,
    },
    body: JSON.stringify({
      supabase_user_id: session.user.id,
      linked_provider:  linkedProvider,                // 'kakao' | 'custom:kakao'.

      // ===== provider 측 raw 자료 — backend 가 Kakao user-info / scopes API 재호출에 사용. =====
      // provider OAuth access token. id_token 이 아니다 (review item 4).
      provider_access_token: session.provider_token ?? null,
      // 일반적으로 callback 1회 호출에 충분하므로 refresh 는 옵션.
      provider_refresh_token: session.provider_refresh_token ?? null,
      // OIDC id_token 은 SDK 가 안정적으로 노출하지 않으므로 본 payload 에 포함하지 않는다.
      // backend 가 id_token 또는 동의 raw payload 가 꼭 필요하면 Kakao /v2/user/scopes
      // 또는 /v2/user/me?secure_resource=true 를 provider_access_token 으로 재호출한다.
    }),
  });
}
```

backend 측 처리 합의 (Backend/Auth 트랙 owner — **id_token 의존 금지 / provider_access_token 으로 user-info API 재호출 강제, review item 4 재확인**):

1. `Authorization` 검증 → `supabase_user_id` 와 token sub 일치 확인.
2. **`provider_access_token` 으로 `https://kapi.kakao.com/v2/user/scopes` 호출** → 동의된 scope 목록 수신. 본 단계가 audit 의 truth-source. id_token / 자체 claim 신뢰 금지.
3. (옵션) `/v2/user/me?secure_resource=true` 로 추가 정보 수신.
4. `terms_consents(source='kakao_sync', user_id, term_id, version, agreed_at=now)` insert (UNIQUE 충돌 시 멱등 무시).
5. 응답 4xx 면 callback 측은 best-effort 로 swallow, reconcile 잡이 사후 보정.

> `provider_access_token` 은 본 callback 1회 호출에만 사용하고 backend 는 보관하지 않는다 (PII / 추가 권한 누설 방지). 보관이 필요해지면 ADR 갱신.
> Kakao 가 응답한 id_token (있는 경우) 만으로 audit 결정을 내리지 않는다 — id_token 의 audience 가 우리 backend 인지 검증하기도 어렵고, scope 동의 항목이 들어 있다는 보장도 없다. 항상 access token → user-info API 경로를 따른다.

#### 4.5.2.3 fallback (audit 누락 방어)

- 백엔드는 `terms_consents` 의 `(user_id, term_id, version, source='kakao_sync')` 가 비어 있고 `auth.identities` 에 Kakao identity 가 존재하며 마지막 카카오 로그인이 N 분 (예: 5분) 이상 지난 user 를 야간 reconcile 잡으로 스캔, Kakao user-info 를 재호출하여 사후 insert. 본 잡 owner 는 Backend/Auth 트랙.
- 웹 콜백이 5xx 로 실패하거나 §4.5.2.1 detection 이 두 신호 충돌로 `null` 을 반환한 경우, 사용자에게 toast 노출 ("동의 기록을 다시 시도 중입니다") 후 다음 로그인 진입 시 backend 가 재확인.

> 본 트랙은 경로 (a) 만 봉인한다. (b) / (c) 가 채택되면 본 절을 갱신한다.

### 4.6 로그아웃

- `supabase.auth.signOut()` — 모든 storage / cookie 정리.
- 백엔드 `POST /auth/logout` 호출은 불필요 (자체 refresh token 폐기 대상이 없음). 백엔드 측에 audit log 트리거가 필요하다면 별도 `POST /events/logout` 같은 명시 라우트로 분리하되, 본 트랙의 권고는 "백엔드 logout 호출 제거".
- signOut 후 `/login` 으로 redirect.

### 4.7 OAuth callback route — `exchangeCodeForSession`

> **문제.** PR #42 v1 안은 provider 의 `redirectTo` 를 곧바로 `/auth/success` 로 향하게 했다. Supabase SSR/PKCE 흐름에서는 콜백 Route Handler 가 `exchangeCodeForSession(code)` 를 호출해야 `@supabase/ssr` cookie chunked storage 에 토큰이 저장된다. 이 절차를 생략하면 클라이언트는 코드만 받고 세션은 만들지 못한다.

#### 4.7.1 신규 라우트

신설 파일: `apps/web/app/auth/callback/route.ts` (Node runtime — App Router Route Handler).

```ts
// 의사 코드
import { NextResponse, type NextRequest } from 'next/server';
import { createServerClient } from '@/lib/supabase/server';
import { isSafeNext } from '@/lib/safe-redirect';
import { detectNewlyLinkedProvider } from '@/lib/supabase/identities';

const DEFAULT_NEXT  = process.env.NEXT_PUBLIC_FRONTEND_AUTH_SUCCESS_URL ?? '/auth/success';
const FAILURE_URL   = process.env.NEXT_PUBLIC_FRONTEND_AUTH_FAILURE_URL ?? '/auth/failure';
const ORIGIN        = (request: NextRequest) =>
  new URL('/', request.url).origin;            // request.url 의 query 를 절대 가져오지 않는다.

// 화이트리스트 외 토큰은 모두 'oauth_error' 로 normalize 해 외부 메시지를 그대로 흘리지 않는다.
const KNOWN_REASONS = new Set([
  'missing_code', 'exchange_failed', 'oauth_error',
  'access_denied', 'server_error', 'temporarily_unavailable',
]);
const sanitizeReason = (raw: string | null): string =>
  raw && KNOWN_REASONS.has(raw) ? raw : 'oauth_error';

// query string 을 일체 상속하지 않는 fresh failure URL. provider authorization code 가
// `/auth/failure` 의 URL · access log · referer 에 절대 남지 않도록 한다 (review item 2).
//
// FAILURE_URL 형태별 동작 (review item 3):
//   - 상대 경로 ('/auth/failure')      → new URL(...) 이 ORIGIN(request) 와 합성. ✓
//   - 절대 URL ('https://...auth/failure') → new URL(absolute, base) 가 base 를 무시하고
//                                            absolute 를 그대로 사용. ✓ (malformed path 안 됨)
//   - schema-relative ('//evil.com/...')   → URL 생성자가 base 의 protocol 만 차용하므로
//                                            cross-origin 으로 새 나간다. **반드시** env 입력
//                                            단계에서 차단. 본 페이지에서는 한 번 더 origin
//                                            검증 후 mismatched 면 DEFAULT_FAILURE_FALLBACK 으로
//                                            교체 (아래 sanitizeFailureBase 참조).
const DEFAULT_FAILURE_FALLBACK = '/auth/failure';
const sanitizeFailureBase = (request: NextRequest): string => {
  try {
    const target = new URL(FAILURE_URL, ORIGIN(request));
    return target.origin === ORIGIN(request) ? `${target.pathname}${target.search}` : DEFAULT_FAILURE_FALLBACK;
  } catch {
    return DEFAULT_FAILURE_FALLBACK;       // env 값이 invalid 면 안전한 기본값으로.
  }
};
// ★ Invariant — 본 Route Handler 가 반환하는 모든 NextResponse 는 expireCallbackCookies 를
//   거쳐야 한다. provider cancel / error / missing-code / exchange 실패 / 성공 / 어떤 분기든
//   예외 없음. stale intent 가 다음 OAuth callback 에 소비되어 잘못된 merge 가 발생하지
//   않게 하기 위한 정본 규칙 (review item 1).
const CALLBACK_COOKIES = ['jippin_merge_intent', 'jippin_oauth_provider'] as const;
const expireCallbackCookies = (res: NextResponse) => {
  for (const name of CALLBACK_COOKIES) {
    res.cookies.set(name, '', { path: '/auth/callback', maxAge: 0 });
  }
  return res;
};

const failureRedirect = (request: NextRequest, reason: string | null) => {
  const target = new URL(sanitizeFailureBase(request), ORIGIN(request));
  target.search = '';                       // 어떤 경우에도 inbound query 상속 금지.
  target.searchParams.set('reason', sanitizeReason(reason));
  return expireCallbackCookies(NextResponse.redirect(target));   // provider cancel/error/missing-code 케이스 포함.
};

export async function GET(request: NextRequest) {
  const url       = request.nextUrl;
  const code      = url.searchParams.get('code');
  const nextRaw   = url.searchParams.get('next');
  const errorCode = url.searchParams.get('error');                  // provider OAuth error.
  const safeNext  = nextRaw && isSafeNext(nextRaw) ? nextRaw : DEFAULT_NEXT;

  if (errorCode) return failureRedirect(request, errorCode);
  if (!code)     return failureRedirect(request, 'missing_code');

  const supabase = createServerClient();
  const { data, error } = await supabase.auth.exchangeCodeForSession(code);
  if (error || !data?.session) {
    return failureRedirect(request, error?.code ?? 'exchange_failed');
  }

  // 익명 → 실명 merge intent 회수 (§4.2.2 ladder step e).
  // 쿠키는 `apps/web/app/auth/callback` path 로만 발급되므로 다른 라우트에 누설되지 않는다.
  // 응답 마지막의 expireCallbackCookies() 가 성공/실패와 무관하게 cookie 를 1회용으로 비운다.
  const mergeIntentCookie = request.cookies.get('jippin_merge_intent')?.value ?? null;
  let mergeStatus: 'none' | 'committed' | 'commit_failed' = 'none';
  if (mergeIntentCookie) {
    try {
      const commitRes = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/auth/anon-merge-intents/commit`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${data.session.access_token}`,
        },
        body: JSON.stringify({ signed_intent_cookie_value: mergeIntentCookie }),
      });
      // commit HTTP failure 처리 (review item 5):
      //  - 2xx → committed.
      //  - 4xx (특히 410 expired / 409 already_consumed / 422 signature_invalid)
      //    → 로그 + UI 에 "이전 실패" 토스트 노출용 query 추가. 데이터는 그대로 두고 cookie 만 정리.
      //  - 5xx / network → reconcile 잡이 사후 처리한다는 가정 하에 같은 처리.
      mergeStatus = commitRes.ok ? 'committed' : 'commit_failed';
      if (!commitRes.ok) {
        console.warn('[auth/callback] anon merge commit non-2xx', commitRes.status);
      }
    } catch (e) {
      console.warn('[auth/callback] anon merge commit network failure', e);
      mergeStatus = 'commit_failed';
    }
  }

  // Kakao 동의 audit (§4.5.2 경로 (a)).
  // primary `app_metadata.provider` 만으로는 anonymous→link 케이스에서 누락 가능 (review item 3).
  // (1) flow context cookie (login-buttons 가 OAuth 진입 직전에 설정한 `jippin_oauth_provider`,
  //     httpOnly·Secure·Path=/auth/callback·Max-Age=600) → UI 가 의도한 provider.
  // (2) data.user.identities[] 의 신규 추가 provider 와 교차 검증.
  // 둘 중 어느 한 곳이라도 'kakao' / 'custom:kakao' 면 audit fire.
  const intendedProviderCookie = request.cookies.get('jippin_oauth_provider')?.value ?? null;
  const linkedProvider         = detectNewlyLinkedProvider(data.user, intendedProviderCookie);
  if (linkedProvider === 'kakao' || linkedProvider === 'custom:kakao') {
    await persistKakaoSyncConsent(data.session, linkedProvider).catch((e) =>
      console.warn('[auth/callback] kakao-sync persistence failed', e),
    );
  }

  // 성공 경로는 /auth/callback-done?next=<safeNext> 로 한 번 더 우회 — small client page 가
  // sessionStorage.removeItem('jippin_oauth_in_progress') 한 키만 제거 후 next 로 navigate
  // (§4.1.1 guard clear, Clear-Site-Data 금지).
  const done = new URL('/auth/callback-done', ORIGIN(request));
  done.searchParams.set('next', safeNext);                       // callback-done 가 다시 isSafeNext 로 재검증.
  if (mergeStatus === 'commit_failed') {
    done.searchParams.set('merge', 'failed');                    // UI 가 토스트로 알릴 수 있게 hint 만 전달.
  }
  return expireCallbackCookies(NextResponse.redirect(done));     // 성공 케이스에서도 callback-scoped cookie 일괄 정리.
}
```

> `ORIGIN(request)` 헬퍼와 `failureRedirect()` 가 **failure 경로에서 query string 을 절대 상속하지 않게** 한다. `request.url` 또는 `request.nextUrl.clone()` 을 그대로 사용하면 `?code=…&state=…` 가 다음 URL · access log · `Referer` 헤더로 새어 나간다 (review item 2).

#### 4.7.2 `next` allow list — open redirect 방어

`/auth/callback?next=...` 의 `next` 파라미터를 그대로 redirect 하면 open redirect 가 된다. `lib/safe-redirect.ts` 가 SSOT:

- 허용: `next` 가 상대 경로이고 `/` 로 시작하며 `//` 또는 `\\` 로 시작하지 않을 것.
- 거부: 절대 URL, 다른 호스트, schema-relative URL (`//evil.com`), 백슬래시 패턴.
- 검증 실패 시 `DEFAULT_NEXT` (= SUCCESS_URL) 로 fallback.

Supabase 콘솔 redirect allow list 에는 다음을 등록:

- 로컬: `http://localhost:3000/auth/callback`
- preview/staging: `https://<preview-domain>/auth/callback`
- 운영: `https://<prod-domain>/auth/callback`

`/auth/success` / `/auth/failure` 는 redirect 의 최종 목적지(302)이지 OAuth redirect 의 직접 대상이 아니므로 allow list 에 등록할 필요가 없다.

#### 4.7.3 Server Component vs Route Handler

`@supabase/ssr` v0.5+ 에서 `exchangeCodeForSession` 은 Route Handler / Server Action / Server Component 모두에서 호출 가능하다. 본 트랙은 **Route Handler** 를 SSOT 로 둔다. 이유:

- 콜백은 GET-only 진입이며 페이지 렌더링이 아닌 302 가 정답.
- Route Handler 가 `cookies()` mutation 시 가장 직접적 (Server Component 는 cookies set 이 제한적).

#### 4.7.4 Client-side hop hardening (review item 5)

OAuth 흐름은 다음 hop 들을 거친다:

```
[/auth/oauth/start] ──302──> [provider hosted page] ──302──> [/auth/callback]
       │                                                              │
       └─ (Web BFF, Set-Cookie chain)                                  │
                                                                       │
                              [/auth/callback-done?next=&merge=] <──302┘
                                       │
                                       └─ client page: sessionStorage clear + navigate(next)
                                              │
                                              └──> safeNext (SUCCESS_URL 등)
```

각 hop 의 책임을 명시한다 — 한 곳이라도 빠지면 hop chain 전체가 깨진다.

##### (a) `/auth/callback-done` next revalidation

```tsx
// apps/web/app/auth/callback-done/page.tsx (의사 코드, client component)
'use client';
import { useEffect } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { isSafeNext } from '@/lib/safe-redirect';

const DEFAULT_NEXT = process.env.NEXT_PUBLIC_FRONTEND_AUTH_SUCCESS_URL ?? '/auth/success';

export default function CallbackDone() {
  const sp = useSearchParams();
  const router = useRouter();

  useEffect(() => {
    // 1) §4.1.1 guard clear — sessionStorage 단일 키만. localStorage / Supabase cookie 미터치.
    try { window.sessionStorage.removeItem('jippin_oauth_in_progress'); } catch { /* private mode */ }

    // 2) next 재검증 — callback 가 이미 safeNext 만 넘기지만, 클라이언트가 직접 받은 query 이므로
    //    공격자가 page URL 을 직접 만들어 침입할 가능성 차단. 동일 SSOT (`isSafeNext`) 재사용.
    //    invalid 면 DEFAULT_NEXT 로 fallback 하되 Sentry breadcrumb 로 기록 — 정상 흐름이라면
    //    절대 도달하지 않는 분기이므로 alert 으로 운영 가시화 (review item 5 강화).
    const nextRaw = sp.get('next');
    const isSafe = nextRaw && isSafeNext(nextRaw);
    if (nextRaw && !isSafe) {
      try {
        Sentry.captureMessage('[callback-done] invalid next param fallback', {
          level: 'warning',
          extra: { nextRaw },
        });
      } catch { /* Sentry 미초기화 시 swallow */ }
    }
    const safe = isSafe ? nextRaw! : DEFAULT_NEXT;

    // 3) merge 실패 UX — toast 큐 enqueue. 본 hop 자체는 navigate 만 하고 toast 는 다음 페이지에서.
    if (sp.get('merge') === 'failed') {
      try { window.sessionStorage.setItem('jippin_toast_pending', 'merge_failed'); } catch {}
    }

    // 4) router.replace (history stack 에 callback-done 가 남지 않도록).
    router.replace(safe);
  }, [sp, router]);

  return <p>로그인 마무리 중…</p>;        // JS 비활성 사용자에게도 보이는 fallback 텍스트.
}
```

##### (b) OAuth redirect hop 검증

각 hop 의 `next` / `to` 파라미터는 **자체 hop 의 SSOT 검증을 다시 거친다**:

| hop | 받는 입력 | 검증 |
|---|---|---|
| `/auth/oauth/start` | `?provider=<ui>&intent=<...>` | provider 화이트리스트 + intent enum 검증. 외부 URL 받지 않음. |
| `/auth/callback` | `?code=…&next=<relative>` | `isSafeNext(next)` — 실패 시 DEFAULT_NEXT. |
| `/auth/callback-done` | `?next=<relative>&merge=<...>` | 위 (a) 의 `isSafeNext(next)` 재검증. merge 는 `'failed'` 단일 enum. |

중간에 사용자가 brute-force 로 query 를 손대도 모든 hop 이 동일 SSOT 로 거부하므로 open redirect 가 만들어지지 않는다.

##### (c) merge commit HTTP failure UX

callback 의 commit fetch 결과는 다음과 같이 분기 (callback Route Handler 가 이미 §4.7.1 의사코드에서 처리, 본 절은 UX 보장):

| 결과 | 동작 | UX |
|---|---|---|
| 2xx | `mergeStatus='committed'` | 일반 success redirect. toast 없음. |
| 4xx (`410 expired` / `409 already_consumed` / `422 signature_invalid`) | `mergeStatus='commit_failed'` + log warn | callback-done 가 `jippin_toast_pending=merge_failed` set → 다음 페이지의 ToastBus 가 "이전 실패. 다시 시도하세요" 노출 + 재시도 CTA. backend reconcile 잡이 사후 처리하지 않으면 사용자는 새 ladder 재진입으로 복구. |
| 5xx / network | 위와 동일 | reconcile 잡 owner = Backend/Auth 트랙. |

callback 응답에 inline 상태 코드를 노출하지 않는 이유 — Sentry 식 server-side log 만 신뢰 (사용자 URL 에 4xx 코드를 노출하면 fingerprinting / 공격 정보 노출).

##### (d) guard clearing 시점 — 모든 실패 분기 포함 (review item 1 강화)

- **정상 경로** — callback-done page 의 `useEffect` 첫 줄에서 `sessionStorage.removeItem('jippin_oauth_in_progress')`.
- **callback failureRedirect 경로 (cancel / error / missing-code / exchange 실패)** — `/auth/failure/page.tsx` 도 client component 로서 mount 시 동일하게 `sessionStorage.removeItem('jippin_oauth_in_progress')` 를 호출. callback Route Handler 의 server response 만으로는 sessionStorage 를 만질 수 없으므로 client page 가 동일 정리 책임을 진다. failure page 의 useEffect 의사 코드:

  ```tsx
  // apps/web/app/auth/failure/page.tsx (의사 코드, client component)
  'use client';
  import { useEffect } from 'react';
  import { useSearchParams } from 'next/navigation';
  export default function AuthFailure() {
    const sp = useSearchParams();
    useEffect(() => {
      try { window.sessionStorage.removeItem('jippin_oauth_in_progress'); } catch {}
    }, []);
    return /* reason 별 안내 + retry CTA */;
  }
  ```

  결과: 모든 callback 분기 (성공 / cancel / error / missing-code / exchange 실패) 가 client page 를 1번 통과하면서 guard 가 정리된다.
- **JS 비활성 / 페이지 에러** — 위 client page 의 `useEffect` 가 fire 하지 못한다. SessionProvider 의 10분 stale 안전망 (§4.1.1 마지막 bullet) 이 유일 복구 경로. 10분 후 다음 페이지 로드에서 자동 clear.
- **사용자가 OAuth provider 화면에서 탭 이탈** — callback / failure 둘 다 통과하지 않으므로 guard 는 10분 stale 까지 활성. 동일 탭 재진입 시 SessionProvider 가 stale 검사로 정리.

`Clear-Site-Data` 헤더는 위 어떤 경로에서도 사용 금지 — §4.1.1 의 "금지" 규칙 (review item 2) 참조.

### 4.8 Edge proxy (`apps/web/proxy.ts`) 변경

```ts
// 의사 코드
import { type NextRequest, NextResponse } from 'next/server';
import { createProxySupabaseClient } from '@/lib/supabase/proxy';

const PROTECTED_APP_PREFIXES = ['/app/consult', '/app/leads', '/app/reports'];
const ANONYMOUS_ALLOWED_APP_PREFIXES = ['/app/pre-review'];

export async function proxy(request: NextRequest) {
  const response = NextResponse.next();
  const supabase = createProxySupabaseClient(request, response);
  const { data: { user } } = await supabase.auth.getUser();

  const { pathname } = request.nextUrl;
  const isAnonAllowed = ANONYMOUS_ALLOWED_APP_PREFIXES.some(p => pathname.startsWith(p));
  const isProtected = PROTECTED_APP_PREFIXES.some(p => pathname.startsWith(p));

  if (isAnonAllowed || !isProtected) return response;

  // 보호 경로: 익명이 아닌 실명 user 필요
  const isNonAnonymous = user && user.is_anonymous === false;
  if (isNonAnonymous) return response;

  const loginUrl = request.nextUrl.clone();
  loginUrl.pathname = '/login';
  loginUrl.searchParams.set('next', pathname + request.nextUrl.search);
  return NextResponse.redirect(loginUrl);
}

export const config = { matcher: ['/app/:path*'] };
```

핵심:

- `user.is_anonymous` 로 익명/실명 구분. 익명 user 는 `/app/pre-review` 만 허용 (기존 정책 유지).
- 자체 `jippin_session` 쿠키 검사 라인 삭제.
- Supabase `@supabase/ssr` 가 요청 cookie 를 읽고 응답 cookie 를 갱신하므로 `response` 를 그대로 반환해야 token 회전이 클라이언트로 전달된다.

---

## 5. UI / 카피 keep-discard 표

### 5.1 유지

| 위치 | 항목 | 이유 |
|---|---|---|
| `app/layout.tsx` | `LegalNotice` 강제 노출 | AGENTS.md §4.6 — 모든 페이지 봉인. |
| `app/(auth)/login/page.tsx` | 페이지 골격 + "집핀 로그인" 헤더 | 라우트는 그대로. 카피만 §5.2 로 교체. |
| `app/(auth)/login/login-buttons.tsx` | provider 라벨 (`카카오로 시작하기` / `네이버로 시작하기` / `Google 로 시작하기`) | 사용자 노출 문구 유지. 내부 호출 함수만 교체. |
| `/auth/test` 페이지 자체 | 통합 검증 페이지로의 존재 | 흐름이 바뀌어도 검증 페이지는 필요. 본문은 §5.2 로 재작성. |
| `lib/api/error.ts` | 에러 정규화 | Supabase 와 무관. |
| `LegalNotice` | 본문 | 그대로. |

### 5.2 폐기 / 재작성

| 위치 | 항목 | 사유 / 대체 |
|---|---|---|
| `login/page.tsx` | "소셜 OAuth 로 로그인하면 백엔드가 자체 JWT 를 발급합니다." | "Google / 카카오 / 네이버 계정으로 시작하세요. 비밀번호는 만들지 않습니다." 로 교체. 자체 JWT 표현 금지. |
| `login-buttons.tsx` | `GET /auth/{provider}/start?return_url=...&anonymous_user_id=...` 호출 | `linkIdentity` / `signInWithOAuth` 분기 (§4.2.1) + `linkIdentity` 실패 ladder (§4.2.2) + provider mapping (§4.2.3). `redirectTo` 는 항상 `/auth/callback?next=...` 절대 URL. |
| `login-buttons.tsx` | `getOrCreateAnonymousUserId()` import | **Phase 1 유지**, Phase 2 에서 import 제거. ([§9](#9-phase-별-전환-순서)) |
| (신규) `app/auth/callback/route.ts` | (없음) | OAuth provider redirect 의 1차 수신점. `exchangeCodeForSession` + 쿠리 query 비상속 failure URL + merge intent commit + Kakao Sync audit 트리거 (§4.7). |
| (신규) `app/auth/oauth/start/route.ts` | (없음) | OAuth 진입 BFF. `jippin_oauth_provider` flow context 쿠키 + (옵션) `jippin_merge_intent` 쿠키 발급 후 server-side `signInWithOAuth({ skipBrowserRedirect: true })` URL 로 302. 클라이언트가 SDK 를 직접 호출하지 않는 이유는 httpOnly 쿠키 발급을 위한 것 (§4.2.1). |
| (신규) `lib/supabase/providers.ts` | (없음) | UI provider id (`google\|kakao\|naver`) → Supabase provider id 매핑 SSOT (§4.2.3). |
| (신규) `lib/supabase/identities.ts` | (없음) | `detectNewlyLinkedProvider(user, intendedProviderCookie)` — `app_metadata.provider` 단독 누락 케이스 보강 (§4.5.2.1). |
| (신규) `lib/supabase/anonymous-bootstrap.ts` | (없음) | `ensureAnonymousSession(supabase)` — module-scope singleton promise 로 React Strict mode / 다중 mount / multi-tab 동시 호출에서 중복 anonymous user 생성을 방지 (§4.1.0, review item 6). |
| (신규) `lib/safe-redirect.ts` | (없음) | `isSafeNext(next)` — callback `next` allow list 검증 (§4.7.2). |
| (신규) `app/auth/redirect/page.tsx` | (없음) | OAuth 진입 단계 small client page — `sessionStorage.jippin_oauth_in_progress='1'` set 후 `window.location.assign(?to=<oauth_url>)` 로 진짜 OAuth URL 로 navigate (§4.1.1 guard set 시점). server-only 302 만으로는 sessionStorage 를 만질 수 없어 client-side 한 단계가 필수. |
| (신규) `app/auth/callback-done/page.tsx` | (없음) | callback 직후 small client page — `sessionStorage.removeItem('jippin_oauth_in_progress')` 후 `next` 로 navigate (§4.1.1 guard clear 시점). `isSafeNext` 재검증 + invalid 시 Sentry breadcrumb. |
| (재작성) `app/auth/failure/page.tsx` | (placeholder) | client component 로서 mount 시 `sessionStorage.removeItem('jippin_oauth_in_progress')` 호출 — failureRedirect 경로의 guard 정리 책임 (§4.7.4 (d) round-9 강화). reason 별 안내 + retry CTA 도 본 page 책임. |
| `/auth/test` | "비회원 ID" 섹션의 `localStorage.jippin_anonymous_user_id` 표기 | **Phase 1: 양쪽 표시.** Supabase user `id` + `is_anonymous` + legacy `jippin_anonymous_user_id` 를 함께 노출하여 dual-write 가 정합한지 검증. **Phase 2 폐기.** |
| `/auth/test` | `/auth/me` raw fetch | `supabase.auth.getUser()` 결과 + 백엔드 `/users/me` 응답 split 으로 교체. |
| `/auth/test` | `POST /auth/logout` 호출 | `supabase.auth.signOut()` 로 교체. |
| `/auth/test` | "provider link" 섹션의 `POST /auth/sso-accounts/{provider}/link?mode=json` | `supabase.auth.linkIdentity({ provider: toSupabaseProviderId(uiProvider) })` 로 교체. 실패 케이스에서 §4.2.2 fallback ladder 의 모달 동작도 직접 검증 가능하도록 "ladder 강제 트리거" 버튼 추가. |
| `proxy.ts` | `jippin_session` 쿠키 가드 | Supabase session + `is_anonymous` 가드 (§4.8). |
| `lib/auth-token.ts` | 파일 전체 | **Phase 2 삭제** (Phase 1 동안에는 호출자가 줄어들면서 dead code 가 되며, 단일 PR 에서 dual-write 종료와 함께 제거). |
| `lib/anonymous-user.ts` | 파일 전체 | **Phase 2 삭제** ([§1 인벤토리](#1-현-웹-인증-코드-인벤토리-origindev-ad57caa1-기준) / §9). |
| `lib/api-client.ts` | 401 refresh 큐 / `withCredentials` | 재작성 (§4.3). 403 `AUTH_ANONYMOUS_NOT_ALLOWED` 처리 추가 (§4.4). |
| `README.md` (apps/web) | "## 인증 전략 (CMP-529 선택)" 섹션 | "## 인증 전략 (CMP-577 — Supabase Auth 전환 중, Phase 1)" 로 교체. NextAuth v5 언급 제거. Phase 1/2 표 링크. |
| `.env.example` | `AUTH_COOKIE_NAME` 주석 | Phase 1 주석 유지, Phase 2 폐기 표기. |

### 5.3 비목표 (이번 트랙에서 손대지 않음)

- 디자인 SSOT (`docs/brand/...`) 의 색상 / 타이포그래피.
- `/auth/success` · `/auth/failure` 페이지 자체 카피 — 라우팅 흐름만 검증되면 다음 디자인 트랙에서 다듬는다.
- 실제 Supabase 콘솔 세팅 / Custom Provider 등록 / redirect URL 화이트리스트.
- API 측 `/auth/*` 라우트 정리. 웹이 호출하지 않게 되는 시점부터의 cleanup 일정은 Backend/Auth 트랙 합의 후 별도 이슈로 끊는다.

---

## 6. 트랙 간 의존 / 연결점

| 의존 | 무엇 | 본 트랙이 가정하는 것 |
|---|---|---|
| **Backend/Auth — Supabase JWT 검증 + anonymous gating** | `apps/api` 가 `Authorization: Bearer <supabase access_token>` 헤더에서 JWT 를 검증 (JWKS endpoint or HS256 shared secret) 하고 `user.id` + `is_anonymous` claim 을 신뢰. conversion-only 라우트에 §4.3.2 의 403 계약을 적용. | `users.id` 가 Supabase user `id` 와 동일하거나, 매핑 테이블로 1:1 매핑. ADR-0003 의 `external_sso_accounts` 가 Supabase `auth.users` 와 어떻게 정렬되는지는 Backend/Auth 트랙이 결정. |
| **Backend/Auth — `POST /auth/anon-merge-intents` 라우트** | §4.2.2 fallback ladder 의 익명 데이터 이전 큐. 멱등 + 단일 트랜잭션 ownership 이전 + audit log. | 본 트랙은 호출 계약과 payload 만 봉인. |
| **Backend/Auth — `POST /auth/terms/kakao-sync` 라우트** | §4.5.2 경로 (a) 의 callback-side audit insert. 백엔드가 카카오 user-info 재조회 (또는 id_token 파싱) 후 `terms_consents(source='kakao_sync')` 단일 트랜잭션 insert. | 콜백 실패 대비 reconcile 잡도 owner. |
| **ADR-0003 supersede (=ADR-0004 가칭)** | ADR-0003 의 "익명 식별자 = localStorage.jippin_anonymous_user_id" / "POST /auth/anonymous-users 발급 라우트" 결정을 supersede 하는 ADR-0004 신규 작성 + Accepted. | **본 runbook 의 Phase 2 작업 (localStorage 키 삭제, `lib/anonymous-user.ts` 삭제, dual-write 종료) 은 ADR-0004 Accepted 또는 동등한 supersede 자식 이슈 완료 전까지 코드/PR 에서 수행하지 않는다.** Phase 1 PR (= 본 PR) 은 ADR-0003 정본을 유지한다. |
| **Supabase 콘솔 세팅** | Project 생성, OAuth provider 등록 (Google native + Kakao/Naver Custom OAuth), redirect URL 화이트리스트 (`/auth/callback` 만 등록 — `/auth/success` 는 등록 불필요, §4.7.2), Email/Phone provider OFF, Anonymous sign-in ON, Identity Linking 정책 = "수동". | 본 트랙은 콘솔 작업을 수행하지 않는다. 변수명·기능 flag 만 봉인. |
| **ADR-0003 §2.3 + CMP-572 자동 병합 금지** | Supabase 콘솔의 동일 verified email auto-link / Account Linking auto / "Link accounts with same email" 옵션이 모두 OFF. CMP-572 CEO 결정 (§0.0) 으로 hard-requirement 격상. | 콘솔 세팅 트랙이 라이브 전 강제 검증. 켜진 상태로 라이브 가면 본 runbook + CMP-572 + ADR-0003 동시 위반 — 발견 즉시 라이브 차단. |
| **약관 동의 흐름 (Google · Naver)** | `terms_consents(source='internal_signup')` 데이터는 백엔드가 owner. Supabase user metadata 에는 약관 동의를 저장하지 않는다. | `POST /auth/terms/accept` 라우트 자체는 유지되지만 호출자가 보내는 token 이 자체 JWT → Supabase access token 으로 바뀐다. |
| **약관 동의 흐름 (Kakao Sync)** | `terms_consents(source='kakao_sync')` 는 §4.5.2 경로 (a) 로 callback-side 에서 insert. | Backend/Auth 트랙이 (b)/(c) 경로로 합의 변경 시 본 runbook §4.5.2 갱신. |

---

## 7. 검증

본 트랙은 설계 / 스캐폴드까지이므로 라이브 Supabase 검증은 후속 이슈에서 수행한다.

| 단계 | 검증 | 본 트랙에서 가능? |
|---|---|---|
| Lint / Typecheck | `pnpm lint`, `pnpm typecheck` 가 본 PR 의 변경 후에도 통과. | **예** (라이브 키 불요). |
| Build | `pnpm build` 가 통과. | **예** (env 미설정 시 runtime fail 만 발생, build 통과). |
| 익명 sign-in 실호출 | `supabase.auth.signInAnonymously()` 가 실제 Supabase project 에 세션을 만든다. | **아니오** (콘솔 세팅 + env 필요. 후속 트랙). |
| OAuth 라이브 | Kakao/Naver/Google 로그인 실 흐름. | **아니오** (콘솔 + provider client ID/secret 필요. 후속 트랙). |
| linkIdentity 검증 | 익명 → 실명 전환 시 user `id` 유지. | **아니오** (콘솔). |

---

## 8. 블로커 / 사용자 입력 필요 항목

본 트랙은 다음 값을 코드/문서에 기재하지 않는다. 라이브 검증 단계에 진입할 때 다음을 사용자에게 정확히 요청한다 (AGENTS.md §4.4 / ADR-0003 시크릿 봉인).

| 입력 항목 | 보관 위치 | 사유 |
|---|---|---|
| Supabase project URL | `apps/web/.env.local::NEXT_PUBLIC_SUPABASE_URL` | 브라우저 노출 OK. |
| Supabase `anon` key | `apps/web/.env.local::NEXT_PUBLIC_SUPABASE_ANON_KEY` | 브라우저 노출 OK. |
| Supabase `service_role` key | `apps/api/.env.local::SUPABASE_SERVICE_ROLE_KEY` | **웹에 두지 않음.** |
| Google OAuth client ID/secret | Supabase 콘솔 → Auth → Providers → Google | 웹·API 모두에 두지 않음. |
| Kakao OAuth client ID/secret | Supabase 콘솔 → Auth → Providers → **Kakao** (Supabase native built-in provider 패널) | 동일. **Custom 경로 없음** — §4.2.3 매핑 표 정합. provider identifier = `kakao` 고정. |
| **Naver Custom OAuth2 (not OIDC)** — client ID / secret / authorize URL / token URL / user-info URL / scope / email_optional | Supabase 콘솔 → Auth → Providers → **Custom OAuth Provider (`OAuth2 (Generic)` 모드)** | §4.3.1 봉인. **OIDC 모드 금지** (Naver 는 `.well-known/openid-configuration` 미지원). 입력 필드는 변수명 `NAVER_OAUTH_CLIENT_ID` / `NAVER_OAUTH_CLIENT_SECRET` / `NAVER_OAUTH_AUTHORIZE_URL` / `NAVER_OAUTH_TOKEN_URL` / `NAVER_OAUTH_USERINFO_URL` / (옵션) `NAVER_OAUTH_SCOPE` 로 SSOT — AGENTS.md §4.7 정합. 실값은 코드 / 문서 / 이슈에 절대 기재 금지. provider identifier = `naver` (prefix 없이) 고정 — Supabase 가 SDK 측에서 `custom:` 를 자동 prepend 하여 `custom:naver` 가 된다 (§4.2.3 매핑). **Scope 필드는 비워둔다 (default `''`, round-4 봉인)** — Naver authorize 가 scope 파라미터를 정식 사양에 두지 않으므로 임의 토큰을 보내면 `invalid_request` 위험. 사용자 동의 항목은 Naver Developers 콘솔 UI 에서 별도 선언. **`email_optional=true` 필수** — Phase 1 은 email 동의 항목을 요구하지 않으므로 user-info `response.email` 부재 가능 → OFF 면 `auth.users` insert 가 `email_required` 로 실패해 사용자 가입 자체가 막힌다 (§4.3.1 round-3 봉인). |
| **Provider 화이트리스트 정책** | Supabase 콘솔 → Auth → Providers — **Email provider OFF**, Phone provider OFF, magic link OFF, OTP OFF, SMS OFF, anonymous sign-in 만 별도 ON. UI 노출은 `ALLOWED_PROVIDERS = ['google','kakao','naver']` 한정 (§4.2.5). | §4.2.5 / CMP-584. 위 비-OAuth 경로 중 하나라도 ON 인 상태로 라이브 가면 §0.0 CMP-572 CEO 결정의 "자동 verified email merge 우회로" 위험. 즉시 라이브 차단. |
| Identity Linking 정책 | Supabase 콘솔 → Auth → Settings → **Account Linking = `manual only`**, "Auto-link verified emails" / "Link accounts with same email" 모두 OFF | **§0.0 CMP-572 CEO 결정 + ADR-0003 §2.3.** 위 토글 중 하나라도 ON 인 상태로 라이브 가면 본 runbook 위반 → 즉시 라이브 차단. Identity Linking 자체 기능 (`auth.linkIdentity` 호출 권한) 은 ON 이어야 한다 (manual flow 의 진입 권한). |
| **ADR-0003 supersede 결정 (=ADR-0004)** | `docs/adr/0004-*.md` 신규 + Accepted | Phase 2 (localStorage 키 제거, `lib/anonymous-user.ts` 제거, dual-write 종료) 가 시작될 수 있는 유일한 gate. ADR-0004 가 Accepted 되기 전에는 본 runbook 도 Phase 1 동작만 봉인한다. |
| **Kakao Sync 동의 audit 경로 합의** | §4.5.2 표의 (a) / (b) / (c) 중 어느 경로를 봉인할지 Backend/Auth 트랙이 결정 | 본 runbook 은 (a) 로 가정. (b)/(c) 결정 시 본 절 갱신. |

값이 모이지 않은 동안 본 이슈는 설계 산출물(본 문서 + env 변수 + UI 변경 계획) 완료로 종결한다. 라이브 검증은 별도 자식 이슈 (`[SUPABASE][WEB] live wiring + smoke`) 로 분리한다.

---

## 9. Phase 별 전환 순서

본 runbook 은 ADR-0003 정본을 유지한 상태로 **단계적 전환** 을 봉인한다. 단일 PR 에서 전부 폐기하지 않는다. ADR-0003 §2 (익명 식별자 / 발급 라우트 / 콜백 트랜잭션 claim) 은 ADR-0004 (가칭, Supabase Auth supersede) 가 Accepted 되기 전까지 살아 있다.

| Phase | 진입 조건 | 본 runbook 이 봉인하는 작업 | 종료 조건 |
|---|---|---|---|
| **0 — 설계 봉인** | (현재) | 본 문서, env 변수명, SSOT 디렉터리 구조, 흐름 설계 | 본 PR 머지 |
| **1 — Supabase adapter 도입 + dual-write** | Phase 0 종료 + Supabase 콘솔 세팅 + 라이브 키 입력 (§8) + Backend/Auth 트랙의 JWT 검증 라우트 + `POST /auth/anon-merge-intents` + `POST /auth/terms/kakao-sync` 라우트 완료 | • `lib/supabase/*` 추가 · `/auth/callback` Route Handler 신설 (§4.7)<br>• `signInAnonymously` + 기존 `getOrCreateAnonymousUserId()` 를 **둘 다** 호출 (§4.1 dual-write)<br>• axios 인터셉터: `Authorization: Bearer <supabase>` + `x-jippin-anon-id: <legacy>` 헤더 동시 전송<br>• login-buttons → `linkIdentity` / `signInWithOAuth` 분기 + fallback ladder (§4.2)<br>• `/auth/test` 페이지가 Supabase + legacy 양쪽 ID 를 표시 (정합 검증)<br>• proxy.ts 가 Supabase 세션 + `is_anonymous` 가드로 전환 (§4.8)<br>• `lib/auth-token.ts` 는 호출자 제거하되 파일 유지<br>• `lib/anonymous-user.ts` 는 유지 (dual-write 책임)<br>• Kakao Sync audit insert (§4.5.2 경로 (a)) 활성화 | ADR-0004 Accepted (또는 ADR-0003 supersede 자식 이슈 완료) |
| **2 — Legacy 폐기** | ADR-0004 Accepted | • `lib/anonymous-user.ts` 삭제<br>• `localStorage.jippin_anonymous_user_id` 폐기<br>• axios 의 `x-jippin-anon-id` 헤더 제거<br>• `lib/auth-token.ts` 파일 삭제<br>• `.env.example` 의 `AUTH_COOKIE_NAME` 주석 라인 제거<br>• `/auth/test` 에서 legacy 표시 라인 제거<br>• ADR-0003 §2 의 익명 발급 라우트 호출 코드 일괄 제거<br>• backend 측 `anonymous_users` 테이블 / `POST /auth/anonymous-users` cleanup 은 Backend/Auth 트랙 별도 이슈로 끊는다 (web 트랙 비범위) | Live smoke 통과 (`[SUPABASE][WEB] live wiring + smoke` 자식 이슈) |

> **위반 케이스 — 즉시 차단.** ADR-0004 Accepted 전에 Phase 2 변경 (예: `localStorage.jippin_anonymous_user_id` 키 삭제, `POST /auth/anonymous-users` 호출 제거) 을 포함한 PR 은 **본 runbook 위반** 으로 reject 한다.

---

## 10. 변경 절차

- 본 runbook 의 흐름·환경변수·SSOT 디렉터리 구조·Phase 표는 본 PR 머지 시점부터 봉인된다. 변경 시 새 PR + 본 문서 갱신을 같은 커밋에 포함.
- ADR-0003 의 결정 (provider 3종, 자동 병합 금지, 약관 source 분리) 은 본 runbook 보다 상위. 충돌 시 ADR-0003 가 우선. ADR-0004 Accepted 시점 이후에는 ADR-0004 가 §2 범위에서 우선.
- Supabase SDK major 버전 변경 (`@supabase/supabase-js` v3 등) 은 새 runbook 절 / ADR 로 처리.
- §9 Phase 표의 진입/종료 조건은 본 runbook 의 SSOT. 다른 트랙의 progress 추적 문서가 Phase 정의를 바꾸려면 본 절을 먼저 갱신한다.

---

## 11. Open review handoff (Phase 1 자식 이슈)

PR [#42](https://github.com/J511Y/Jippin/pull/42) 의 잔여 review thread (2026-06-01 기준 13건 non-outdated) 는 round-2 ~ round-9 누적 incremental 패치로 더는 닫히지 않는다. 본 runbook 은 Phase 0 (설계 봉인) 의 SSOT 로서 봉인되며, 잔여 review 항목은 Phase 1 자식 이슈로 분리해 **실 코드 구현 단계에서 봉인**한다.

### 11.1 자식 이슈 매핑

| 자식 이슈 | 영역 | 포함 thread | runbook anchor |
|---|---|---|---|
| **CMP-579** [Phase 1 (a)](/CMP/issues/CMP-579) | OAuth callback ladder & guard cleanup | R1, R5, R7, R8, R12 | §4.2 / §4.7 |
| **CMP-580** [Phase 1 (b)](/CMP/issues/CMP-580) | SSR cookie adapter & PKCE preservation | R2, R10 | §4.2.1 BFF |
| **CMP-581** [Phase 1 (c)](/CMP/issues/CMP-581) | Anonymous gate & Kakao Sync audit | R3, R4, R9, R13 | §4.1 / §4.4 / §4.5.2 / §8 |
| **CMP-582** [Phase 1 (d)](/CMP/issues/CMP-582) | Open redirect hop & login next | R6, R11 | §4.6 / §4.2.1 |
| **CMP-584** [Phase 1 (e)](/CMP/issues/CMP-584) | Provider 화이트리스트 + Naver Custom OAuth2 (not OIDC) | round-11 wake item 5 | §4.2.5 / §4.3.1 / §8 |

### 11.2 잔여 review thread → 자식 이슈 매핑

| ID | runbook 줄 | 영역 요지 | 처리 자식 이슈 |
|---|---|---|---|
| R1 (`PRRT_kwDOSp2wlM6F_CSA`) | §4.7.4 / line ~760 | callback 실패 분기에서 `jippin_merge_intent` / `jippin_oauth_provider` 쿠키 즉시 삭제 | CMP-579 |
| R2 (`PRRT_kwDOSp2wlM6F_CSD`) | §4.2.1 / line ~99 | OAuth start 302 응답에 Supabase 가 set 한 PKCE cookie 가 brower 까지 전달되도록 Set-Cookie 위임 | CMP-580 — PR [#47](https://github.com/J511Y/Jippin/pull/47) `fd1c85dd` (`apps/web/app/auth/oauth/start/route.ts`) |
| R3 (`PRRT_kwDOSp2wlM6F_Jq6`) | §4.5.2 / line ~576 | SSOT path 표 의 `id_token` 잔재 제거, 정본은 `provider_access_token` | CMP-581 — PR [#46](https://github.com/J511Y/Jippin/pull/46) `2a411974` (`apps/web/lib/kakao-sync-audit.ts`) |
| R4 (`PRRT_kwDOSp2wlM6F_Jq9`) | §4.1 / line ~142 | anonymous sign-in abuse-control gate (Turnstile / intent confirm / IP rate-limit) | CMP-581 — PR [#46](https://github.com/J511Y/Jippin/pull/46) `2a411974` (`apps/web/lib/anonymous-gate.ts`) |
| R5 (`PRRT_kwDOSp2wlM6F_Jq_`) | §4.2.1 / line ~380 | merge `signed_token` 을 web BFF 가 받아 `jippin_merge_intent` 쿠키에 set | CMP-579 |
| R6 (`PRRT_kwDOSp2wlM6F_JrA`) | §4.6 / line ~1032 | `/auth/redirect?to=` open redirect 차단 (nonce 또는 origin allow-list) | CMP-582 |
| R7 (`PRRT_kwDOSp2wlM6F_JrC`) | §4.7.4 / line ~760 | callback 실패 분기에서 `sessionStorage.jippin_oauth_in_progress` 명시 정리 | CMP-579 |
| R8 (`PRRT_kwDOSp2wlM6F_Ntr`) | §4.7.4 / line ~759 | `error=identity_already_exists` 분기 → §4.2.2 migration ladder 진입점 | CMP-579 |
| R9 (`PRRT_kwDOSp2wlM6F_Ntv`) | §4.3 / line ~429 | SDK provider id default 가 콘솔 매핑 (`custom:kakao` 가능) 와 정합 | CMP-581 — PR [#46](https://github.com/J511Y/Jippin/pull/46) `2a411974` (`apps/web/lib/oauth-providers.ts`) |
| R10 (`PRRT_kwDOSp2wlM6F_SzM`) | §4.2.1 / line ~308 | `@supabase/ssr` v0.5+ 표준 `getAll`/`setAll` 패턴 SSR cookie adapter | CMP-580 — PR [#47](https://github.com/J511Y/Jippin/pull/47) `fd1c85dd` (`apps/web/lib/supabase/{server,proxy}.ts`) |
| R11 (`PRRT_kwDOSp2wlM6F_SzP`) | §4.2.1 / line ~326 | `/login?next=...` 가 OAuth start → callback → next-navigation 까지 보존 | CMP-582 |
| R12 (`PRRT_kwDOSp2wlM6F_SzR`) | §4.2.2 / line ~392 | merge commit endpoint 정본은 cookie-only path 단일 (`POST /auth/anon-merge-intents/commit`) | CMP-579 |
| R13 (`PRRT_kwDOSp2wlM6F_SzS`) | §4.5.2 / line ~636 | Kakao consent sync `fetch()` 응답에서 `response.ok` 명시 검증 | CMP-581 — PR [#46](https://github.com/J511Y/Jippin/pull/46) `2a411974` (`apps/web/lib/kakao-sync-audit.ts`) |

### 11.3 봉인 규칙

- 본 runbook 의 §1–§10 본문은 Phase 0 SSOT 로서 **본 PR 머지 시점에 봉인**된다. PR #42 의 잔여 review thread 13건은 본 §11 표를 통해 Phase 1 자식 이슈로 위임되며, 본 PR 머지가 위 13건 thread 해결의 사전 조건은 아니다.
- 각 자식 이슈는 해당 row 의 `runbook anchor` 절을 SSOT 로 참조하며, 코드 구현 시 anchor 절과 충돌하면 자식 이슈가 본 runbook 을 갱신하는 같은 커밋을 동반한다 (§10 변경 절차).
- 자식 이슈 4개가 모두 `done` 으로 종료되면 Paperclip `issue_children_completed` wake 가 CMP-577 의 assignee 를 깨우고, 본 이슈는 최종 `done` 처리된다.

— 끝 —

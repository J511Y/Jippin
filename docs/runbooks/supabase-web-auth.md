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
| **OAuth provider** | UI 노출 정본은 `google`, `kakao`, `naver` (ADR-0003 봉인). Supabase native = `google` 만. Kakao / Naver 는 Supabase Custom OAuth (OIDC) 로 등록하고 SDK 호출 시 `custom:<id>` 식별자로 매핑한다 — UI provider id → Supabase provider id 변환은 [§4.2.3 provider mapping](#423-provider-id-매핑) 표 단일 SSOT 가 owner. |
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

### 2.1 의존성

`apps/web/package.json` `dependencies` 에 추가:

```json
"@supabase/supabase-js": "^2.45.0",
"@supabase/ssr": "^0.5.0"
```

> 정확한 minor 는 설치 시점에 lockfile 로 봉인한다. Major 만 ^2 / ^0 으로 명시. Next.js 16 App Router 와 `@supabase/ssr` 의 cookie 통합은 v0.5+ 가 안정 라인.

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
  3. **PKCE verifier cookie (필수).** server-side `linkIdentity` / `signInWithOAuth` 호출은 `@supabase/ssr` `createServerClient({ cookies: { get, set, remove } })` 의 cookie adapter 를 통해 `sb-<project-ref>-auth-token-code-verifier` 쿠키를 발급한다. **BFF 의 응답은 이 Set-Cookie 를 그대로 운반해야** callback 의 `exchangeCodeForSession(code)` 가 verifier 를 읽어 PKCE 교환을 완료할 수 있다. Route Handler 패턴에서 cookie adapter 는 동일 `NextResponse` 인스턴스에 바인딩하므로, 아래 4번의 302 응답을 **만들고 나서** SDK 를 호출하지 말고, 응답 객체를 먼저 만들어 SDK 에 cookie adapter 로 넘기고 마지막에 redirect 시킨다.
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
| `kakao` | `'kakao'` (native) — Supabase 가 native 로 추가했는지 콘솔 세팅 트랙이 확인. **없으면 `'custom:kakao'`** 로 fallback. | Kakao Sync 동의 화면을 OAuth 화면에서 표시하려면 콘솔에서 `scope=profile_nickname,profile_image,account_email,gender,birthyear,birthday,terms_of_service` 등 명시적 입력 필요. |
| `naver` | **`'custom:naver'`** | Supabase 는 Naver native provider 를 제공하지 않으므로 OIDC Custom Provider 로 등록한다. UI / 분석 / 텔레메트리 코드는 여전히 `'naver'` 식별자를 그대로 쓰며, **본 매핑 함수만이 SDK 경계에서 변환** 한다. |

매핑 함수 서명 (의사 코드):

```ts
// apps/web/lib/supabase/providers.ts
export type UiProvider = 'google' | 'kakao' | 'naver';
export type SupabaseProvider = 'google' | 'kakao' | `custom:${string}`;

const MAP: Record<UiProvider, SupabaseProvider> = {
  google: 'google',
  kakao:  'kakao',       // Supabase 가 native 미지원이면 'custom:kakao' 로 교체 (콘솔 세팅 트랙 결정).
  naver:  'custom:naver',
};

export function toSupabaseProviderId(ui: UiProvider): SupabaseProvider {
  return MAP[ui];
}
```

- 본 매핑을 거치지 않은 raw UI 식별자가 SDK 에 도달하면 `signInWithOAuth({ provider: 'naver' })` 가 Supabase 측에서 invalid provider 로 실패한다.
- Custom Provider 등록 시 콘솔에서 부여하는 identifier 가 `naver` 가 아닌 다른 값으로 결정되면, 본 매핑 함수만 한 줄 갱신하고 UI 는 손대지 않는다.
- 라이브 검증 단계에서 카카오 native 지원 여부가 확정되면 `MAP.kakao` 도 한 줄로 교체한다.

#### 4.2.4 일반 에러 처리

- `redirectTo` 가 Supabase 콘솔의 redirect allow list 에 없으면 SDK 가 즉시 에러. UI 는 "관리자에게 문의" toast 노출 + Sentry/log 캡처.
- provider OAuth error (사용자 취소, scope 거부) 는 callback 에서 처리하여 `FAILURE_URL` 로 302 (§4.7).

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

### 4.4 anonymous gating contract (conversion-only 엔드포인트)

> **문제.** Supabase 익명 user 도 유효한 access token 을 받는다 (`is_anonymous=true` claim 포함). 백엔드가 token 검증 직후 `user.id` 만 신뢰하면 익명 access token 으로도 상담 저장 / 리드 / 리포트 발급을 호출할 수 있다 — ADR-0003 §2.2 "비회원은 사전검토만" 정책 위반.

본 트랙은 다음을 **web → backend 계약**으로 봉인한다 (실제 enforcement 는 Backend/Auth 트랙 owner — 별도 자식 이슈에서 단위 테스트로 강제):

| 엔드포인트 분류 | 예시 라우트 | 허용되는 인증 입력 | 거부 응답 |
|---|---|---|---|
| **공개 / 사전검토** (anonymous 허용) | `GET /catalog/*`, `POST /pre-review/run`, `GET /pre-review/{id}` | anonymous Supabase access token **OR** non-anonymous Supabase access token **OR** Phase 1 한정 `x-jippin-anon-id: <legacy uuid>` (Supabase 도달 실패 fallback — §4.1 fail-soft (A)). 셋 다 없으면 익명 핸들 발급 후 응답. | 401 만 비정상적 케이스 (legacy header 도 invalid format). |
| **conversion-only — 사용자 영속 데이터** | `POST /consults`, `GET /consults/{id}`, `POST /leads`, `POST /reports`, `GET /users/me`, `POST /auth/terms/*` | **non-anonymous Supabase access token 만**. legacy `x-jippin-anon-id` 헤더는 **절대 허용하지 않는다** — 영구 데이터를 만들 수 없으므로. | `403` + 본문은 repo 표준 envelope (§4.4.1) |
| **conversion intent** | `POST /auth/anon-merge-intents`, `POST /auth/anon-merge-intents/commit` | anonymous **또는** non-anonymous (각각 from/target 측에서 호출) | 잘못된 단계의 token 은 422. |

검증 우선순위 (Backend/Auth 트랙 가이드 — web 트랙은 호출자 입장에서 신뢰):

1. JWT 서명 / `aud` / 만료 검증.
2. `is_anonymous` claim 추출. claim 이 없거나 `true` 이고 라우트가 conversion-only 분류면 즉시 403.
3. (선택) backend 의 `users` 테이블에 해당 user id 가 존재하고 `is_active=true` 인지 cross-check. Supabase 콘솔에서 admin 이 user 를 비활성화한 케이스 방어.

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

- axios 인터셉터는 `parseApiError(err)` (`apps/web/lib/api/error.ts:60-95`) 를 호출하여 위 envelope 을 `ApiError { code, message, requestId, timestamp, status, cause }` 로 정규화. **`apiError.code === 'AUTH_ANONYMOUS_NOT_ALLOWED'` 분기로 logout/login modal 로 전환** (자동 token 재시도 금지). flat body (`{ code, message }`) 를 직접 읽는 일이 없도록 모든 호출자가 `parseApiError` 를 거친다.
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
| **(a)** | **Callback Route Handler 직후 backend sync** — `/auth/callback` 가 `exchangeCodeForSession` 성공 직후, Supabase session 의 provider id (`'kakao'` / `'custom:kakao'`) 가 카카오인 경우 `POST /auth/terms/kakao-sync` 호출. payload = `{ supabase_user_id, id_token, raw_kakao_payload(있을 시) }`. backend 가 token claims 에서 동의 항목을 파싱 또는 카카오 user-info API 를 재조회하여 `terms_consents(source='kakao_sync')` 단일 트랜잭션 insert. | Web (호출 위치) + Backend (검증/저장) | 흐름이 명시적이고 추적 가능. Supabase webhook 의존 없음. | callback 가 실패하면 동의 기록이 누락 — fallback 필요 (§4.5.2 끝). |
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

backend 측 처리 합의 (Backend/Auth 트랙 owner):

1. `Authorization` 검증 → `supabase_user_id` 와 token sub 일치 확인.
2. `provider_access_token` 으로 `https://kapi.kakao.com/v2/user/scopes` 호출 → 동의된 scope 목록 수신.
3. (옵션) `/v2/user/me?secure_resource=true` 로 추가 정보 수신.
4. `terms_consents(source='kakao_sync', user_id, term_id, version, agreed_at=now)` insert (UNIQUE 충돌 시 멱등 무시).
5. 응답 4xx 면 callback 측은 best-effort 로 swallow, reconcile 잡이 사후 보정.

> `provider_access_token` 은 본 callback 1회 호출에만 사용하고 backend 는 보관하지 않는다 (PII / 추가 권한 누설 방지). 보관이 필요해지면 ADR 갱신.

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
// 모든 callback-scoped cookie 를 한 번에 정리. stale intent 가 다음 OAuth callback 에 소비되어
// 잘못된 merge 가 발생하지 않게 한다 (review item 3).
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
  if (mergeIntentCookie) {
    try {
      await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/auth/anon-merge-intents/commit`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${data.session.access_token}`,
        },
        body: JSON.stringify({ signed_intent_cookie_value: mergeIntentCookie }),
      });
    } catch (e) {
      console.warn('[auth/callback] anon merge commit failed', e);
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
  done.searchParams.set('next', safeNext);
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
| (신규) `lib/safe-redirect.ts` | (없음) | `isSafeNext(next)` — callback `next` allow list 검증 (§4.7.2). |
| (신규) `app/auth/redirect/page.tsx` | (없음) | OAuth 진입 단계 small client page — `sessionStorage.jippin_oauth_in_progress='1'` set 후 `window.location.assign(?to=<oauth_url>)` 로 진짜 OAuth URL 로 navigate (§4.1.1 guard set 시점). server-only 302 만으로는 sessionStorage 를 만질 수 없어 client-side 한 단계가 필수. |
| (신규) `app/auth/callback-done/page.tsx` | (없음) | callback 직후 small client page — `sessionStorage.removeItem('jippin_oauth_in_progress')` 후 `next` 로 navigate (§4.1.1 guard clear 시점). |
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
| Kakao OAuth client ID/secret | Supabase 콘솔 → Auth → Providers → Custom (OIDC) | 동일. |
| Naver OAuth client ID/secret | Supabase 콘솔 → Auth → Providers → Custom (OIDC) | 동일. |
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

— 끝 —

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
| **OAuth callback route** | provider redirect URL 은 `/auth/success` 가 아니라 **`/auth/callback?next=<원래 목적지>`**. 콜백 Route Handler 가 `exchangeCodeForSession(code)` 로 PKCE 코드를 세션 쿠키로 교환한 뒤 `next` 로 302. Supabase 콘솔 redirect allow list 도 `/auth/callback` 기준으로 등록한다 ([§4.7](#47-oauth-callback-route--exchangecodeforsession)). |
| **FastAPI 호출** | `Authorization: Bearer <session.access_token>` 헤더 주입. 자체 refresh 인터셉터 폐기 — Supabase SDK 의 토큰 자동 갱신을 신뢰. **API 측 anonymous 거부 계약.** Conversion-only 엔드포인트(상담 저장 / 리드 / 리포트 발급)는 token 의 `is_anonymous` claim 이 `false` 임을 강제하거나 backend 측 user state 로 거부한다 ([§4.4 anonymous gating contract](#44-anonymous-gating-contract-conversion-only-엔드포인트)). |
| **Edge proxy 가드** | `proxy.ts` 는 `jippin_session` 쿠키 대신 `@supabase/ssr` 의 `createServerClient` 로 세션을 읽고, anonymous user 도 비보호 경로(`/app/pre-review`)에 들어올 수 있게 한다. |
| **Kakao Sync 동의 audit** | Supabase hosted OAuth 가 사용자 동의 화면 owner. callback Route Handler 가 `exchangeCodeForSession` 직후 `POST /auth/terms/kakao-sync` (백엔드 신규) 로 Supabase access token + Kakao consent payload (id_token 또는 user-info) 를 함께 전달 → backend 가 `terms_consents.source='kakao_sync'` 를 단일 트랜잭션 insert. 콜백이 실패하면 사용자에게 "동의 기록 실패, 다시 로그인" 으로 fallback ([§4.5.2](#452-kakao-sync-동의-audit-persistence)). |
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
| `apps/web/app/(auth)/login/login-buttons.tsx` | `GET /auth/{provider}/start?return_url=...&anonymous_user_id=...` 로 브라우저 redirect. | **재작성.** `signInWithOAuth` / `linkIdentity` 분기 + `linkIdentity` 실패 fallback (§4.2.2). provider id 는 `lib/supabase/providers.ts` 매핑 함수를 거쳐 Supabase 식별자로 변환 (§4.2.3). `redirectTo` 는 항상 `/auth/callback?next=...` 절대 URL. anonymous_user_id 쿼리는 Phase 2 시점에 폐기 (Phase 1 는 dual-write 위해 호출 유지). |
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
└── session.ts       # SessionUser 타입 정의 + 익명/실명 구분 헬퍼
```

추가로 callback Route Handler 가 `apps/web/app/auth/callback/route.ts` 신설된다 (§4.7).

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
  1) supabase.auth.getSession() → 세션 있음? then no-op
  2) 세션 없음 → supabase.auth.signInAnonymously()
  3) onAuthStateChange listener 등록 → React Query / UI 가 의존하는 SessionContext 업데이트
  ```

- **호출 보장.** 익명 sign-in 은 페이지 첫 진입 1회만 호출되어야 한다 (Strict mode, refresh, navigation 모두에서). 정합을 위해:
  - `getSession` 결과를 await 한 뒤에만 `signInAnonymously` 를 호출.
  - SSR 측 `server.ts` 에서도 동일하게 `getSession` 만 수행하고 익명 발급은 **클라이언트에서만** 한다 (Supabase 의 anonymous user 는 client SDK 가 anon key 로 발급하는 것이 표준).
  - SSR 단계에서 세션이 없는 사용자는 빈 user 컨텍스트로 렌더링되고, 클라이언트 hydration 직후 익명 세션이 생성된다.

- **fail-soft.** `signInAnonymously` 실패 시:
  - 비회원 사전검토 흐름 (`/app/pre-review`) 은 그대로 진입 허용하되, user-aware 기능 (도면 저장, 이력) 은 disabled 표기.
  - 재시도 버튼을 LegalNotice 또는 sticky toast 로 노출 (UX 트랙 후속).

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
   │            payload: { from_anon_user_id, from_legacy_anon_id, target_provider }.
   │         b) supabase.auth.signOut()  // 익명 세션 폐기
   │         c) supabase.auth.signInWithOAuth({ provider }) 로 기존 계정 로그인.
   │         d) callback Route Handler 가 세션 확보 직후
   │            `POST /auth/anon-merge-intents/{id}/commit` 호출 → backend 가
   │            target_user_id 로 도면/리포트 ownership 이전 (단일 트랜잭션, audit log 포함).
   │         e) 사용자에게 "이전 완료" toast.
   │      3) "아니오" 선택 시: 익명 세션 유지, login modal 닫기. 사용자는 다른 provider 로 재시도 가능.
   │
   └─ 그 외 일반 실패 (네트워크 / provider OAuth error) ⇒ §4.2.4 일반 에러 처리.
```

- **`POST /auth/anon-merge-intents` 는 Backend/Auth 트랙 신설 라우트** (본 트랙은 web 측 호출 계약과 payload 만 봉인한다). 백엔드가 ADR-0003 의 anonymous_users + 신규 supabase user 매핑을 검증하고 ownership 이전을 단일 트랜잭션으로 처리한다.
- intent 큐는 멱등 키 (`from_anon_user_id + target_provider`) 로 중복 제출을 흡수한다. 사용자가 모달을 두 번 띄워도 데이터가 두 번 옮겨지지 않는다.
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

| 엔드포인트 분류 | 예시 라우트 | 허용되는 token | 거부 응답 |
|---|---|---|---|
| **공개 / 사전검토** (anonymous 허용) | `GET /catalog/*`, `POST /pre-review/run`, `GET /pre-review/{id}` | anonymous OR non-anonymous Supabase access token | 401 (no token) |
| **conversion-only — 사용자 영속 데이터** | `POST /consults`, `GET /consults/{id}`, `POST /leads`, `POST /reports`, `GET /users/me`, `POST /auth/terms/*` | **non-anonymous Supabase access token 만** | `403 AUTH_ANONYMOUS_NOT_ALLOWED` (구조: `{ "code": "AUTH_ANONYMOUS_NOT_ALLOWED", "message": "...", "next": "/login" }`) |
| **conversion intent** | `POST /auth/anon-merge-intents`, `POST /auth/anon-merge-intents/{id}/commit` | anonymous **또는** non-anonymous (각각 from/target 측에서 호출) | 잘못된 단계의 token 은 422. |

검증 우선순위 (Backend/Auth 트랙 가이드 — web 트랙은 호출자 입장에서 신뢰):

1. JWT 서명 / `aud` / 만료 검증.
2. `is_anonymous` claim 추출. claim 이 없거나 `true` 이고 라우트가 conversion-only 분류면 즉시 403.
3. (선택) backend 의 `users` 테이블에 해당 user id 가 존재하고 `is_active=true` 인지 cross-check. Supabase 콘솔에서 admin 이 user 를 비활성화한 케이스 방어.

웹 측 호출자의 응답 처리:

- 403 + `code=AUTH_ANONYMOUS_NOT_ALLOWED` 를 받으면 axios 인터셉터가 logout/login modal 로 전환 (자동 token 재시도 금지). 사용자가 비회원 상태에서 conversion-only 라우트를 직접 호출한 경우이므로 UI 단에서도 버튼을 disabled 로 두는 것이 정합이지만, 깊은 링크 / 캐시된 페이지를 통해 호출이 새는 경우의 안전망.

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

**경로 (a) 의 web 측 의사 코드** (`/auth/callback/route.ts` 발췌 — 전체 코드는 §4.7):

```ts
const { data: { session }, error } = await supabase.auth.exchangeCodeForSession(code);
if (error || !session) {
  return NextResponse.redirect(new URL(FAILURE_URL, request.url));
}

const provider = session.user.app_metadata?.provider; // 'kakao' or 'custom:kakao'
if (provider === 'kakao' || provider === 'custom:kakao') {
  // Best-effort. 실패해도 로그인 자체는 진행. 별도 reconcile 잡으로 추적 (§4.5.2 fallback).
  try {
    await fetch(`${API_BASE}/auth/terms/kakao-sync`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${session.access_token}`,
      },
      body: JSON.stringify({
        supabase_user_id: session.user.id,
        // Supabase 는 provider id_token 을 session.provider_token / provider_refresh_token 로 노출.
        // 카카오 응답 본문 raw 는 보관되지 않으므로 backend 가 카카오 user-info API 를 재조회한다.
        id_token: session.provider_token ?? null,
      }),
    });
  } catch (e) {
    console.warn('[auth/callback] kakao-sync persistence failed', e);
  }
}
```

**fallback (audit 누락 방어).**

- 백엔드는 `terms_consents` 의 `(user_id, term_id, version, source='kakao_sync')` 가 비어 있고 마지막 카카오 로그인이 N 분 (예: 5분) 이상 지난 user 를 야간 reconcile 잡으로 스캔, 카카오 user-info 를 재호출하여 사후 insert. 본 잡 owner 는 Backend/Auth 트랙.
- 웹 콜백이 5xx 로 실패하면 사용자에게 toast 노출 ("동의 기록을 다시 시도 중입니다") 후 다음 로그인 진입 시 backend 가 재확인.

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

const DEFAULT_NEXT = process.env.NEXT_PUBLIC_FRONTEND_AUTH_SUCCESS_URL ?? '/auth/success';
const FAILURE_URL  = process.env.NEXT_PUBLIC_FRONTEND_AUTH_FAILURE_URL ?? '/auth/failure';

export async function GET(request: NextRequest) {
  const url = request.nextUrl;
  const code = url.searchParams.get('code');
  const next = url.searchParams.get('next') ?? DEFAULT_NEXT;
  const errorCode = url.searchParams.get('error');

  // Supabase 콘솔 redirect allow list 에 등록된 path 와 동일해야 함.
  const safeNext = isSafeNext(next) ? next : DEFAULT_NEXT;

  if (errorCode) {
    const failure = url.clone();
    failure.pathname = FAILURE_URL;
    failure.searchParams.set('reason', errorCode);
    return NextResponse.redirect(failure);
  }

  if (!code) {
    const failure = url.clone();
    failure.pathname = FAILURE_URL;
    failure.searchParams.set('reason', 'missing_code');
    return NextResponse.redirect(failure);
  }

  const supabase = createServerClient();
  const { data, error } = await supabase.auth.exchangeCodeForSession(code);
  if (error || !data?.session) {
    const failure = url.clone();
    failure.pathname = FAILURE_URL;
    failure.searchParams.set('reason', error?.code ?? 'exchange_failed');
    return NextResponse.redirect(failure);
  }

  // Kakao 동의 audit (§4.5.2 경로 (a)).
  const provider = data.session.user.app_metadata?.provider;
  if (provider === 'kakao' || provider === 'custom:kakao') {
    await persistKakaoSyncConsent(data.session).catch((e) =>
      console.warn('[auth/callback] kakao-sync persistence failed', e),
    );
  }

  return NextResponse.redirect(new URL(safeNext, request.url));
}
```

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
| (신규) `app/auth/callback/route.ts` | (없음) | OAuth provider redirect 의 1차 수신점. `exchangeCodeForSession` + `next` 안전 리다이렉트 + Kakao Sync audit 트리거 (§4.7). |
| (신규) `lib/supabase/providers.ts` | (없음) | UI provider id (`google\|kakao\|naver`) → Supabase provider id 매핑 SSOT (§4.2.3). |
| (신규) `lib/safe-redirect.ts` | (없음) | `isSafeNext(next)` — callback `next` allow list 검증 (§4.7.2). |
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

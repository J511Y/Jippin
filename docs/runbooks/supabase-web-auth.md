# Runbook — Next.js Supabase Auth 전환 설계 (CMP-577)

- 작성자: Frontend Lead (`60ef2b0f`)
- 작성일: 2026-05-29
- 상태: **Design (Draft)** — 본 문서는 설계 정본이다. 실제 Supabase 콘솔 세팅 / 라이브 로그인 검증은 후속 트랙이 별도로 수행한다.
- 관련 이슈: **CMP-577** (`[SUPABASE][WEB] Next.js Supabase Auth client/session adapter 전환 설계`)
- 의존 트랙: Backend/Auth Supabase JWT 검증 트랙 (별도 CMP-* 이슈 — `apps/api` 가 Supabase JWKS 또는 공유 비밀로 access token 을 검증하는 흐름이 합의되어야 본 설계가 닫힌다)
- 정본 종속: `docs/adr/0003-anon-user-and-sso.md` (익명 + OAuth 정책), `docs/brief/CEO_PROJECT_BRIEF.md`, `AGENTS.md §4.4` (시크릿 봉인)
- 비목표: 실제 Supabase project URL / `anon` key / `service_role` key / OAuth client secret 의 본 문서 기재. 본 문서는 **변수명과 보관 위치만** 명시한다.

---

## 0. TL;DR

| 항목 | 결정 |
|---|---|
| **세션 1차 소스** | Supabase Auth session (`supabase.auth.getSession()`). 자체 JWT / 자체 메모리 토큰 / 자체 `jippin_session` 쿠키 폐기. |
| **클라이언트 라이브러리** | `@supabase/supabase-js` + `@supabase/ssr` (Next.js 16 App Router · Edge proxy / Route Handler / Server Component cookie 통합). |
| **익명 흐름** | `supabase.auth.signInAnonymously()` — 페이지 첫 진입 시 세션이 없으면 1회 호출. `localStorage.jippin_anonymous_user_id` 와 `POST /auth/anonymous-users` 는 **폐기**. Supabase user `id` 가 익명/실명 user 의 단일 키. |
| **전환 시점 CTA** | 익명 세션 존재 시 `supabase.auth.linkIdentity({ provider })` 호출. 익명 세션이 아닌 비로그인 진입은 `supabase.auth.signInWithOAuth({ provider, options: { redirectTo } })`. 두 경로 모두 Supabase 가 hosted login page / provider redirect 를 owner 로 가진다. |
| **OAuth provider** | `google`, `kakao`, `naver` (ADR-0003 봉인). Supabase 콘솔에서 활성화. Naver / Kakao 는 Supabase 가 기본 제공하지 않을 수 있으므로 Generic OAuth 또는 Custom Provider 로 등록한다 (트랙 후속). |
| **FastAPI 호출** | `Authorization: Bearer <session.access_token>` 헤더 주입. 자체 refresh 인터셉터 폐기 — Supabase SDK 의 토큰 자동 갱신을 신뢰. |
| **Edge proxy 가드** | `proxy.ts` 는 `jippin_session` 쿠키 대신 `@supabase/ssr` 의 `createServerClient` 로 세션을 읽고, anonymous user 도 비보호 경로(`/app/pre-review`)에 들어올 수 있게 한다. |
| **클라이언트 SSOT** | `apps/web/lib/supabase/` 디렉터리 신설 — `browser.ts`, `server.ts`, `middleware.ts` 3분할. axios 인터셉터는 이 SSOT 가 발급한 token 만 읽도록 단방향 의존. |

---

## 1. 현 웹 인증 코드 인벤토리 (origin/dev `ad57caa1` 기준)

| 경로 | 책임 | 전환 후 처분 |
|---|---|---|
| `apps/web/proxy.ts` | `/app/consult`, `/app/leads`, `/app/reports` 진입 시 `jippin_session` 쿠키 존재 여부 가드. | **재작성.** Supabase 세션 기반으로 변경. matcher 와 prefix 정책은 유지. |
| `apps/web/lib/auth-token.ts` | 메모리 access token 저장 + listener. | **폐기.** Supabase SDK 가 세션을 관리. |
| `apps/web/lib/api-client.ts` | axios + `/auth/refresh` 401 인터셉터 + `Bearer <메모리 토큰>` 주입. | **재작성.** Supabase session 에서 token 을 읽어 주입. 401 refresh 큐 삭제 (SDK 가 처리). `withCredentials` 도 제거 가능 (쿠키 의존 종료). |
| `apps/web/lib/anonymous-user.ts` | `POST /auth/anonymous-users` 로 익명 ID 발급 + `localStorage.jippin_anonymous_user_id` 캐싱. | **폐기.** `signInAnonymously()` 의 user `id` 로 대체. localStorage 키도 제거. |
| `apps/web/lib/api-base-url.ts` | `NEXT_PUBLIC_API_BASE_URL` fallback. | **유지.** Supabase 와 무관. |
| `apps/web/lib/api/error.ts` | 백엔드 에러 정규화. | **유지.** `apiClient` 재작성 후에도 그대로 호출 가능. |
| `apps/web/app/(auth)/login/page.tsx` | "집핀 로그인" 소개 + provider 버튼 placeholder. | **부분 유지.** 카피만 갱신 (§5.2). 페이지 구조는 동일. |
| `apps/web/app/(auth)/login/login-buttons.tsx` | `GET /auth/{provider}/start?return_url=...&anonymous_user_id=...` 로 브라우저 redirect. | **재작성.** `signInWithOAuth` / `linkIdentity` 호출로 교체. anonymous_user_id 헤더 / 쿼리 폐기. |
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
└── session.ts       # SessionUser 타입 정의 + 익명/실명 구분 헬퍼
```

- 모든 외부 호출은 위 4개 파일 중 하나를 import 한다. `@supabase/supabase-js` / `@supabase/ssr` 직접 import 는 `lib/supabase/` 외에서 금지 (lint rule 후속 추가 권장).
- env reader 를 단일 모듈로 격리하는 이유: `NEXT_PUBLIC_*` 누락 시 SSR / 클라이언트 모두에서 동일한 명시적 에러를 던지도록 한다. fallback 금지 (라이브 URL/key 가 미설정이면 fail loud).

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
| `NEXT_PUBLIC_FRONTEND_AUTH_SUCCESS_URL` | 기존 유지 | `signInWithOAuth({ options: { redirectTo } })` 에 사용 가능. | ADR-0003 정합. |
| `NEXT_PUBLIC_FRONTEND_AUTH_FAILURE_URL` | 기존 유지 | OAuth 실패 시 redirect 표시 경로. | 정본은 `apps/api/.env.example`. |
| `AUTH_COOKIE_NAME` | **폐기 후보** | 기존 `jippin_session` 가드용. Supabase 가 자체 쿠키 (`sb-<project-ref>-auth-token`) 를 발급하므로 web 쿠키 이름은 더 이상 의미가 없다. | proxy.ts 재작성 후 env 라인 제거. |

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

### 4.2 로그인 / 전환 CTA — `linkIdentity` 와 `signInWithOAuth` 분기

ADR-0003 §2.2 의 "비회원 사전검토 → 전환 시점 OAuth" 정책을 유지하기 위한 분기:

```
[CTA 클릭]
   │
   ├─ supabase.auth.getUser() → user.is_anonymous === true
   │      → supabase.auth.linkIdentity({
   │          provider,
   │          options: { redirectTo: <FRONTEND_AUTH_SUCCESS_URL absolute> }
   │        })
   │      ⇒ Supabase 가 provider 페이지로 redirect. 콜백 후 동일 user id 유지, identities 가 추가됨.
   │
   └─ user 없음 / 이미 실명 user
          → supabase.auth.signInWithOAuth({
              provider,
              options: { redirectTo: <FRONTEND_AUTH_SUCCESS_URL absolute> }
            })
          ⇒ 신규 user 생성 또는 기존 로그인.
```

- **`linkIdentity` 호출 권한.** Supabase 대시보드에서 `Auth → Identity Linking` 기능을 활성화해야 한다 (콘솔 세팅 트랙).
- **자동 병합 금지 (ADR-0003 §2.3) 와의 정합.** Supabase 의 기본 동작은 동일 이메일에 대해 provider identities 를 같은 user 에 자동 link 한다. 우리는 이를 끄거나 (대시보드 `Email Confirmations / Account Linking` 설정), 또는 backend 에서 webhook 으로 거부해야 한다. 본 트랙은 web 측 설계만 봉인하고, Supabase 콘솔 정책 봉인은 후속 트랙에 위임한다. **자동 병합이 켜진 상태로 라이브가 가면 ADR-0003 §2.3 위반**이므로, Supabase 콘솔 세팅 시점에 이 항목을 반드시 검증한다.
- **provider 화이트리스트.** UI 가 노출하는 provider 는 `kakao | naver | google` 로 고정 (ADR-0003 봉인). `signInWithOAuth({ provider: 'kakao' })` 등으로 호출. Kakao / Naver 가 Supabase 의 native provider 가 아니면 **Custom Provider (OIDC / OAuth2) 등록 + provider id 매핑** 이 필요하며, 이 작업도 콘솔 세팅 트랙 책임.

### 4.3 FastAPI 호출 adapter

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

**옵션: 401 fallback.** 백엔드가 token 검증 실패로 401 을 돌려주는 경우, SDK 의 자동 갱신과 무관한 영구 만료 / 키 회전 / revoke 시나리오가 있다. 그 시 한 번만 `supabase.auth.refreshSession()` 을 호출하고 재시도. 재시도까지 실패하면 client 상태를 logout 으로 전환하고 호출부에 propagate.

### 4.4 약관 동의 / 추가 user metadata

ADR-0003 §2.2 의 `terms_consents` 흐름은 그대로 유지. 변경 포인트:

- 약관 동의 화면 진입 트리거 — 더 이상 `GET /auth/me` 의 `missing_required_terms` 가 아닌, **백엔드가 `Authorization: Bearer <supabase_jwt>` 호출에 대해 `/users/me` (or 동등 엔드포인트) 응답에 포함시키는 동일 필드** 를 신뢰한다. 응답 구조는 그대로 둘 수 있으므로 web 측 컴포넌트는 백엔드의 새 path 만 가져다 호출.
- 약관 동의 제출은 `POST /auth/terms/accept` 그대로 (이름은 Backend 트랙이 변경 가능). Supabase user `id` 를 backend 가 token 에서 추출.

### 4.5 로그아웃

- `supabase.auth.signOut()` — 모든 storage / cookie 정리.
- 백엔드 `POST /auth/logout` 호출은 불필요 (자체 refresh token 폐기 대상이 없음). 백엔드 측에 audit log 트리거가 필요하다면 별도 `POST /events/logout` 같은 명시 라우트로 분리하되, 본 트랙의 권고는 "백엔드 logout 호출 제거".
- signOut 후 `/login` 으로 redirect.

### 4.6 Edge proxy (`apps/web/proxy.ts`) 변경

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
| `login-buttons.tsx` | `GET /auth/{provider}/start?return_url=...&anonymous_user_id=...` 호출 | `linkIdentity` / `signInWithOAuth` 분기 (§4.2). |
| `login-buttons.tsx` | `getOrCreateAnonymousUserId()` import | Supabase session 의 user id 가 단일 키. import 제거. |
| `/auth/test` | "비회원 ID" 섹션의 `localStorage.jippin_anonymous_user_id` 표기 | Supabase user `id` + `is_anonymous` 플래그로 교체. |
| `/auth/test` | `/auth/me` raw fetch | `supabase.auth.getUser()` 결과 + 백엔드 `/users/me` 응답 split 으로 교체. |
| `/auth/test` | `POST /auth/logout` 호출 | `supabase.auth.signOut()` 로 교체. |
| `/auth/test` | "provider link" 섹션의 `POST /auth/sso-accounts/{provider}/link?mode=json` | `supabase.auth.linkIdentity({ provider })` 로 교체. |
| `proxy.ts` | `jippin_session` 쿠키 가드 | Supabase session + `is_anonymous` 가드 (§4.6). |
| `lib/auth-token.ts` | 파일 전체 | 삭제. |
| `lib/anonymous-user.ts` | 파일 전체 | 삭제. |
| `lib/api-client.ts` | 401 refresh 큐 / `withCredentials` | 재작성 (§4.3). |
| `README.md` (apps/web) | "## 인증 전략 (CMP-529 선택)" 섹션 | "## 인증 전략 (CMP-577 — Supabase Auth)" 로 교체. NextAuth v5 언급 제거. |
| `.env.example` | `AUTH_COOKIE_NAME` 주석 | 폐기 표기. |

### 5.3 비목표 (이번 트랙에서 손대지 않음)

- 디자인 SSOT (`docs/brand/...`) 의 색상 / 타이포그래피.
- `/auth/success` · `/auth/failure` 페이지 자체 카피 — 라우팅 흐름만 검증되면 다음 디자인 트랙에서 다듬는다.
- 실제 Supabase 콘솔 세팅 / Custom Provider 등록 / redirect URL 화이트리스트.
- API 측 `/auth/*` 라우트 정리. 웹이 호출하지 않게 되는 시점부터의 cleanup 일정은 Backend/Auth 트랙 합의 후 별도 이슈로 끊는다.

---

## 6. 트랙 간 의존 / 연결점

| 의존 | 무엇 | 본 트랙이 가정하는 것 |
|---|---|---|
| **Backend/Auth — Supabase JWT 검증** | `apps/api` 가 `Authorization: Bearer <supabase access_token>` 헤더에서 JWT 를 검증 (JWKS endpoint or HS256 shared secret) 하고 `user.id` 를 신뢰 user 컨텍스트로 사용한다. | `users.id` 가 Supabase user `id` 와 동일하거나, 매핑 테이블로 1:1 매핑. ADR-0003 의 `external_sso_accounts` 가 Supabase `auth.users` 와 어떻게 정렬되는지는 Backend/Auth 트랙이 결정. |
| **Supabase 콘솔 세팅** | Project 생성, OAuth provider 등록 (Google native + Kakao/Naver Custom OAuth), redirect URL 화이트리스트 (`/auth/callback`, `https://*.vercel.app` 등), Email/Phone provider OFF, Anonymous sign-in ON, Identity Linking 정책 = "수동". | 본 트랙은 콘솔 작업을 수행하지 않는다. 변수명·기능 flag 만 봉인. |
| **ADR-0003 자동 병합 금지** | Supabase 의 동일 이메일 자동 link 가 꺼져 있어야 함. | 콘솔 세팅 트랙에서 검증. 켜진 상태로 라이브 가면 ADR-0003 §2.3 위반. |
| **약관 동의 흐름** | `terms_consents` 데이터는 백엔드가 owner. Supabase user metadata 에는 약관 동의를 저장하지 않는다. | `POST /auth/terms/accept` 라우트 자체는 유지되지만 호출자가 보내는 token 이 자체 JWT → Supabase access token 으로 바뀐다. |

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
| Identity Linking 정책 | Supabase 콘솔 → Auth → Settings → Account Linking = `manual` | ADR-0003 §2.3 정합. |

값이 모이지 않은 동안 본 이슈는 설계 산출물(본 문서 + env 변수 + UI 변경 계획) 완료로 종결한다. 라이브 검증은 별도 자식 이슈 (`[SUPABASE][WEB] live wiring + smoke`) 로 분리한다.

---

## 9. 변경 절차

- 본 runbook 의 흐름·환경변수·SSOT 디렉터리 구조는 본 PR 머지 시점부터 봉인된다. 변경 시 새 PR + 본 문서 갱신을 같은 커밋에 포함.
- ADR-0003 의 결정 (provider 3종, 자동 병합 금지, 약관 source 분리) 은 본 runbook 보다 상위. 충돌 시 ADR-0003 가 우선.
- Supabase SDK major 버전 변경 (`@supabase/supabase-js` v3 등) 은 새 runbook 절 / ADR 로 처리.

— 끝 —

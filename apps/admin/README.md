# @jippin/admin — 집핀 관리자 사이트

Next.js 16(App Router) 단독 앱. 별도 백엔드 없이 main Supabase 프로젝트를 직접 사용한다.

## 인증/인가

- 로그인: Supabase 이메일/비밀번호 (`/auth/login` Route Handler, sb-\* 쿠키).
- 인가 게이트 SSOT: `lib/auth.ts` 의 `isAdminUser` — **`app_metadata.role === 'admin'`** 클레임만 신뢰한다.
  - main 프로젝트는 일반 사용자 이메일 가입이 열려 있으므로 "로그인 성공 = 관리자"가 아니다.
  - `app_metadata` 는 service_role 로만 수정 가능 → 클라이언트 위조 불가. (`user_metadata` 는 게이트 금지.)
- `proxy.ts` 가 `/login` 제외 전 경로를 deny-by-default 로 차단하고, 페이지/핸들러에서 `requireAdminUser` 로 이중 방어한다.
- 관리자 계정 시드: `tools/admin/create-admin-users.mjs` (service_role 키로 운영자가 로컬 일회 실행, 재실행 안전).

## 로컬 개발

```bash
cd apps/admin
cp .env.example .env.local   # anon key 는 Supabase 대시보드에서 주입
corepack pnpm@9 install
corepack pnpm@9 dev          # http://localhost:3100
```

- 글로벌 pnpm v11 과 무관하게 `corepack pnpm@9` 로 호출한다 (engines.pnpm <10).
- 검색엔진 차단: `X-Robots-Tag: noindex, nofollow` 헤더 + metadata robots — 절대 해제하지 않는다.
- `SUPABASE_SERVICE_ROLE_KEY` 는 서버 전용. 데이터 접근 Route Handler 를 추가할 때만 주입한다.

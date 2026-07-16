# @jippin/admin — 집핀 관리자 사이트

Next.js 16(App Router) 단독 앱. 별도 백엔드 없이 main Supabase 프로젝트를 직접 사용한다. (예외: 담당자 알림톡 발송만 FastAPI 백엔드에 위임 — 아래 환경변수 참조)

## 콘솔 구성

사이드바 내비게이션 정본은 `components/console/sidebar-nav.tsx`.

| 구역 | 라우트 | 내용 |
|---|---|---|
| 개요 → 대시보드 | `/` | 상담 추이·세션 퍼널 차트 (`components/dashboard/`) |
| 운영 → 상담 | `/leads`, `/leads/[id]` | 상담 리드 목록/상세 — 필터·담당자 배정·코멘트·상태 변경. 담당자 배정 시 알림톡은 FastAPI `POST /leads/{id}/assignee-notification` 위임 |
| 운영 → 회원 | `/users` | 회원 검색 (`components/users/user-search.tsx`) |
| 사전검토 → 세션 | `/sessions`, `/sessions/[id]` | 사전검토 세션 목록/상세 + 상태 필터 |
| 사전검토 → 업로드 도면 | `/floorplans` | 업로드 도면 조회 |
| 셀프 서비스 | 프로필/비밀번호 다이얼로그, `/auth/logout` | `app/(console)/profile-actions.ts` |

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
corepack pnpm@9 dev          # http://localhost:4000
```

- 글로벌 pnpm v11 과 무관하게 `corepack pnpm@9` 로 호출한다 (engines.pnpm <10).
- 검색엔진 차단: `X-Robots-Tag: noindex, nofollow` 헤더 + metadata robots — 절대 해제하지 않는다.
- `SUPABASE_SERVICE_ROLE_KEY` 는 서버 전용. 데이터 접근 Route Handler 를 추가할 때만 주입한다.
- `API_BASE_URL` (기본 `https://api.jippin.ai`) — 담당자 알림톡 발송을 FastAPI 백엔드에 위임할 때 사용 (`lib/api-base-url.ts`). 이외 데이터 접근은 전부 Supabase 직접.

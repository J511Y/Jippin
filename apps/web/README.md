# apps/web — 집핀 프론트엔드 (Next.js 16.2 LTS)

Next.js 16.2 LTS · React 19 · Node 22 LTS · pnpm 9 으로 구성된 집핀의 Presentation tier 입니다.
본 디렉터리는 ADR-0001 §2 (`docs/adr/0001-stack-reevaluation.md`) 와 CMP-529 자식 이슈가 봉인합니다.

## 개발 명령

```bash
nvm use         # .nvmrc -> 22
pnpm install
cp .env.example .env.local

pnpm dev        # http://localhost:3000
pnpm storybook  # http://127.0.0.1:6006
pnpm typecheck
pnpm lint
pnpm build
pnpm build-storybook
pnpm start
```

## 헬스체크

- `GET http://localhost:3000/healthz` -> `{ "status": "ok", "service": "jippin-web", ... }`

## 디렉터리

```
apps/web/
├── .storybook/                # Storybook 설정
├── app/
│   ├── (app)/                 # CMP-618: 모바일 IA shell (MobileShell + 하단 탭)
│   │   ├── layout.tsx
│   │   ├── page.tsx           # / (랜딩)
│   │   ├── sessions/          # /sessions, /sessions/new, /sessions/[sessionId], …/report
│   │   ├── leads/             # /leads, /leads/new
│   │   ├── contacts/          # /contacts, /contacts/[contactId]
│   │   ├── prices/
│   │   ├── terms/
│   │   └── privacy/
│   ├── api/healthz/route.ts   # Next.js BFF 헬스 핸들러
│   ├── auth/                  # /auth/callback 등 Supabase OAuth 라우트 (모바일 shell 밖)
│   ├── layout.tsx             # 루트 레이아웃 + LegalNotice 강제 노출 (AGENTS.md §4.6)
│   └── globals.css
├── components/
│   ├── LegalNotice.tsx
│   ├── MobileShell.tsx        # CMP-618: 모바일 퍼스트 shell + 하단 탭
│   ├── a2ui/                  # 채팅·동적 컴포넌트 placeholder (SDD §6.2 CHAT)
│   └── ui/                    # Mantine 기본 컴포넌트 re-export + Storybook 예시
├── lib/
│   ├── api-client.ts          # axios + 401 refresh 인터셉터
│   ├── auth-token.ts
│   ├── mantine-theme.ts       # docs/design 토큰 -> Mantine theme/CSS variables
│   ├── providers.tsx
│   └── query-client.ts
├── next.config.mjs
├── tsconfig.json
├── tailwind.config.ts
├── postcss.config.mjs
├── Dockerfile                 # Node 22 alpine multi-stage
└── package.json
```

## 정보구조 (IA) / 라우트

CMP-618 이후 모바일 퍼스트 IA 가 `app/(app)` route group 으로 봉인되어 있습니다. 하단 탭은 홈 / 검토 / 상담 / 가격 네 칸이며, `/leads/new` 는 탭에 직접 들어가지 않고 CTA 로만 진입합니다. `/auth/*` 는 shell 바깥 (root layout) 에 위치해 OAuth 콜백/익명 가입 흐름과 충돌하지 않습니다.

| Route | 역할 | 하단 탭 |
|---|---|---|
| `/` | 랜딩. 서비스 이해 + 사전검토 시작 CTA. | 홈 |
| `/sessions` | 사전검토 세션 목록 + 새 세션 진입. | 검토 |
| `/sessions/new` | 주소/도면 입력 시작. | 검토 |
| `/sessions/:sessionId` | 사전검토 진행 화면. | 검토 |
| `/sessions/:sessionId/report` | AI 판단 결과 + inline `LegalNotice` + 상담 전환 CTA. | 검토 |
| `/leads` | 사전검토 없이 상담 신청 진입. | 상담 |
| `/leads/new` | 상담 신청 폼 (탭에는 노출하지 않음). | — |
| `/contacts` | 신청한 상담의 진행 상태 목록. | 상담 |
| `/contacts/:contactId` | 상담 상세 (진행 단계, 메모, 첨부). | 상담 |
| `/prices` | 가격/상품 소개. | 가격 |
| `/terms`, `/privacy` | 약관 / 개인정보처리방침 placeholder. | — |
| `/auth/callback` | Supabase OAuth callback. **모바일 shell 밖** — 변경 금지. | — |

세부 제품 판단:

- `/leads` 와 `/contacts` 는 분리됩니다. `/leads` 는 신규 상담 요청 생성, `/contacts` 는 생성된 상담의 진행 관리.
- `/sessions/:sessionId/report` 는 AI 사전검토 → 상담 전환의 중심이므로 항상 inline `LegalNotice` 를 노출합니다. (AGENTS.md §4.6 정본 문구)
- 모든 모바일 shell 화면은 `(app)/layout.tsx` 가 `MobileShell` 로 감쌉니다. shell 은 하단 탭 높이 + `env(safe-area-inset-bottom)` 만큼 본문/footer 를 밀어내므로 root 의 `LegalNotice` 가 탭 위로 노출됩니다.
- 실제 세션/리드/상담 API 와 Supabase Auth 정책 변경은 후속 이슈에서 수행됩니다 — 현재는 mock 데이터와 disabled 컨트롤만 있는 placeholder 입니다.

## 인증 전략 (Supabase Auth SSOT)

CMP-603/CMP-604 이후 웹 인증의 정본은 **Supabase Auth** 입니다. 기존 `localStorage.jippin_anonymous_user_id` + `/auth/anonymous-users` dual-write 경로는 제거되었고, 남은 route/helper 는 accidental call 을 410/throw 로 실패시킵니다.

- 설계 정본: [`docs/runbooks/supabase-web-auth.md`](../../docs/runbooks/supabase-web-auth.md).
- 클라이언트: `@supabase/supabase-js` + `@supabase/ssr` 도입 (Next.js 16 App Router · Edge proxy / Route Handler / Server Component cookie 통합).
- 비회원 흐름: `supabase.auth.signInAnonymously()` 로 익명 세션 발급. 도면/리포트 ownership 은 Supabase `auth.users.id` 를 사용한다.
- 전환 시점: 익명 user 는 `supabase.auth.linkIdentity({ provider })`, 신규 로그인은 `supabase.auth.signInWithOAuth({ provider })`. `linkIdentity` 실패 시 "익명 데이터 이전" 모달 ladder 로 fallback (runbook §4.2.2). provider 화이트리스트는 `google | kakao | naver` (ADR-0003 봉인). SDK 에 넘기는 식별자는 `lib/supabase/providers.ts` 매핑을 거치며 Naver 는 `custom:naver`.
- **MVP linking 정책 (CMP-572 CEO 결정)** — Manual identity linking only. 동일 verified email 자동 link 는 Supabase 콘솔에서 OFF 봉인. 이미 다른 user 에 연결된 provider identity 의 익명 세션 연결 시도는 §4.2.2 fallback ladder (기존 계정 로그인 + 데이터 이관 분기) 로만 처리하며 자동 병합 금지. 상세는 runbook §0.0.
- OAuth callback: `/auth/callback?next=<원래 목적지>` Route Handler 가 `exchangeCodeForSession` 으로 세션 쿠키를 저장한 뒤 `next` 로 302. Supabase 콘솔 redirect allow list 도 `/auth/callback` 기준 (runbook §4.7).
- Kakao Sync 동의 audit: callback Route Handler 가 `POST /auth/terms/kakao-sync` 를 호출 → 백엔드가 `terms_consents(source='kakao_sync')` 단일 트랜잭션 insert (runbook §4.5.2).
- FastAPI 호출: `Authorization: Bearer <session.access_token>` 헤더를 사용한다. `x-jippin-anon-id` legacy header 는 더 이상 전송하지 않는다.
- API anonymous gating: conversion-only 라우트 (상담 / 리드 / 리포트) 는 403 `AUTH_ANONYMOUS_NOT_ALLOWED` 로 익명 token 을 거부한다 — 계약은 runbook §4.4.

env 추가 변수는 `apps/web/.env.example` 의 `NEXT_PUBLIC_SUPABASE_*` 두 라인을 참조하십시오. 실제 값은 `.env.local` 또는 운영 시크릿 매니저에만 보관합니다.

## A2UI

`components/a2ui/` 는 LLM 응답에 첨부되는 동적 컴포넌트의 렌더 골격입니다.

- `MessageList` / `MessageInput` — 기본 채팅 UI
- `DynamicComponent` — `{ kind, payload }` 스펙을 받아 클라이언트 레지스트리에서 매칭

정본 스키마는 `packages/contracts` (CMP-528) 와 후속 CHAT 이슈에서 확정합니다.

## Storybook / 컴포넌트 운영 규칙

Storybook은 `apps/web` 의 디자인 시스템과 기본 컴포넌트를 에이전트와 사람이 같은 방식으로 확인하는 표면입니다.

- 기본 UI 베이스는 Mantine입니다. 새 화면은 `@mantine/core`, `@mantine/form`, `@mantine/modals`, `@mantine/notifications`, `@mantine/dates` 를 우선 사용합니다.
- `components/ui/index.ts` 는 에이전트 편의를 위한 Mantine re-export 표면입니다. 별도 래퍼 컴포넌트는 실제 중복·정책 캡슐화가 필요할 때만 추가합니다.
- 집핀 토큰은 `lib/mantine-theme.ts` 에서 Mantine theme/CSS variables로 노출합니다. 색·폰트·법적 고지 문구 변경은 `docs/design/DESIGN.md` 하위 정본과 함께 갱신합니다.
- 컴포넌트에 variant, 상태, 접근성 동작, 문구가 추가되면 같은 PR에서 `*.stories.tsx` 를 함께 갱신합니다.
- 디자인 토큰과 사용 규칙은 `Design System/Overview`, `Design System/Colors`, `Design System/Typography`, `Design System/Component Tokens` 를 먼저 확인합니다.
- 에이전트는 새 화면을 만들기 전에 Storybook의 `UI/Button`, `UI/Badge`, `UI/Alert`, `UI/Card`, `UI/Inputs`, `UI/Overlay`, `UI/Feedback`, `UI/Form`, `UI/ResultSummary`, `UI/LegalNotice` 를 먼저 확인합니다.
- Mantine 전체 컴포넌트 사용 후보는 `Mantine Catalog/*` 를 먼저 확인합니다. Catalog 는 `Actions`, `Forms`, `Mobile Overlays`, `Feedback`, `Navigation`, `Workflow Progress`, `Data Display` 로 나뉘며, 집핀에서 승인한 조합과 문구 규칙을 함께 보여줍니다.
- 모바일 first 화면은 `Mantine Catalog/Mobile Overlays` 의 `Bottom Sheet` / `Full Screen Dialog` story에서 먼저 확인합니다. Drawer 는 하단 bottom sheet 를 기본으로 검토하고, 짧은 확인·다운로드만 full-screen Modal 을 사용합니다.
- 확인 명령은 `pnpm storybook`, component test 는 `pnpm test:storybook`, 정적 빌드 검증은 `pnpm build-storybook` 입니다.

## 컨테이너

```bash
docker build -t jippin/web -f apps/web/Dockerfile apps/web
docker run --rm -p 3000:3000 -e NEXT_PUBLIC_API_BASE_URL=http://host.docker.internal:8000 jippin/web
```

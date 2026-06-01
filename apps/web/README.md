# apps/web — 집핀 프론트엔드 (Next.js 16.2 LTS)

Next.js 16.2 LTS · React 19 · Node 22 LTS · pnpm 9 으로 구성된 집핀의 Presentation tier 입니다.
본 디렉터리는 ADR-0001 §2 (`docs/adr/0001-stack-reevaluation.md`) 와 CMP-529 자식 이슈가 봉인합니다.

## 개발 명령

```bash
nvm use         # .nvmrc -> 22
pnpm install
cp .env.example .env.local

pnpm dev        # http://localhost:3000
pnpm typecheck
pnpm lint
pnpm build
pnpm start
```

## 헬스체크

- `GET http://localhost:3000/healthz` -> `{ "status": "ok", "service": "jippin-web", ... }`

## 디렉터리

```
apps/web/
├── app/
│   ├── api/healthz/route.ts   # Next.js BFF 헬스 핸들러
│   ├── layout.tsx             # 루트 레이아웃 + LegalNotice 강제 노출 (AGENTS.md §4.6)
│   ├── page.tsx
│   └── globals.css
├── components/
│   ├── LegalNotice.tsx
│   └── a2ui/                  # 채팅·동적 컴포넌트 placeholder (SDD §6.2 CHAT)
├── lib/
│   ├── api-client.ts          # axios + 401 refresh 인터셉터
│   ├── auth-token.ts
│   ├── providers.tsx
│   └── query-client.ts
├── next.config.mjs
├── tsconfig.json
├── tailwind.config.ts
├── postcss.config.mjs
├── Dockerfile                 # Node 22 alpine multi-stage
└── package.json
```

## 인증 전략 (CMP-577 — Supabase Auth 전환 중, Phase 1 dual-write)

본 골격은 CMP-529 시점에 자체 발급 JWT + HttpOnly 리프레시 쿠키 경로로 시작되었으나, CMP-577 부터 **Supabase Auth 를 세션 1차 소스로 채택**합니다. 다만 ADR-0003 §2 의 익명 식별자 / 발급 라우트 정본을 supersede 하는 ADR-0004 가 아직 Accepted 되지 않았으므로, 본 트랙은 **Phase 1 dual-write** 로 진입하고 ADR-0003 호환 흐름과 Supabase 흐름을 병행 유지합니다. Phase 2 (legacy 폐기) 는 ADR-0004 Accepted 이후 별도 PR 에서 한 번에 처리합니다.

- 설계 정본: [`docs/runbooks/supabase-web-auth.md`](../../docs/runbooks/supabase-web-auth.md) (CMP-577) — Phase 표는 §9.
- 클라이언트: `@supabase/supabase-js` + `@supabase/ssr` 도입 (Next.js 16 App Router · Edge proxy / Route Handler / Server Component cookie 통합).
- 비회원 흐름: `supabase.auth.signInAnonymously()` 로 익명 세션 발급. **Phase 1 동안 `localStorage.jippin_anonymous_user_id` + `POST /auth/anonymous-users` 호출도 그대로 유지** (도면/리포트 claim 경로 보존). Phase 2 에서 일괄 폐기.
- 전환 시점: 익명 user 는 `supabase.auth.linkIdentity({ provider })`, 신규 로그인은 `supabase.auth.signInWithOAuth({ provider })`. `linkIdentity` 실패 시 "익명 데이터 이전" 모달 ladder 로 fallback (runbook §4.2.2). provider 화이트리스트는 `google | kakao | naver` (ADR-0003 봉인). SDK 에 넘기는 식별자는 `lib/supabase/providers.ts` 매핑을 거치며 Naver 는 `custom:naver`.
- OAuth callback: `/auth/callback?next=<원래 목적지>` Route Handler 가 `exchangeCodeForSession` 으로 세션 쿠키를 저장한 뒤 `next` 로 302. Supabase 콘솔 redirect allow list 도 `/auth/callback` 기준 (runbook §4.7).
- Kakao Sync 동의 audit: callback Route Handler 가 `POST /auth/terms/kakao-sync` 를 호출 → 백엔드가 `terms_consents(source='kakao_sync')` 단일 트랜잭션 insert (runbook §4.5.2).
- FastAPI 호출: `Authorization: Bearer <session.access_token>` 헤더 + Phase 1 동안 `x-jippin-anon-id: <legacy uuid>` 동시 전송. 자체 refresh 인터셉터 폐기 (SDK 자동 갱신 신뢰).
- API anonymous gating: conversion-only 라우트 (상담 / 리드 / 리포트) 는 403 `AUTH_ANONYMOUS_NOT_ALLOWED` 로 익명 token 을 거부한다 — 계약은 runbook §4.4.

env 추가 변수는 `apps/web/.env.example` 의 `NEXT_PUBLIC_SUPABASE_*` 두 라인을 참조하십시오. 실제 값은 `.env.local` 또는 운영 시크릿 매니저에만 보관합니다.

## A2UI

`components/a2ui/` 는 LLM 응답에 첨부되는 동적 컴포넌트의 렌더 골격입니다.

- `MessageList` / `MessageInput` — 기본 채팅 UI
- `DynamicComponent` — `{ kind, payload }` 스펙을 받아 클라이언트 레지스트리에서 매칭

정본 스키마는 `packages/contracts` (CMP-528) 와 후속 CHAT 이슈에서 확정합니다.

## 컨테이너

```bash
docker build -t jippin/web -f apps/web/Dockerfile apps/web
docker run --rm -p 3000:3000 -e NEXT_PUBLIC_API_BASE_URL=http://host.docker.internal:8000 jippin/web
```

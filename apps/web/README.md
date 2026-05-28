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

## 인증 전략 (CMP-529 선택)

본 골격은 자체 발급 JWT + HttpOnly 리프레시 쿠키 경로를 채택합니다.

- 액세스 토큰은 `lib/auth-token.ts` 메모리 저장소에 보관되며 `apiClient` 가 자동 주입합니다.
- 리프레시는 HttpOnly Secure 쿠키로 백엔드에서 발급되어, `/auth/refresh` 호출 시 자동 전달됩니다.
- 401 응답 시 단일 refresh 큐로 직렬화하여 동시 갱신 폭주를 방지합니다.

NextAuth v5 도입 여부는 후속 [Frontend] 이슈에서 재검토합니다
(교체 시 `lib/auth-token.ts` / `lib/api-client.ts` 만 갈아끼울 수 있도록 책임을 격리해 두었습니다).

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

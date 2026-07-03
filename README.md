# 집핀 (Jippin)

> **공동주택 비내력벽 철거(발코니 확장 등) 행위허가의 사전검토를 AI 로 자동화하는 B2C 무료 웹앱.**
> 비전문 사용자가 주소·도면만으로 철거 가능 여부·필요 방화시설·법령 근거를 한 번의 채팅 세션 안에서 확인하고, 상담·행위허가 의뢰로 자연스럽게 전환되도록 만든다.

> ⚠️ **법적 효력 없음 — 본 서비스는 AI 기반 사전 검토 시스템입니다. 최종 행위허가 여부는 관할 행정기관 판단에 따라 달라질 수 있습니다.** (요구사항 §2 NFR-LEGAL-001 / 기능 §FR-REPORT-009)

---

## 1. 프로젝트 상태

현재 단계: **MVP 구현 진행 중**. 웹(`apps/web`)·API(`apps/api`)·공통 컨트랙트(`packages/contracts`)·인프라(`infra/`, `supabase/`)가 구현되어 있고, 인증(Supabase Auth)·상담 리드·자주묻는질문 등은 DB-backed 실 기능이다. 통합 브랜치는 `dev`, 배포 토폴로지는 ADR-0006(분리형) 기준으로 진행한다. 모듈별 로컬 개발·테스트 명령은 각 앱 README 가 정본이다.

- 요구·기능·기술·SDD 정본: [`docs/명세서/`](docs/명세서/) (Word/Excel)
- 정본 텍스트 캐시(Office 미설치 환경용): [`docs/_extracted/`](docs/_extracted/)
- 본 이슈 범위·인도물·금지사항: [`docs/brief/CEO_PROJECT_BRIEF.md`](docs/brief/CEO_PROJECT_BRIEF.md)
- 에이전트 · 사람 공통 작업 가이드: [`AGENTS.md`](AGENTS.md)
- 디자인·브랜드 정본 (UI/문구/리포트 작업 전 통독): [`docs/design/DESIGN.md`](docs/design/DESIGN.md) — 진입점. 하위 정본 [`BRAND.md`](docs/design/BRAND.md) · [`COLOR_SYSTEM.md`](docs/design/COLOR_SYSTEM.md) · [`TYPOGRAPHY.md`](docs/design/TYPOGRAPHY.md).

### 1.1 브랜드 방향 요약

집핀의 시각 정체성은 **Urban Teal (`#147A73`) 을 기본**으로, **Blueprint Navy (`#153B5C`) 를 리포트·도면 분석·관리자 전문 영역의 보조 축**으로 사용한다. 가능/불가/보류 상태색은 브랜드 컬러와 분리된 별도 기능 토큰(`status.*`) 으로 운용한다. 자세한 토큰·접근성 기준·문체 규칙은 디자인 SSOT 4종 참조.

---

## 2. 모노레포 구조 (현행)

```
jippin/
├── apps/
│   ├── web/                 # Presentation 레이어 (Next.js 16.2 LTS · React 19 · Node 22 · pnpm 9)
│   └── api/                 # Application 레이어 (FastAPI 0.115 · Python 3.13 · uv)
├── packages/
│   └── contracts/           # CommonJudgmentSchema · CompletionDecision · RuleEvalResult · EstimateResult
│                            # (언어 중립 JSON 스키마 + 생성된 TS/Python 타입 — CMP-527)
├── supabase/
│   └── migrations/          # forward schema SSOT (*.sql) — Supabase GitHub Integration 이 적용
├── infra/
│   ├── docker/              # nginx.conf (앱 Dockerfile 은 각 apps/*/Dockerfile)
│   └── compose/             # docker-compose.yml + override.example (로컬 3-컨테이너)
├── docs/
│   ├── 명세서/              # 정본 4종 + 참고 이미지 (read-only)
│   ├── _extracted/          # 정본 텍스트 캐시 (tooling/extract_specs.py 산출물)
│   ├── brief/               # CEO 프로젝트 브리프
│   ├── adr/                 # CTO 아키텍처 결정 기록 (0001–0007)
│   ├── design/              # 디자인·브랜드 SSOT
│   └── runbooks/            # 운영 런북 (Supabase·Fly 배포 등)
├── tools/                   # secret-scan 등 운영 도구
└── tooling/                 # extract_specs.py · validate_commit_msg.py 등 보조 스크립트
```

---

## 3. 기술 스택 (현재 합의된 기준선)

| 영역 | 채택 | 비고 |
|---|---|---|
| 웹 프론트엔드 | **Next.js 16.2 LTS (App Router)** · React 19 · Node 22 · pnpm 9 | ADR-0001 봉인 — CMP-529 |
| 백엔드 API | **FastAPI 0.115** · Python 3.13 · uv | ADR-0001 봉인 — CMP-528 |
| 공통 컨트랙트 | TypeScript / Python 타입 자동 생성 | JSON 스키마 정본 — `packages/contracts/` (CMP-527) |
| DB · Auth | **Supabase Postgres + Supabase Auth** | `supabase/migrations/*.sql` 이 forward schema SSOT (ADR-0004) |
| 세션·캐시 | Redis 7.4 (로컬 compose / 운영 managed 도쿄) | ADR-0006 |
| 로컬 오케스트레이션 | **docker-compose 3-컨테이너** (web + api + redis) | DB 는 외부 Supabase 원격 |
| AI | Mask2Former + VLM (라인별 ADR) | 도면 인식·판별 — 후속 이슈에서 구현 |
| 배포 토폴로지 | **분리형 (제안 — ADR-0006)**: web=Vercel · api=Fly.io 도쿄 · redis=managed · DB=Supabase | ADR-0002(단일 VM) supersede |

---

## 4. 빠른 시작 (Getting Started)

### 4.1 사전 요구사항

- Docker 24+, Docker Compose v2
- Node.js 22 LTS (web 로컬 개발 시 — `apps/web/.nvmrc`), pnpm 9 (corepack)
- Python 3.13 (api 로컬 개발 시 — `apps/api/.python-version`), uv 0.5+
- Supabase project connection string (direct 5432 + pooler 6543)

### 4.2 환경 변수

```bash
cp .env.example .env       # 루트 .env.example 참조 (앱별: apps/api/.env.example · apps/web/.env.example)
# 최소 변수
# DATABASE_URL=postgresql://...supabase.co/postgres?sslmode=require       # direct 5432 (마이그레이션·롱 트랜잭션)
# DATABASE_POOL_URL=postgresql://...pooler.supabase.com/postgres?sslmode=require # pooler 6543 (일반 쿼리)
```

> 실제 자격 증명은 절대 커밋하지 않는다. 자세한 정책은 [`AGENTS.md §4.4`](AGENTS.md) 참조.

### 4.3 부팅

```bash
# 전체 부팅 (web + api + redis, Postgres 는 Supabase 원격)
make up                                   # = docker compose -f infra/compose/docker-compose.yml up --build

# 헬스 체크
curl http://localhost:3000/healthz       # web
curl http://localhost:8000/healthz       # api
```

자세한 모듈별 로컬 개발·테스트 명령은 각 앱의 `apps/*/README.md` 가 정본이다 (루트 공통 명령은 [`AGENTS.md §6`](AGENTS.md) · `Makefile`).

---

## 5. 개발 규칙 요약

전체 규칙은 [`AGENTS.md`](AGENTS.md) 가 정본이며, 본 README 는 한 줄 요약만 둔다.

- **브랜치 전략**: `main ← dev ← feature/*`. `main`/`dev` 직접 푸시 금지, 일반 작업 PR base 는 `dev`, `main` PR 은 `dev` 승격 또는 CTO/DevOps 승인 핫픽스만 허용.
- **커밋 메시지**: gitmoji (`✨ feat:`, `🐛 fix:`, `📝 docs:`, `♻️ refactor:`, `✅ test:`, `🔧 chore:`, `🚀 perf:`, `🔒 security:`, `🚧 wip:`, `🔖 release:`).
- **PR 본문**: 영향 모듈 명시. 관련 이슈가 있으면 식별자를 적어도 좋으나 `CMP-###` 표기는 더 이상 필수가 아니다(Paperclip 보드 운용 중단, pr-title-lint 미강제). 체크리스트는 [`AGENTS.md §4.3`](AGENTS.md).
- **에러·응답 포맷**: `{ "error": { "code", "message", "request_id", "timestamp" } }` 통일 (자세한 정의는 [`AGENTS.md §4.5`](AGENTS.md)).
- **법적 고지**: 모든 결과 화면·다운로드 산출물에 위 ⚠️ 문구 필수 — 누락 시 머지 거부.
- **디자인 SSOT 우선**: UI/문구/리포트 작업 전에 [`docs/design/DESIGN.md`](docs/design/DESIGN.md) 통독. 브랜드 색·상태 색·법적 고지 문구·폰트·문체를 코드에서 임의 변경 금지 (자세한 정책은 [`AGENTS.md §4.7`](AGENTS.md)).

### 5.1 UI 작업 전 사전 체크 (로컬 개발자)

`apps/web` 에서 UI 변경을 시작하기 전에 다음 디자인 정본을 확인한다.

- [ ] [`docs/design/DESIGN.md`](docs/design/DESIGN.md) — 디자인 원칙·인덱스
- [ ] [`docs/design/BRAND.md`](docs/design/BRAND.md) — 톤앤매너 / 금지 톤
- [ ] [`docs/design/COLOR_SYSTEM.md`](docs/design/COLOR_SYSTEM.md) — 토큰 표 / WCAG 기준
- [ ] [`docs/design/TYPOGRAPHY.md`](docs/design/TYPOGRAPHY.md) — 폰트 스택 / 문체 좋은 예/나쁜 예

---

## 6. 문서 지도

| 문서 | 무엇이 정본인지 | 누가 변경하는가 |
|---|---|---|
| [`docs/명세서/`](docs/명세서/) | 요구·기능·기술·SDD (외부 합의) | PM/이해관계자 |
| [`docs/_extracted/`](docs/_extracted/) | 위 정본의 텍스트 캐시 | `tooling/extract_specs.py` 산출물 |
| [`docs/brief/CEO_PROJECT_BRIEF.md`](docs/brief/CEO_PROJECT_BRIEF.md) | 본 이슈 범위·인도물·종결 조건 | CEO |
| [`AGENTS.md`](AGENTS.md) | 에이전트·사람 공통 작업 가이드 | CEO(§1·§3·§4 봉인), CTO·라인 리드(§2·§5·§6·§7) |
| [`docs/design/DESIGN.md`](docs/design/DESIGN.md) | 디자인 원칙·SSOT 진입점 | Frontend Lead |
| [`docs/design/BRAND.md`](docs/design/BRAND.md) | 브랜드 약속·톤앤매너·금지 톤 | Frontend Lead + CEO 봉인(§1·§5·§6) |
| [`docs/design/COLOR_SYSTEM.md`](docs/design/COLOR_SYSTEM.md) | 컬러 토큰·상태색·법적/오류 색·WCAG 기준 | Frontend Lead |
| [`docs/design/TYPOGRAPHY.md`](docs/design/TYPOGRAPHY.md) | 폰트 스택·타입스케일·문체 가이드 | Frontend Lead |
| [`docs/adr/`](docs/adr/) | 기술 채택 결정 기록 (0001–0007) | CTO·라인 리드 |
| 각 앱 `README.md` ([`apps/web`](apps/web/README.md) · [`apps/api`](apps/api/README.md)) | 모듈별 로컬 개발·테스트 명령 정본 | 해당 모듈 라인 리드 |

명세 4종 사이에 모순이 있으면 다음 우선순위를 따른다:
**(이슈 본문) > (CEO 브리프) > (SDD) > (기술명세서) > (기능명세서) > (요구사항)**.
모순 자체는 PR 또는 후속 이슈로 보고한다.

---

## 7. 이슈 트래커 · 자동화 에이전트

본 레포는 **Paperclip 보드**의 `CMP-###` 식별자를 기준으로 이슈를 관리한다. 자동화 에이전트(CEO / CTO / 라인 리드 / 엔지니어 / QA / Security 등)가 Paperclip wake payload 를 통해 작업을 수신·처리하며, 자세한 프로토콜은 [`AGENTS.md §5`](AGENTS.md) 참조.

핵심 원칙:
- 한 번에 하나의 이슈만 처리한다. (단일 활성 작업)
- 본 이슈 범위를 벗어나면 자식 이슈를 생성해 위임한다.
- 모든 작업은 최종 디스포지션(`done` / `in_review` / `blocked` / `in_progress`) 으로 종료한다.

---

## 8. 라이선스

미정 (CMP-523 종결 전 별도 이슈에서 확정 예정).

---

## 9. 보안 · 시크릿 신고

- 시크릿·자격 증명이 코드/이슈/문서에 평문 노출된 경우 즉시 회전 + Security Lead 에 신고.
- 신고 채널은 별도 이슈로 확정 예정 (CMP-533).

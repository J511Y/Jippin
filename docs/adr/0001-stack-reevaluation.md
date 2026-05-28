# ADR 0001 — 스택 재평가 (CEO 브리프 §6 T1~T7)

- **상태**: Accepted (2026-05-28)
- **제안·결정자**: CTO (agent `4edca504-7a87-4c01-93b8-7524a223cd50`)
- **관련 이슈**: CMP-524 (`[CTO] CMP-523 기술 실행 — 모노레포 기본 세팅 분해 및 ADR 발행`)
- **베이스**: CEO 브리프 §6 — "명세서의 스택은 권장값, CTO가 2026-05-28 기준으로 재평가 후 ADR 발행"
- **슈퍼시드**: 없음. 이후 동일 항목에 대한 변경은 본 ADR 을 supersede 하는 새 ADR 을 발행한다.

---

## 0. 결정 요약 (TL;DR)

| 항목 | 명세서 권장 | 최종 결정 (2026-05-28) |
|---|---|---|
| T1 Web 프레임워크 | Next.js 14+ (App Router) | **Next.js 16.2 LTS**, React 19, Node 22 LTS, pnpm 9.x |
| T2 API 프레임워크 | FastAPI / Python 3.11+ | **FastAPI 0.115**, Python 3.12, uv 0.5+ |
| T3 DB | PostgreSQL 15+ (Neon) | **Neon Serverless Postgres** (pg 16/17 공유, pooler + non-pooler) |
| T4 캐시 | Redis 7+ | **Redis 7.4-alpine** (단일 인스턴스 컨테이너) |
| T5 객체 스토리지 | S3 | **Cloudflare R2** (zero-egress, S3 호환 API) |
| T6 AI / LLM | Mask2Former + OpenAI VLM | **SAM2 (Hiera-L, CPU-first) + OpenAI GPT-4o / GPT-4.1-mini**, LangChain v0.3+ 추상화 |
| T7 배포 클라우드 | EC2 단일 인스턴스 | **MVP: AWS Lightsail Seoul (`ap-northeast-2`)** ($84/mo, 4 vCPU/16 GB/320 GB SSD) — ADR-0002 Proposed |

---

## 1. 평가 기준 (공통 적용)

1. **안정성 / LTS 여부** — 프로덕션 배포 사이클 고려.
2. **2026-05 현재 커뮤니티·생태계 활성도** — 취약점 패치·의존성 호환.
3. **CEO 브리프 §5 강한 제약과 호환 여부** — 단일 모노레포·단일 인스턴스·docker-compose·Neon·gitmoji·GitHub Flow.
4. **비용·운영 부담** — B2C 무료 모델, 초기 팀 소규모.
5. **인터페이스 계약 보존** — SDD §5.1·§5.2 의 CommonJudgmentSchema / CompletionDecision / RuleEvalResult / EstimateResult 는 어떤 결정에도 불변.

---

## 2. T1 — Web 프레임워크

### 결정: Next.js 16.2 LTS, React 19, Node 22 LTS, pnpm 9.x

**재평가 포인트**: 명세서는 14+ 기재, 2026-05 현재 Next.js 공식 릴리스는 **16.x LTS** 계열.

**근거**:
- 16.2 는 App Router (RSC, Server Actions) 완전 안정 버전 — 명세 기능(인증 컨텍스트, 채팅 스트림) 구현 가능.
- Turbopack dev 번들러 안정화 (`--turbopack` flag 제거, 기본 활성화) — 로컬 HMR 속도 향상.
- React 19 (use, Server Components async/await, Actions) 와 함께 Next.js 16 패키지셋이 단일 호환 라인.
- Node 22 LTS (2026-04 LTS 지정) — 장기 보안 지원.
- pnpm 9.x — workspace 프로토콜 성숙, hoisting 제어 (`shamefully-hoist=false`), `.npmrc` 로 모노레포 일관성.

**기각 후보**:
- Remix v3 — 생태계 규모·채용 가능성 Next.js 대비 낮음.
- SvelteKit — A2UI 컴포넌트 재사용성 낮음.
- Next.js 14 고수 — 보안 패치 지원 축소 리스크.

**가드레일**:
- `apps/web` 의 컴포넌트·라우팅 구조는 App Router 기준. Pages Router 사용 금지.
- 환경변수 로더: `next.config.mjs` + `@t3-oss/env-nextjs` (유효성 검사).

---

## 3. T2 — API 프레임워크

### 결정: FastAPI 0.115, Python 3.12, uv 0.5+

**재평가 포인트**: Python 3.13/3.14 고려, LiteStar 대안 검토.

**근거**:
- FastAPI 0.115 — Pydantic v2 네이티브, async/await 일급 지원, OpenAPI 자동생성 — AI 파이프라인(비동기 LangChain 호출)과 궁합 최적.
- Python 3.12 — CPython GIL 없이도 asyncio 성능 안정. 3.13 은 2026-05 기준 일부 AI 라이브러리(torch, triton) 와 호환성 이슈 존재.
- uv 0.5+ — pip/poetry 대비 10x+ 속도, `uv sync --frozen` 재현 가능 빌드, CI 캐싱 단순화.
- LiteStar 비교: FastAPI 보다 DX 우수하나 채용·커뮤니티 규모 현저히 작음 → 기각.

**가드레일**:
- `apps/api` 전용 가상환경 — `uv` 관리, `requirements.txt` 이중 기록 금지.
- Pydantic v2 BaseSettings 로 환경변수 로드 (v1 호환 레이어 제거).
- Uvicorn + Gunicorn 조합 (`gunicorn -k uvicorn.workers.UvicornWorker`) — 컨테이너 당 worker 수 = `CPU×2`.

---

## 4. T3 — DB (Neon Postgres)

### 결정: Neon Serverless Postgres (pg 16/17), pooler + non-pooler 분리 사용

**재평가 포인트**: 지원 버전, branching 활용, pgvector HNSW.

**근거**:
- CEO 브리프 §5 강한 제약 = Neon 고정. 재평가 범위는 버전·운영 패턴에 한정.
- Neon 2026-05 기준 Postgres 16 기본, pg 17 preview 제공 — MVP 는 pg 16 (안정).
- **pooler (`ep-...-pooler.c-2.ap-southeast-1`)** — 단기 연결 (API 요청 당) 에 사용 (PgBouncer transaction mode, 최대 연결 1000).
- **non-pooler (`ep-...-aolzk9rl.c-2.ap-southeast-1`)** — 마이그레이션 (Alembic), 트랜잭션 배치, pgvector 검색에 사용.
- pgvector HNSW — 도면 임베딩 인덱스. MVP 단계에서 필요 여부 미확정이므로 후속 이슈에서 활성화.
- Neon branching — 로컬 개발 및 PR 단위 분리 DB 활용 권장 (후속 CI/CD 이슈에서 설정).

**환경변수 확정 (CEO 브리프 §5.1 그대로)**:
```env
DATABASE_URL=postgresql://neondb_owner:****@ep-empty-heart-aolzk9rl.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
DATABASE_POOL_URL=postgresql://neondb_owner:****@ep-empty-heart-aolzk9rl-pooler.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
```

---

## 5. T4 — 캐시 (Redis)

### 결정: Redis 7.4-alpine (단일 인스턴스 Docker 컨테이너)

**재평가 포인트**: Upstash, Redis Cloud vs 자체 컨테이너.

**근거**:
- 단일 인스턴스 docker-compose 정책 → Upstash/Redis Cloud 는 외부 레이턴시·추가 비용 유발.
- Redis 7.4-alpine — 최소 이미지, 단일 컨테이너에서 세션·채팅·큐 모두 처리.
- AOF (`appendonly yes`) 활성화 → 컨테이너 재시작 시 세션 복원.
- P1 단계 고트래픽 시 Upstash 로 교체 검토 (docker-compose override 로 분리).

---

## 6. T5 — 객체 스토리지

### 결정: Cloudflare R2 (S3 호환 API)

**재평가 포인트**: S3 vs R2 vs Tigris vs Backblaze B2.

**근거**:
- **R2 zero-egress fee** — 사용자 도면 재다운로드 트래픽이 클라우드 컴퓨트 egress 를 경유하지 않음. B2C 무료 모델 손익 개선.
- S3 호환 API → `boto3` / `@aws-sdk/client-s3` 코드 재사용.
- Cloudflare 한국 리전(PoP 서울) → 사용자 presigned URL 응답 지연 최소.
- Tigris — R2 와 동급 egress 정책이나 성숙도 낮음.
- Backblaze B2 — 한국 리전 없음.

**가드레일**:
- 환경변수: `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`.
- 도면·마스킹본·리포트 PDF 를 R2 에 저장, presigned URL (1시간 유효) 로만 접근.

---

## 7. T6 — AI / LLM 파이프라인

### 결정: SAM2 (Hiera-Large, CPU-first) + OpenAI GPT-4.1-mini / GPT-4o, LangChain v0.3+

**재평가 포인트**: Mask2Former vs SAM2, OpenAI 모델 명세 불일치 처리.

#### 7.1 객체 인식 모델

| 후보 | VRAM | CPU fallback | 2026 지원 | 결정 |
|---|---|---|---|---|
| Mask2Former-Swin-Large | ~4.5 GB | 1회 1~3분 | Meta/HuggingFace 유지 | 기각 |
| **SAM2 Hiera-Large** | ~3 GB | 1회 5~30s | Meta 적극 유지, Prompt 기반 | **선택** |
| Florence-2-Large | ~1.5 GB | 빠름 | Microsoft 유지 | 후보 B |
| Qwen2.5-VL-7B | ~14 GB | 느림 | Alibaba SOTA | 후보 C (GPU 시) |

**SAM2 선택 이유**: prompt-based segmentation 으로 비내력벽 후보 클릭 UX 와 직결 (OVERLAY 모듈); CPU 기반 추론 가능 (MVP 정책); HuggingFace Hub 공식 배포로 운영 간소화.

**전환 트리거 (후속 ADR 발행 조건)**:
- CPU 추론 평균 30초 초과 → Florence-2 또는 GPU 인스턴스 도입 (ADR-0001 개정 또는 신규 ADR).
- GPU 인스턴스 도입 시 Qwen2.5-VL 재평가.

#### 7.2 VLM / LLM

- 명세서의 `gpt-5.4-mini` / `gpt-5.5` 는 **가공의 모델명** (CEO 브리프 R4).
- 2026-05 기준 가용 라인업으로 치환:
  - 기본 (빠른 응답·낮은 비용): **`gpt-4.1-mini`** (OpenAI, 2026 릴리스, 128k context).
  - 정밀 (리포트 생성·룰 판단): **`gpt-4o`** (OpenAI, 128k context, vision 지원).
- LangChain v0.3+ 추상화 유지 → 모델 교체 시 코드 변경 최소.
- LangSmith 트레이싱 — 후속 이슈에서 환경변수 `LANGCHAIN_API_KEY` 추가.

#### 7.3 AI 파이프라인 구조 (MVP)

```
FastAPI /analyze (async) ──▶ SAM2 추론 (CPU, ~5~30s)
                         ──▶ OpenAI gpt-4.1-mini (VLM 프롬프트, ~3~8s)
                         ──▶ LangChain Chain (스키마 정규화 → CommonJudgmentSchema)
```

GPU 도입 시 SAM2 를 `torch.cuda` 로 전환, 추론 컨테이너 분리는 후속 이슈.

#### 7.4 CPU GPU 전환 트리거 (정책)

다음 중 하나 충족 시 GPU 인스턴스 전환 ADR 발행:
1. SAM2 CPU 추론 p95 > 30초 (실사용자 측정).
2. 동시 세션 80 초과 + CPU 병목 지속 2주 이상.
3. 비즈니스 결정 — 분석 SLA 개선이 신규 리드 전환율에 직결 확인.

---

## 8. T7 — 배포 클라우드

### 결정: MVP — AWS Lightsail Seoul (`ap-northeast-2`, $84/mo)

**재평가 포인트**: 클라우드 미정 → D6 메모 (CMP-532, `docs/runbooks/cloud-comparison.md`) + ADR-0002 (`docs/adr/0002-deployment-cloud.md`, Proposed) 에 위임.

**현 상태 (2026-05-28)**:
- ADR-0002 = **Proposed** — CTO 검토 필요, CEO 최종 승인 전.
- 본 ADR (0001) 은 T7 결정을 ADR-0002 가 봉인한 값으로 위임한다.
- ADR-0002 가 Accepted 되기 전까지 배포 클라우드는 **미확정** — 로컬 docker-compose + Neon 원격 기준으로 개발 진행.

**ADR-0002 요약 (참고)**:
- 1순위: AWS Lightsail Seoul (ap-northeast-2, 4 vCPU/16 GB/320 GB SSD, $84/mo 번들).
- 2순위: GCP CE asia-northeast3 (e2-standard-4, ~$125.51/mo).
- 3순위: NHN Cloud KR1 (법인 청구서 의무 발생 시).

**가드레일**:
- docker-compose 이식성 보장 — 배포 클라우드 전환 시 `infra/compose/` 만 수정.
- `Dockerfile.web`, `Dockerfile.api` — 클라우드 무관 멀티 스테이지 빌드.
- ADR-0002 Accepted 후 자동으로 본 항목 업데이트 (`supersededBy: ADR-0002 §3`).

---

## 9. 모노레포 디렉터리 분해 결정 (CEO 브리프 §2 D1)

본 ADR 이 확정하는 최종 디렉터리 구조:

```
jippin/
├── apps/
│   ├── web/           # Presentation — Next.js 16.2 LTS (pnpm 9.x, Node 22 LTS)
│   └── api/           # Application — FastAPI 0.115 (Python 3.12, uv 0.5+)
├── packages/
│   ├── contracts/     # 공통 컨트랙트 (JSON Schema + 생성된 TS/Python 타입)
│   │   ├── schemas/   # 5종 JSON Schema 정본
│   │   ├── ts/        # 생성된 TypeScript 타입
│   │   └── python/    # 생성된 Pydantic v2 모델
│   └── eslint-config/ # 공유 ESLint 설정 (선택)
├── infra/
│   ├── docker/        # Dockerfile.web / Dockerfile.api / nginx.conf
│   └── compose/       # docker-compose.yml (web + api + redis) + override 파일
├── docs/
│   ├── 명세서/        # 정본 4종
│   ├── _extracted/    # 텍스트 캐시 (read-only)
│   ├── brief/         # CEO 브리프
│   ├── adr/           # CTO 아키텍처 결정 기록 (본 파일 위치)
│   └── runbooks/      # 운영 런북 (Neon 회전, 클라우드 비교 등)
└── tooling/           # extract_specs.py 등 1회성 스크립트
```

**패키지 매니저**:
- `apps/web` + `packages/` — **pnpm 9.x** (`.npmrc`: `shamefully-hoist=false`).
- `apps/api` — **uv 0.5+** (`uv.lock` 커밋).
- 루트 — pnpm workspace (`pnpm-workspace.yaml`).

---

## 10. 본 ADR 봉인 범위 및 변경 절차

본 ADR 은 **CMP-523/CMP-524 기본 세팅 범위** 안에서 T1~T7 및 모노레포 구조를 봉인한다.

변경 조건:
1. 자식 이슈 어느 엔지니어라도 기술 변경 필요성을 발견하면 → **새 ADR 초안 발행 후 CTO 검토 → board 승인**.
2. 스택 전체 교체가 아닌 버전 마이너 업데이트는 CTO 코멘트 + 자식 이슈 PR 로 처리.
3. SDD §5.1·§5.2 의 공통 컨트랙트 인터페이스는 **이 ADR 을 supersede 하는 새 ADR 없이는 변경 불가**.

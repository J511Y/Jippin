# `apps/api` — Jippin FastAPI Backend

FastAPI 0.115 / Python 3.13 / `uv` 패키지 매니저.
외부 managed Postgres (psycopg3 async) — **Supabase Postgres + Supabase Auth** — 위에서 집핀의 전 도메인 API 를 제공한다:

- **인증/계정** — Supabase Auth JWT 검증(JWKS — RS256/ES256 전용)·세션 브리지, 이메일+비밀번호 가입, SOLAPI 문자(OTP) 인증, 아이디/비번 찾기, 회원 탈퇴 (`/auth/*`)
- **상담 리드** — 익명 허용 상담 신청 + 도로명주소(JUSO) 프록시 + 담당자 알림톡 (`/leads*`)
- **자주묻는질문** — DB-backed 공개 FAQ (`/faqs*`)
- **우리집 체크** — 집합건축물대장 전유부/표제부 발급(세움터 직결 워커 또는 CODEF)·위반/확장 판정·비동기 잡 (`/home-check*`, ADR-0008/0009)
- **사전검토 세션** — 세션·주소·도면 업로드/세그멘테이션(HF Mask2Former)·벽/창호 선택·상태 전이 머신·리포트/PDF(WeasyPrint) (`/sessions*`)
- **대화형 에이전트** — deepagents(LangGraph) 기반 사전검토 에이전트, SSE 런 스트림·resume/interrupt, langgraph Postgres 체크포인터 (`/sessions/{id}/agent/*`)

공통 기반: structlog JSON 로깅, `request_id` 컨텍스트, AGENTS.md §4.5 에러 봉투, `/healthz`, 요청 로그 미들웨어.

> **DB / Auth SSOT (CMP-603/CMP-604)**: forward schema authority is `supabase/migrations/*.sql` plus Supabase GitHub Integration. Alembic (`apps/api/migrations/`) remains historical reference only. Supabase JWT `sub` maps directly to `auth.users.id`; `public.users` is an app profile table and `public.terms_consents` is the product consent audit table.

---

## 1. 사전 요구

- Python 3.13 (`.python-version=3.13`)
- [uv](https://docs.astral.sh/uv/) 0.5+
- (옵션) Docker — `docker compose up api` 실행 시
- Supabase project connection string 또는 `TEST_MODE=true` (DB 없이 부팅)
- (Supabase Auth 검증/세션 브리지를 시험할 때만) Supabase project 의 `SUPABASE_JWT_ISSUER` + `SUPABASE_JWKS_URL` (또는 `SUPABASE_REF` 로 파생) — **필수**, HS256 폴백 없음. 자세한 변수는 `.env.example` AUTH/Supabase 절 참조.

---

## 2. 로컬 실행

```bash
cd apps/api
cp .env.example .env        # 값 채우기. Supabase DB 자격증명 또는 TEST_MODE=true.
uv sync                     # 가상환경 + 의존성 설치
uv run uvicorn src.main:app --reload --port 8000
```

헬스 체크:

```bash
curl http://localhost:8000/healthz
# → { "status": "ok", "db": { "ok": true, "select_1": 1 }, "version": "0.1.0", "request_id": "..." }
```

---

## 3. 환경 변수

| 키 | 기본값 | 용도 |
|---|---|---|
| `APP_ENV` | `development` | 런타임 모드 (`development|staging|production`) |
| `LOG_LEVEL` | `INFO` | `DEBUG|INFO|WARNING|ERROR` |
| `API_PORT` | `8000` | uvicorn/gunicorn 바인드 포트 |
| `REQUEST_ID_HEADER` | `x-request-id` | request_id 미들웨어 헤더명 |
| `TEST_MODE` | `false` | true 시 `/healthz` 가 DB 호출 없이 `db.ok=true` 반환 (테스트·오프라인 부팅) |
| `DATABASE_POOL_URL` | — | Supabase pooler URL (port 6543). **요청 경로** 쿼리. (`postgresql+psycopg://`) |
| `DATABASE_URL` | — | Supabase direct URL (port 5432). **마이그레이션·DDL·롱 트랜잭션.** |
| `SUPABASE_JWT_SECRET` | — | **legacy — 현행 코드 미사용** (HS256 폴백 미구현). 기존 배포 형상 호환용 이름만 잔존. |
| `SUPABASE_JWT_AUDIENCE` | `authenticated` | Supabase JWT 검증 시 허용 audience. |
| `SUPABASE_JWT_ISSUER` | — | Supabase JWT issuer (`https://<project-ref>.supabase.co/auth/v1`). bearer 검증 **필수** (`SUPABASE_REF` 로 파생 가능). |
| `SUPABASE_JWKS_URL` | — | (ADR-0004 §2.3 rev5+) JWKS — bearer 검증 **필수** (RS256/ES256 전용, `SUPABASE_REF` 로 파생 가능). 미설정 시 503(AUTH_SESSION_CONFIG_MISSING). |
| `CORS_ALLOW_ORIGINS` | `["*"]` | JSON 리스트. 개발 외 환경에서는 좁힌다. |

위 표는 코어 부팅 변수만이다. **전체 정본은 `.env.example`** — 주요 그룹:

- **파생 프리미티브**: `SUPABASE_REF`, `PUBLIC_WEB_ORIGIN` (여러 URL 을 부팅 시 파생 — `config.py::_derive_from_primitives`)
- **리드/주소/스토리지**: `JUSO_CONFM_KEY`, `LEAD_FLOORPLAN_BUCKET`, `SESSION_FLOORPLAN_BUCKET`, `SESSION_REPORT_BUCKET`
- **우리집 체크**: `CODEF_*`, `SEUMTER_ID/PASSWORD`, `HOME_CHECK_DOC_BUCKET`, `EXTENSION_JUDGE_ENABLED`, `SEUMTEO_ENABLED`, `SEUMTEO_WORKER_URL/TOKEN` (세움터 워커 스위치 — ADR-0009)
- **에이전트/LLM**: `AGENT_ENABLED`, `AGENT_MODEL` (기본 `openai:gpt-5.6-luna`), `VLM_MODEL` (도면 VLM 전용, 기본 `openai:gpt-5.6-luna`), `OPENAI_API_KEY`, `LANGCHAIN_TRACING_V2`, `LANGSMITH_*`. 에이전트 체크포인터는 **direct `:5432` `DATABASE_URL` 필수** (`config.py::_validate_agent_checkpointer_url` 이 부팅 차단)
- **도면 세그멘테이션**: `HF_SEGMENTATION_ENDPOINT_URL/TOKEN` (+ 타임아웃/재시도/threshold — private endpoint, scale-to-zero 콜드스타트 유의)
- **OAuth/가입/SMS**: `KAKAO_*`, `GOOGLE_OAUTH_*`, `NAVER_OAUTH_*`, `OAUTH_STATE_REDIS_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SOLAPI_*`, `PHONE_OTP_*`

시크릿은 절대 커밋하지 않는다 (AGENTS.md §4.4).

---

## 4. 모듈 구성

```
apps/api/
├── pyproject.toml            # 의존성: fastapi·sqlalchemy·langchain/langgraph/deepagents·weasyprint·shapely·solapi 등
├── .python-version           # 3.13
├── Dockerfile                # multi-stage (uv builder → non-root runtime + pango/cairo + fonts-nanum — WeasyPrint)
├── alembic.ini               # Historical reference only; forward SSOT is supabase/migrations
├── .env.example              # 환경변수 정본 (§3)
├── src/
│   ├── main.py               # create_app() + lifespan(체크포인터 스키마 검증 등) + CORS + SelectiveGZip(/agent/runs SSE 제외) + RequestLog 미들웨어
│   ├── config.py             # Pydantic Settings (+ 파생 프리미티브 · 에이전트 체크포인터 URL 가드)
│   ├── db.py                 # SQLAlchemy async (psycopg3) — pool / non-pool engine
│   ├── logging.py            # structlog JSON + RequestIDMiddleware
│   ├── errors.py             # ZippinException + AGENTS.md §4.5 핸들러
│   ├── agent/                # 대화형 에이전트 런타임 — graph·runner·checkpointer·projection·warmup + tools/(segmentation·vlm·domain)
│   ├── auth/                 # JWKS·Supabase JWT·세션·providers(google/kakao/naver)·state_store
│   ├── middleware/           # request_log · selective_gzip · request_log_redaction
│   ├── models/               # ORM — auth · faqs · consultation_leads · home_check · main_feature(Session/Floorplan/AgentRun/ChatMessage/SessionStatusEvent …) · request_log
│   ├── schemas/              # Pydantic 요청/응답 계약
│   ├── services/             # 비즈니스 로직 — leads · faq · account · home_check(+extension) · main_flow · estimate · rule_engine · report_content/overlay/pdf · storage · sms/alimtalk · codef/ · seumteo/ · report_templates/
│   └── routers/              # HTTP 라우터 (모두 무조건 등록 — agent 만 AGENT_ENABLED 게이트)
│       ├── healthz.py        # GET /healthz
│       ├── auth.py           # Supabase 세션 브리지 · 약관 · linking (`/auth/*`)
│       ├── account.py        # 회원가입 · 문자인증 · 아이디/비번 찾기 · 회원탈퇴 (`/auth/*`)
│       ├── leads.py          # POST /leads · GET /leads/mine · 주소검색 프록시 · 알림톡
│       ├── faq.py            # GET /faqs · GET /faqs/{faq_id}
│       ├── home_check.py     # POST /home-check(202) · mine · {id} · {id}/continue(추가인증)
│       ├── sessions.py       # 세션 CRUD · 주소 · 리포트 · POST {id}/report/pdf
│       ├── floorplans.py     # 도면 업로드/에셋/서명URL · PATCH selected-walls(벽+창호)
│       ├── chat.py           # POST /sessions/{id}/chat/messages
│       └── agent.py          # SSE 런 · resume/interrupt · messages · warmup (AGENT_ENABLED)
├── migrations/               # Historical Alembic scripts; do not add forward revisions
└── tests/                    # pytest ~50 파일 — 라우터·서비스·룰엔진·에이전트·세움터/CODEF·PDF·상태머신 등
```

---

## 4.1 마이그레이션 (Supabase SQL SSOT)

Forward schema source of truth is `supabase/migrations/*.sql`. Supabase GitHub Integration applies migrations on `dev` and `main` pushes. Do not create new Alembic revisions for forward schema changes; `apps/api/migrations/` is historical reference only.

`docker compose up` does not run database migrations. Local compose only starts application services against the already-migrated Supabase branch selected by `DATABASE_URL` / `DATABASE_POOL_URL`.

```bash
# 새 forward migration 생성
supabase migration new <slug>
# 생성된 supabase/migrations/<timestamp>_<slug>.sql 을 사람 리뷰 후 PR 에 포함
```

봉인:

- **콘솔 직접 수정 금지.** repo migration 파일과 remote schema 가 어긋나면 `supabase db pull` / `supabase migration repair` 절차가 필요하다.
- **운영 DB 수동 SQL 금지.** roll-forward only — 잘못된 리비전은 보상 SQL migration 으로 되돌린다.

---

## 5. 테스트

```bash
cd apps/api
uv sync --group dev
uv run pytest
```

테스트는 `TEST_MODE=true` 로 동작 — Supabase DB 자격증명 없이도 패스한다.

---

## 6. Docker

```bash
docker build -t jippin-api:dev apps/api
docker run --rm -p 8000:8000 --env-file apps/api/.env jippin-api:dev
```

`docker compose` 오케스트레이션은 `infra/compose/README.md` 참고. Dockerfile runtime 스테이지는 WeasyPrint 시스템 라이브러리(pango/cairo/gdk-pixbuf)와 한글 폰트(`fonts-nanum`)를 설치한다 — PDF 리포트 발부의 전제이며, 제거 시 `POST /sessions/{id}/report/pdf` 가 깨진다.

---

## 7. 로그

stdout JSON, 모든 라인에 `request_id` 자동 주입:

```json
{"event":"api_start","env":"development","version":"0.1.0","level":"info","request_id":"-","timestamp":"2026-05-28T05:00:00Z"}
{"event":"healthz_db_failed","error":"connection refused","level":"warning","request_id":"7f6c…","timestamp":"2026-05-28T05:00:01Z"}
```

---

## 8. 표준 에러 응답 (AGENTS.md §4.5)

```json
{
  "error": {
    "code": "INSUFFICIENT_DATA",
    "message": "도면 마스킹 결과가 비어 있습니다.",
    "request_id": "7f6c1c3a-...",
    "timestamp": "2026-05-28T05:00:00Z"
  }
}
```

비즈니스 예외는 `ZippinException` 을 상속 또는 `code`/`http_status` 지정하여 raise → 공통 핸들러가 변환.

---

## 9. 참고

- ADR-0001 §3 (백엔드), §4 (DB 클라이언트 — ADR-0004 가 Supabase 로 부분 supersede)
- ADR-0004 (Supabase 전환)
- ADR-0008 (우리집 체크 — 건축물대장 전유부+표제부) · ADR-0009 (세움터 직결 내재화 — CODEF 대체, `apps/seumteo-worker`)
- AGENTS.md §4.4 (시크릿/환경변수), §4.5 (에러·응답 표준), §4.7 (사용자 식별 정책)
- `docs/runbooks/supabase-migration-plan.md`, `docs/runbooks/supabase-auth-poc.md`, `docs/runbooks/supabase-session-bridge.md`, `docs/runbooks/fly-api-deploy.md`
- `packages/contracts/` — 판단·룰·견적·에이전트 SSE·우리집 체크·세그멘테이션 스키마 정본 (관련 작업 전 선독)
- SDD v1.9 §6 (모듈 구성), §8.2 (에러 코드)

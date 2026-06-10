# `apps/api` — Jippin FastAPI Backend (CMP-528)

FastAPI 0.115 / Python 3.13 / `uv` 패키지 매니저.
외부 managed Postgres (psycopg3 async) 연결 — **Supabase Postgres + Supabase Auth** — structlog JSON 로깅, `request_id` 컨텍스트, AGENTS.md §4.5 에러 봉투, `/healthz`, Supabase Auth JWT 검증 / 세션 브리지 (CMP-595) 를 제공한다.

본 이슈(CMP-528) 범위는 **API 골격 + `/healthz` + 표준 에러/로깅**까지다. 도메인 라우터(AUTH/INPUT/AI/RULE/REPORT 등)는 후속 이슈에서 채운다.

> **DB / Auth SSOT (CMP-603/CMP-604)**: forward schema authority is `supabase/migrations/*.sql` plus Supabase GitHub Integration. Alembic (`apps/api/migrations/`) remains historical reference only. Supabase JWT `sub` maps directly to `auth.users.id`; `public.users` is an app profile table and `public.terms_consents` is the product consent audit table.

---

## 1. 사전 요구

- Python 3.13 (`.python-version=3.13`)
- [uv](https://docs.astral.sh/uv/) 0.5+
- (옵션) Docker — `docker compose up api` 실행 시
- Supabase project connection string 또는 `TEST_MODE=true` (DB 없이 부팅)
- (Supabase Auth 검증/세션 브리지를 시험할 때만) Supabase project 의 `SUPABASE_JWT_ISSUER` + `SUPABASE_JWKS_URL` 및 fallback 용 `SUPABASE_JWT_SECRET`. 자세한 변수는 `.env.example` AUTH/Supabase 절 참조.

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
| `SUPABASE_JWT_SECRET` | — | Supabase Auth HS256 verification secret. CMP-595 세션 브리지·Anonymous JWT 검증용. |
| `SUPABASE_JWT_AUDIENCE` | `authenticated` | Supabase JWT 검증 시 허용 audience. |
| `SUPABASE_JWT_ISSUER` | — | Supabase JWT issuer (`https://<project-ref>.supabase.co/auth/v1`). CMP-595 세션 브리지 필수. |
| `SUPABASE_JWKS_URL` | — | (ADR-0004 §2.3 rev5+) JWKS 1순위 — 설정 시 비대칭 키 검증. 미설정이면 `SUPABASE_JWT_SECRET` HS256 로 fallback. |
| `CORS_ALLOW_ORIGINS` | `["*"]` | JSON 리스트. 개발 외 환경에서는 좁힌다. |

전체 키는 `.env.example` 참고. 시크릿은 절대 커밋하지 않는다 (AGENTS.md §4.4).

---

## 4. 모듈 구성

```
apps/api/
├── pyproject.toml
├── .python-version           # 3.13
├── Dockerfile                # multi-stage (uv builder → non-root runtime)
├── alembic.ini               # Historical reference only; forward SSOT is supabase/migrations
├── .env.example
├── src/
│   ├── main.py               # create_app() + lifespan + CORS + GZip + middleware
│   ├── config.py             # Pydantic Settings
│   ├── db.py                 # SQLAlchemy async (psycopg3) — pool / non-pool engine
│   ├── logging.py            # structlog JSON + RequestIDMiddleware
│   ├── errors.py             # ZippinException + AGENTS.md §4.5 핸들러
│   ├── models/              # ORM 모델 (faqs · consultation_leads · sessions/floorplans · auth · …)
│   │   └── __init__.py       # Base = DeclarativeBase + naming convention (CMP-537)
│   ├── schemas/             # Pydantic 요청/응답 계약 (leads · faq · account · …)
│   ├── services/            # DB-backed 비즈니스 로직 (leads · faq · account · …)
│   └── routers/             # HTTP 라우터
│       ├── healthz.py        # GET /healthz
│       ├── auth.py           # Supabase 세션 브리지 / OAuth
│       ├── account.py        # 회원가입 · 문자인증 · 아이디/비번 찾기 · 회원탈퇴
│       ├── leads.py          # POST /leads · GET /leads/mine · 주소검색 프록시
│       ├── faq.py            # GET /faqs (공개 자주묻는질문)
│       └── sessions.py · floorplans.py · chat.py  # phase_a_skeleton 플래그에서만 등록
├── migrations/               # Historical Alembic scripts; do not add forward revisions
│   ├── env.py                # sync psycopg3, Settings.database_url 만 사용
│   ├── script.py.mako
│   └── versions/             # 리비전 파일 (YYYYMMDD_HHMM_rev_slug.py)
└── tests/
    └── test_healthz.py       # /healthz + 에러 봉투 단위 테스트
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

`docker compose` 오케스트레이션은 CMP-530 참고.

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
- AGENTS.md §4.4 (시크릿/환경변수), §4.5 (에러·응답 표준), §4.7 (사용자 식별 정책)
- `docs/runbooks/supabase-migration-plan.md`, `docs/runbooks/supabase-auth-poc.md`, `docs/runbooks/supabase-session-bridge.md`
- SDD v1.9 §6 (모듈 구성), §8.2 (에러 코드)

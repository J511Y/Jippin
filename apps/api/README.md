# `apps/api` — Jippin FastAPI Backend (CMP-528)

FastAPI 0.115 / Python 3.13 / `uv` 패키지 매니저.
외부 managed Postgres (psycopg3 async) 연결 — **Neon → Supabase 전환 중** (ADR-0004 Proposed) — structlog JSON 로깅, `request_id` 컨텍스트, AGENTS.md §4.5 에러 봉투, `/healthz`, Supabase Auth JWT 검증 / 세션 브리지 (CMP-595) 를 제공한다.

본 이슈(CMP-528) 범위는 **API 골격 + `/healthz` + 표준 에러/로깅**까지다. 도메인 라우터(AUTH/INPUT/AI/RULE/REPORT 등)는 후속 이슈에서 채운다.

> **DB / Auth SSOT 전환 (2026-06-02)**: Supabase Auth bridge (`src/auth/supabase_jwt.py`, `src/services/supabase_session.py`) 와 Supabase SQL migration 후보 (`supabase/migrations/*.sql`) 가 머지된 상태이다. Alembic (`apps/api/migrations/`) 은 **CMP-575 cutover PR 승인 전까지 schema source of truth** 를 유지한다. 운영 정본은 [`docs/runbooks/supabase-migration-plan.md`](../../docs/runbooks/supabase-migration-plan.md) · [`docs/runbooks/supabase-auth-poc.md`](../../docs/runbooks/supabase-auth-poc.md) · [`docs/runbooks/supabase-session-bridge.md`](../../docs/runbooks/supabase-session-bridge.md). 정책 정본은 [`docs/adr/0004-supabase-transition.md`](../../docs/adr/0004-supabase-transition.md).

---

## 1. 사전 요구

- Python 3.13 (`.python-version=3.13`)
- [uv](https://docs.astral.sh/uv/) 0.5+
- (옵션) Docker — `docker compose up api` 실행 시
- 외부 managed Postgres 자격증명 (전환 중: Supabase project connection string 또는 Neon URL) 또는 `TEST_MODE=true` (DB 없이 부팅)
- (Supabase Auth 검증/세션 브리지를 시험할 때만) Supabase project 의 `SUPABASE_JWT_SECRET` 또는 `SUPABASE_JWKS_URL`. 자세한 변수는 `.env.example` AUTH/Supabase 절 참조.

---

## 2. 로컬 실행

```bash
cd apps/api
cp .env.example .env        # 값 채우기. Supabase/Neon DB 자격증명 또는 TEST_MODE=true.
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
| `DATABASE_POOL_URL` | — | Pooler URL (Supabase pgbouncer port 6543 / Neon `-pooler` 호스트). **요청 경로** 쿼리. (`postgresql+psycopg://`) |
| `DATABASE_URL` | — | Non-pooler URL (Supabase direct port 5432 / Neon non-pooler 호스트). **마이그레이션·DDL·롱 트랜잭션.** |
| `SUPABASE_JWT_SECRET` | — | Supabase Auth HS256 verification secret. CMP-595 세션 브리지·Anonymous JWT 검증용. |
| `SUPABASE_JWT_AUDIENCE` | `authenticated` | Supabase JWT 검증 시 허용 audience. |
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
├── alembic.ini               # Alembic 설정 (CMP-537)
├── .env.example
├── src/
│   ├── main.py               # create_app() + lifespan + CORS + GZip + middleware
│   ├── config.py             # Pydantic Settings
│   ├── db.py                 # SQLAlchemy async (psycopg3) — pool / non-pool engine
│   ├── logging.py            # structlog JSON + RequestIDMiddleware
│   ├── errors.py             # ZippinException + AGENTS.md §4.5 핸들러
│   ├── models/__init__.py    # Base = DeclarativeBase + naming convention (CMP-537)
│   └── routers/
│       └── healthz.py        # GET /healthz
├── migrations/               # Alembic 스크립트 (CMP-537)
│   ├── env.py                # sync psycopg3, Settings.database_url 만 사용
│   ├── script.py.mako
│   └── versions/             # 리비전 파일 (YYYYMMDD_HHMM_rev_slug.py)
└── tests/
    └── test_healthz.py       # /healthz + 에러 봉투 단위 테스트
```

---

## 4.1 마이그레이션 (CMP-537 / CMP-575, transitional)

> **SSOT 전환 상태 (2026-06-02)**: 현 시점 schema source of truth 는 **Alembic** (`apps/api/migrations/versions/*.py`) 이다. CMP-575 가 동일 schema 의 Supabase SQL 후보 (`supabase/migrations/*.sql`) 를 이미 준비했으며, ADR-0004 Accepted + Supabase CI/deploy cutover PR 머지 시점에 SSOT 가 SQL 로 이동한다. **cutover 후에는 신규 Alembic revision 생성 금지** ([`docs/runbooks/supabase-migration-plan.md`](../../docs/runbooks/supabase-migration-plan.md) §Recommended transition). 본 절은 cutover 완료까지 운영 정본이다.

DB 스키마 변경은 **autogenerate → 사람 리뷰 → upgrade** 3-step 으로 진행한다. 컨테이너 ENTRYPOINT 에 묶지 않고 `infra/compose/docker-compose.yml` 의 `migrate` 사이드카로 분리해 돌린다 (multi-replica 경합/롤백 회피).

```bash
# 1) 모델 변경 후 리비전 자동 생성
make migration name=add_users
#   → apps/api/migrations/versions/<UTC ts>_<rev>_add_users.py 생성
#   → ruff format 이 post-write hook 으로 즉시 적용된다.

# 2) 생성된 파일을 PR 에 첨부하기 전 반드시 **사람 리뷰**:
#    - autogenerate 가 놓친 인덱스/제약/타입 차이 보강
#    - downgrade 함수에 실제 역연산을 적는다 (prod 에선 실행 안 해도, 개발/리뷰 용)
#    - 데이터 마이그레이션이 필요한 경우 별도 리비전으로 분리

# 3) 외부 managed Postgres 에 적용 (Supabase/Neon 자격증명, DATABASE_URL non-pooler)
make migrate                            # 로컬: uv 가상환경에서 직접
docker compose -f infra/compose/docker-compose.yml up migrate   # 컨테이너 사이드카
```

봉인:

- **`DATABASE_URL` (non-pooler) 만 사용한다.** `DATABASE_POOL_URL` (pgbouncer) 은 DDL/prepared-statement 호환성 문제로 alembic 경로에서 금지.
- **`alembic downgrade` 는 prod 에서 금지.** roll-forward only — 잘못된 리비전은 보상 리비전으로 되돌린다.
- 리비전 파일명은 `YYYYMMDD_HHMM_<rev>_<slug>.py` 로 고정 (`alembic.ini` `file_template`).

---

## 5. 테스트

```bash
cd apps/api
uv sync --group dev
uv run pytest
```

테스트는 `TEST_MODE=true` 로 동작 — Supabase/Neon DB 자격증명 없이도 패스한다.

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
- ADR-0004 (Neon → Supabase 전환, Proposed)
- AGENTS.md §4.4 (시크릿/환경변수), §4.5 (에러·응답 표준), §4.7 (사용자 식별 정책)
- `docs/runbooks/supabase-migration-plan.md`, `docs/runbooks/supabase-auth-poc.md`, `docs/runbooks/supabase-session-bridge.md`
- SDD v1.9 §6 (모듈 구성), §8.2 (에러 코드)

# `apps/api` — Jippin FastAPI Backend (CMP-528)

FastAPI 0.115 / Python 3.12 / `uv` 패키지 매니저.
Neon Postgres(psycopg3 async) 연결, structlog JSON 로깅, `request_id` 컨텍스트, AGENTS.md §4.5 에러 봉투, `/healthz` 를 제공한다.

본 이슈(CMP-528) 범위는 **API 골격 + `/healthz` + 표준 에러/로깅**까지다. 도메인 라우터(AUTH/INPUT/AI/RULE/REPORT 등)는 후속 이슈에서 채운다.

---

## 1. 사전 요구

- Python 3.12 (`.python-version=3.12`)
- [uv](https://docs.astral.sh/uv/) 0.5+
- (옵션) Docker — `docker compose up api` 실행 시
- Neon Postgres 계정 또는 `TEST_MODE=true` (DB 없이 부팅)

---

## 2. 로컬 실행

```bash
cd apps/api
cp .env.example .env        # 값 채우기. Neon 자격증명 또는 TEST_MODE=true.
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
| `DATABASE_POOL_URL` | — | Neon pooler URL. **요청 경로** 쿼리. (`postgresql+psycopg://`) |
| `DATABASE_URL` | — | Neon non-pooler URL. **마이그레이션·롱 트랜잭션.** |
| `CORS_ALLOW_ORIGINS` | `["*"]` | JSON 리스트. 개발 외 환경에서는 좁힌다. |

전체 키는 `.env.example` 참고. 시크릿은 절대 커밋하지 않는다 (AGENTS.md §4.4).

---

## 4. 모듈 구성

```
apps/api/
├── pyproject.toml
├── .python-version           # 3.12
├── Dockerfile                # multi-stage (uv builder → non-root runtime)
├── .env.example
├── src/
│   ├── main.py               # create_app() + lifespan + CORS + GZip + middleware
│   ├── config.py             # Pydantic Settings
│   ├── db.py                 # SQLAlchemy async (psycopg3) — pool / non-pool engine
│   ├── logging.py            # structlog JSON + RequestIDMiddleware
│   ├── errors.py             # ZippinException + AGENTS.md §4.5 핸들러
│   └── routers/
│       └── healthz.py        # GET /healthz
└── tests/
    └── test_healthz.py       # /healthz + 에러 봉투 단위 테스트
```

---

## 5. 테스트

```bash
cd apps/api
uv sync --group dev
uv run pytest
```

테스트는 `TEST_MODE=true` 로 동작 — Neon 자격증명 없이도 패스한다.

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

- ADR-0001 §3 (백엔드), §4 (Neon 클라이언트)
- AGENTS.md §4.4 (시크릿/환경변수), §4.5 (에러·응답 표준)
- SDD v1.9 §6 (모듈 구성), §8.2 (에러 코드)

"""세움터 워커 HTTP 진입점 (FastAPI + Playwright).

- 앱 기동 시 브라우저 1개 launch, 로그인 컨텍스트 상주.
- ``POST /jobs/building-register`` 로 발급 잡을 받아 결과(구조화 필드 + PDF base64)를 돌려준다.
- 도메인 오류는 HTTP 200 + ``{ok:false, category}`` 로 반환(호출측이 CODEF 예외로 승격).
- Flycast 사설망 위에서 동작하지만, 설정 시 ``SEUMTEO_WORKER_TOKEN`` Bearer 로 추가 인증.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from .browser import BrowserManager, LoginError
from .config import get_settings
from .flow import FlowError, SeumteoFlow
from .models import BuildingRegisterError, BuildingRegisterRequest

_log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    mgr = BrowserManager(settings)
    await mgr.start()
    app.state.mgr = mgr
    app.state.flow = SeumteoFlow(mgr, settings)
    try:
        yield
    finally:
        await mgr.stop()


app = FastAPI(title="jippin-seumteo-worker", lifespan=lifespan)


def _require_token(authorization: str | None) -> None:
    token = get_settings().seumteo_worker_token
    if token and authorization != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/healthz")
async def healthz():
    # 브라우저가 죽었으면 503 — Fly 헬스체크가 실패해 wedged 머신을 재활용하도록 한다.
    mgr: BrowserManager = app.state.mgr
    healthy = mgr.is_healthy()
    if not healthy:
        return JSONResponse(status_code=503, content={"ok": False, "browser": False})
    return {"ok": True, "browser": True}


@app.post("/jobs/building-register")
async def building_register(
    req: BuildingRegisterRequest, authorization: str | None = Header(default=None)
):
    _require_token(authorization)
    flow: SeumteoFlow = app.state.flow
    settings = get_settings()
    started = time.monotonic()
    # 주소·동·호는 로그에 남기지 않는다. 잡 수명과 대장 종류만 남겨 Flycast/세움터 경계를
    # 구분할 수 있게 한다.
    _log.info("job.received", register_kind=req.register_kind)
    try:
        result = await asyncio.wait_for(
            flow.run(req), timeout=settings.job_deadline_ms / 1000
        )
        _log.info(
            "job.completed",
            register_kind=req.register_kind,
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        return result
    except LoginError as exc:
        _log.warning(
            "job.auth_error",
            register_kind=req.register_kind,
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        return JSONResponse(
            content=BuildingRegisterError(
                category="auth", message=str(exc)
            ).model_dump()
        )
    except FlowError as exc:
        _log.warning(
            "job.flow_error",
            category=exc.category,
            message=exc.message,
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        return JSONResponse(
            content=BuildingRegisterError(
                category=exc.category,
                message=exc.message,
                field=exc.field,
                options=exc.options,
            ).model_dump()
        )
    except asyncio.TimeoutError:
        _log.warning(
            "job.timeout",
            register_kind=req.register_kind,
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        return JSONResponse(
            content=BuildingRegisterError(
                category="upstream", message="발급 처리가 시간 내 완료되지 않았습니다."
            ).model_dump()
        )
    except Exception:  # noqa: BLE001
        _log.exception(
            "job.unexpected",
            register_kind=req.register_kind,
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        # 예기치 못한 오류(브라우저 크래시 등) — 다음 잡을 위해 브라우저 재기동 시도.
        try:
            await app.state.mgr.ensure_logged_in()
        except Exception:  # noqa: BLE001
            pass
        return JSONResponse(
            status_code=502,
            content=BuildingRegisterError(
                category="upstream", message="발급 처리 중 오류가 발생했습니다."
            ).model_dump(),
        )

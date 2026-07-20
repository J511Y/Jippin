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
from .models import (
    BuildingRegisterBundleRequest,
    BuildingRegisterBundleResponse,
    BuildingRegisterError,
    BuildingRegisterRequest,
)
from .timing import bind_job, new_job_id

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
    # 브라우저만 죽고 FastAPI 프로세스가 남은 경우에는 먼저 자체 재기동을 시도한다. 실제 잡은
    # healthz ready 뒤에만 .internal로 전달되므로, 여기서 복구하지 않으면 Fly 재활용 전까지
    # warm-up 폴링만 하다 모든 요청이 실패한다.
    mgr: BrowserManager = app.state.mgr
    if not mgr.is_healthy():
        try:
            await mgr.ensure_logged_in()
            _log.info("healthz.browser_restarted")
        except Exception:  # noqa: BLE001 — 외부 헬스체크에는 503만 노출한다.
            _log.warning("healthz.browser_restart_failed", exc_info=True)
    if not mgr.is_healthy():
        return JSONResponse(status_code=503, content={"ok": False, "browser": False})
    return {"ok": True, "browser": True}


@app.post("/readyz")
async def readyz(authorization: str | None = Header(default=None)):
    """Chromium뿐 아니라 세움터 로그인 세션까지 실제 잡 투입 가능한 상태로 만든다."""

    _require_token(authorization)
    mgr: BrowserManager = app.state.mgr
    started = time.monotonic()
    try:
        await mgr.prepare_authenticated()
    except LoginError:
        _log.warning(
            "readyz.auth_failed",
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "browser": mgr.is_healthy(),
                "authenticated": False,
                "category": "auth",
            },
        )
    except Exception:  # noqa: BLE001 — 준비 경로에는 내부 오류를 노출하지 않는다.
        _log.warning(
            "readyz.failed",
            duration_ms=round((time.monotonic() - started) * 1000),
            exc_info=True,
        )
        return JSONResponse(
            status_code=503,
            content={"ok": False, "browser": mgr.is_healthy(), "authenticated": False},
        )
    _log.info(
        "readyz.ready",
        duration_ms=round((time.monotonic() - started) * 1000),
    )
    return {"ok": True, "browser": True, "authenticated": True}


@app.post("/jobs/building-register")
async def building_register(
    req: BuildingRegisterRequest,
    authorization: str | None = Header(default=None),
    x_jippin_trace_id: str | None = Header(default=None),
):
    _require_token(authorization)
    flow: SeumteoFlow = app.state.flow
    settings = get_settings()
    started = time.monotonic()
    worker_job_id = new_job_id(x_jippin_trace_id)
    # 주소·동·호는 로그에 남기지 않는다. 잡 수명과 대장 종류만 남겨 Flycast/세움터 경계를
    # 구분할 수 있게 한다.
    _log.info(
        "job.received", worker_job_id=worker_job_id, register_kind=req.register_kind
    )
    try:
        with bind_job(worker_job_id):
            result = await asyncio.wait_for(
                flow.run(req), timeout=settings.job_deadline_ms / 1000
            )
        _log.info(
            "job.completed",
            worker_job_id=worker_job_id,
            register_kind=req.register_kind,
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        return result
    except LoginError as exc:
        _log.warning(
            "job.auth_error",
            worker_job_id=worker_job_id,
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
            worker_job_id=worker_job_id,
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
            worker_job_id=worker_job_id,
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
            worker_job_id=worker_job_id,
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


def _bundle_error_payload(
    category: str, message: str, *, field: str | None = None, options=None
) -> dict:
    """공유 단계 실패 — 동일 오류 봉투를 양쪽 종류에 복제한다(호출측 매핑은 단건과 동일)."""

    err = BuildingRegisterError(
        category=category, message=message, field=field, options=options
    )
    return BuildingRegisterBundleResponse(exclusive=err, heading=err).model_dump()


@app.post("/jobs/building-register-bundle")
async def building_register_bundle(
    req: BuildingRegisterBundleRequest,
    authorization: str | None = Header(default=None),
    x_jippin_trace_id: str | None = Header(default=None),
):
    _require_token(authorization)
    flow: SeumteoFlow = app.state.flow
    settings = get_settings()
    started = time.monotonic()
    worker_job_id = new_job_id(x_jippin_trace_id)
    # 주소·동·호는 로그에 남기지 않는다(단건 잡과 동일 정책).
    _log.info("job.received", worker_job_id=worker_job_id, register_kind="bundle")
    try:
        with bind_job(worker_job_id):
            result = await asyncio.wait_for(
                flow.run_bundle(req), timeout=settings.bundle_deadline_ms / 1000
            )
        _log.info(
            "job.completed",
            worker_job_id=worker_job_id,
            register_kind="bundle",
            exclusive_ok=result.exclusive.ok,
            heading_ok=result.heading.ok,
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        return result
    except LoginError as exc:
        _log.warning(
            "job.auth_error",
            worker_job_id=worker_job_id,
            register_kind="bundle",
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        return JSONResponse(content=_bundle_error_payload("auth", str(exc)))
    except FlowError as exc:
        _log.warning(
            "job.flow_error",
            worker_job_id=worker_job_id,
            register_kind="bundle",
            category=exc.category,
            message=exc.message,
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        return JSONResponse(
            content=_bundle_error_payload(
                exc.category, exc.message, field=exc.field, options=exc.options
            )
        )
    except asyncio.TimeoutError:
        _log.warning(
            "job.timeout",
            worker_job_id=worker_job_id,
            register_kind="bundle",
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        return JSONResponse(
            content=_bundle_error_payload(
                "upstream", "발급 처리가 시간 내 완료되지 않았습니다."
            )
        )
    except Exception:  # noqa: BLE001
        _log.exception(
            "job.unexpected",
            worker_job_id=worker_job_id,
            register_kind="bundle",
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        # 예기치 못한 오류(브라우저 크래시 등) — 다음 잡을 위해 브라우저 재기동 시도.
        try:
            await app.state.mgr.ensure_logged_in()
        except Exception:  # noqa: BLE001
            pass
        return JSONResponse(
            status_code=502,
            content=_bundle_error_payload(
                "upstream", "발급 처리 중 오류가 발생했습니다."
            ),
        )

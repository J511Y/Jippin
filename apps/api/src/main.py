from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .auth.state_store import close_oauth_state_store
from .config import get_settings
from .db import dispose_engines
from .errors import register_exception_handlers
from .logging import RequestIDMiddleware, configure_logging, get_logger
from .middleware.request_log import RequestLogMiddleware
from .routers.auth import router as auth_router
from .routers.chat import router as chat_router
from .routers.floorplans import router as floorplans_router
from .routers.healthz import router as healthz_router
from .routers.sessions import router as sessions_router


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    log = get_logger("zippin.main")
    settings = get_settings()
    log.info("api_start", env=settings.app_env, version=settings.api_version)
    try:
        yield
    finally:
        await close_oauth_state_store()
        await dispose_engines()
        log.info("api_stop")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Jippin API",
        version=settings.api_version,
        lifespan=_lifespan,
    )

    # Middleware add-order is reverse of execution order:
    # last added wraps first → RequestIDMiddleware sees every request first.
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[settings.request_id_header],
    )
    app.add_middleware(RequestIDMiddleware)
    # Last added wraps first: request logging sees the final response while
    # reading request.state.request_id after RequestIDMiddleware runs.
    app.add_middleware(RequestLogMiddleware)

    register_exception_handlers(app)
    app.include_router(auth_router)
    app.include_router(healthz_router)
    # Phase A 메인 흐름 (CMP-609 skeleton). DB-backed repository 는 CMP-608
    # migration 이 들어온 뒤 services.main_flow 의 in-memory 구현을 교체한다.
    app.include_router(sessions_router)
    app.include_router(floorplans_router)
    app.include_router(chat_router)

    return app


app = create_app()

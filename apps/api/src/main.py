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
from .routers.account import router as account_router
from .routers.auth import router as auth_router
from .routers.chat import router as chat_router
from .routers.faq import router as faq_router
from .routers.floorplans import router as floorplans_router
from .routers.healthz import router as healthz_router
from .routers.home_check import router as home_check_router
from .routers.leads import router as leads_router
from .routers.sessions import router as sessions_router
from .services.phone_verification import close_phone_verification_store


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
        await close_phone_verification_store()
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
    # 이메일/비밀번호 회원가입·문자인증·아이디/비번 찾기·회원탈퇴 (CMP-DIRECT).
    # DB/Supabase-backed 실 기능이므로 phase_a 플래그와 무관하게 항상 등록한다.
    app.include_router(account_router)
    app.include_router(healthz_router)
    # 상담 리드(consultation leads) — DB-backed 실 기능이므로 phase_a 플래그와 무관하게
    # 항상 등록한다. 비회원(익명 Supabase 토큰)도 신청 가능(CMP-DIRECT).
    app.include_router(leads_router)
    # 자주묻는질문(FAQ) — 공개 콘텐츠 읽기 전용(GET /faqs). DB-backed 실 기능이므로
    # phase_a 플래그와 무관하게 항상 등록한다(CMP-DIRECT).
    app.include_router(faq_router)
    # 우리집 체크(home-check) — 집합건축물대장 전유부+표제부 CODEF 비동기 조회(ADR-0008).
    # DB-backed 실 기능이므로 phase_a 플래그와 무관하게 항상 등록한다. 비회원(익명
    # Supabase 토큰)도 조회 가능하고, /mine 이력은 로그인 회원만 가능하다.
    app.include_router(home_check_router)
    # Phase A 메인 흐름 (CMP-609 skeleton → CMP-608 상당 DB 영속화 완료).
    # services.main_flow 는 실 Phase A 테이블 (migration 0008) 에 기록한다.
    # 기능 자체가 아직 미공개 (주소 정규화/도면 파이프라인 미구현) 이므로
    # settings 의 phase_a_skeleton_enabled 플래그가 켜진 환경에서만 라우터를
    # 등록한다 (운영 default 는 False — 출시 결정 시 별도 이슈로 켠다).
    if settings.phase_a_skeleton_enabled:
        app.include_router(sessions_router)
        app.include_router(floorplans_router)
        app.include_router(chat_router)

    return app


app = create_app()

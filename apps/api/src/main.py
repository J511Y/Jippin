from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth.state_store import close_oauth_state_store
from .config import get_settings
from .db import dispose_engines
from .errors import register_exception_handlers
from .logging import RequestIDMiddleware, configure_logging, get_logger
from .middleware.request_log import RequestLogMiddleware
from .middleware.selective_gzip import SelectiveGZipMiddleware
from .routers.account import router as account_router
from .routers.agent import router as agent_router
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
    # 에이전트 체크포인터 스키마 검증(DDL 실행하지 않음). 누락 시 agent 를 런타임
    # fail-safe 로 비활성화한다(라우터 start/resume 가 503). test_mode 에서는 DB 에
    # 접속하지 않으므로 검증을 건너뛴다.
    app.state.agent_ready = True
    if settings.agent_enabled and not settings.test_mode:
        from .agent.checkpointer import verify_schema

        app.state.agent_ready = await verify_schema()
        if not app.state.agent_ready:
            log.error("agent_disabled_checkpointer_schema_missing")
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

    app.state.agent_ready = True

    # Middleware add-order is reverse of execution order:
    # last added wraps first → RequestIDMiddleware sees every request first.
    # SSE(/agent/runs) 는 gzip 청크 압축이 즉시 flush 를 방해하므로 제외한다.
    app.add_middleware(
        SelectiveGZipMiddleware,
        minimum_size=1024,
        exclude_substrings=("/agent/runs",),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # 에이전트 SSE 시작 응답의 X-Agent-Run-Id 를 브라우저가 읽어 resume 에 쓴다.
        expose_headers=[settings.request_id_header, "X-Agent-Run-Id"],
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
    # 사전검토 세션/도면/채팅 — 프로덕션 실기능(세션 CRUD·도면 업로드·리포트). 웹의
    # /sessions 노출과 한 몸이므로 phase_a 플래그와 무관하게 **항상** 등록한다. 과거
    # skeleton 시절엔 phase_a_skeleton_enabled 로 가렸지만, 웹은 빌드타임에 노출되어
    # 백엔드 플래그와 분리되므로 게이트를 두면 프로덕션에서 /sessions 가 404 가 된다.
    app.include_router(sessions_router)
    app.include_router(floorplans_router)
    app.include_router(chat_router)
    # 에이전트 세션 (우리집 체크 대화형 에이전트) — agent_enabled 환경에만 등록한다
    # (config validator 가 agent_enabled 시 phase_a_skeleton_enabled·OPENAI 키를 요구).
    if settings.agent_enabled:
        app.include_router(agent_router)

    return app


app = create_app()

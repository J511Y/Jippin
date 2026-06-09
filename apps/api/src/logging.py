from __future__ import annotations

import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, AsyncIterator, Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .config import get_settings

if TYPE_CHECKING:
    import httpx

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


# 외부 연동(SOLAPI/Supabase/OAuth/주소검색 등) 호출 로깅 전용 로거. request_id
# 컨텍스트가 자동으로 묶여 요청 단위로 외부 호출을 추적할 수 있다.
_external_logger = get_logger("zippin.external")


def _elapsed_ms(started: float) -> int:
    return max(1, int((time.perf_counter() - started) * 1000))


async def log_http_call(
    provider: str,
    operation: str,
    send: Callable[[], Awaitable["httpx.Response"]],
    **fields: Any,
) -> "httpx.Response":
    """외부 HTTP 호출을 실행하면서 성공/실패를 구조화 로그로 남긴다.

    provider/operation/status/duration_ms 만 기록하고 요청·응답 본문은 절대 남기지
    않는다(토큰·PII 유출 방지). 예외/응답은 원본 그대로 호출부로 전달한다 — 로깅은
    부수효과일 뿐 흐름을 바꾸지 않는다.
    """

    started = time.perf_counter()
    try:
        response = await send()
    except Exception as exc:
        _external_logger.warning(
            "external_call_failed",
            provider=provider,
            operation=operation,
            duration_ms=_elapsed_ms(started),
            error=type(exc).__name__,
            **fields,
        )
        raise
    emit = (
        _external_logger.warning
        if response.status_code >= 500
        else _external_logger.info
    )
    emit(
        "external_call",
        provider=provider,
        operation=operation,
        status=response.status_code,
        duration_ms=_elapsed_ms(started),
        **fields,
    )
    return response


@asynccontextmanager
async def log_external_op(
    provider: str, operation: str, **fields: Any
) -> AsyncIterator[None]:
    """HTTP 응답 객체를 돌려주지 않는 외부 호출(예: SOLAPI SDK)용 로깅 래퍼.

    블록이 정상 종료하면 ``external_call``, 예외로 빠져나가면 ``external_call_failed``
    를 남기고 예외를 그대로 재전파한다.
    """

    started = time.perf_counter()
    try:
        yield
    except Exception as exc:
        _external_logger.warning(
            "external_call_failed",
            provider=provider,
            operation=operation,
            duration_ms=_elapsed_ms(started),
            error=type(exc).__name__,
            **fields,
        )
        raise
    _external_logger.info(
        "external_call",
        provider=provider,
        operation=operation,
        duration_ms=_elapsed_ms(started),
        **fields,
    )


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Reuse or mint `X-Request-ID`; bind into structlog contextvars."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        settings = get_settings()
        header = settings.request_id_header
        rid = request.headers.get(header) or str(uuid.uuid4())

        ctx_token = request_id_ctx.set(rid)
        structlog.contextvars.bind_contextvars(request_id=rid)
        request.state.request_id = rid

        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
            request_id_ctx.reset(ctx_token)

        response.headers[header] = rid
        return response

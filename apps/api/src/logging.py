from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .config import get_settings

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

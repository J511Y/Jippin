from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .logging import get_logger

logger = get_logger("zippin.errors")


class ZippinException(Exception):
    """Base domain exception — maps to AGENTS.md §4.5 error envelope."""

    code: str = "INTERNAL_ERROR"
    http_status: int = 500

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        http_status: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code is not None:
            self.code = code
        if http_status is not None:
            self.http_status = http_status


def _envelope(code: str, message: str, request_id: str) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


async def _zippin_handler(request: Request, exc: ZippinException) -> JSONResponse:
    logger.warning(
        "zippin_exception",
        code=exc.code,
        message=exc.message,
        status=exc.http_status,
    )
    body = _envelope(exc.code, exc.message, _rid(request))
    if exc.details:
        body["detail"] = exc.details
    return JSONResponse(status_code=exc.http_status, content=body)


async def _http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(f"HTTP_{exc.status_code}", str(exc.detail), _rid(request)),
    )


async def _validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    body = _envelope("VALIDATION_ERROR", "Request validation failed", _rid(request))
    body["detail"] = exc.errors()
    return JSONResponse(status_code=422, content=body)


async def _fallback_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_exception", error=str(exc))
    return JSONResponse(
        status_code=500,
        content=_envelope(
            "INTERNAL_ERROR", "An internal error occurred", _rid(request)
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ZippinException, _zippin_handler)
    app.add_exception_handler(StarletteHTTPException, _http_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(Exception, _fallback_handler)

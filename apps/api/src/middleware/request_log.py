from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Iterable, Mapping
from typing import Any

import sqlalchemy as sa
from starlette.datastructures import Headers, QueryParams
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..config import get_settings
from ..db import get_engine
from ..logging import get_logger
from ..models import RequestLog
from .request_log_redaction import (
    MAX_LOG_BODY_BYTES,
    decode_body_bytes,
    redact_mapping,
)

logger = get_logger("zippin.request_log")

RequestLogRecord = dict[str, Any]


class RequestLogMiddleware:
    """Capture API request/response metadata and enqueue a best-effort DB insert."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_body_bytes: int = MAX_LOG_BODY_BYTES,
    ) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        request_body = bytearray()
        response_body = bytearray()
        response_status = 500
        request = Request(scope)

        async def receive_wrapper() -> Message:
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                if body and len(request_body) <= self.max_body_bytes:
                    remaining = self.max_body_bytes + 1 - len(request_body)
                    request_body.extend(body[:remaining])
            return message

        async def send_wrapper(message: Message) -> None:
            nonlocal response_status
            pending_record: RequestLogRecord | None = None
            if message["type"] == "http.response.start":
                response_status = int(message["status"])
            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                if body and len(response_body) <= self.max_body_bytes:
                    remaining = self.max_body_bytes + 1 - len(response_body)
                    response_body.extend(body[:remaining])
                if not message.get("more_body", False):
                    duration_ms = max(1, int((time.perf_counter() - started) * 1000))
                    pending_record = build_request_log_record(
                        request=request,
                        request_body=bytes(request_body),
                        response_body=bytes(response_body),
                        response_status=response_status,
                        duration_ms=duration_ms,
                    )
            await send(message)
            if pending_record is not None:
                try:
                    schedule_request_log_insert(pending_record)
                except Exception:
                    logger.warning("request_log_schedule_failed", exc_info=True)

        await self.app(scope, receive_wrapper, send_wrapper)


def schedule_request_log_insert(record: RequestLogRecord) -> None:
    if get_settings().test_mode:
        return
    asyncio.create_task(_safe_insert_request_log(record))


async def _safe_insert_request_log(record: RequestLogRecord) -> None:
    try:
        await insert_request_log(record)
    except Exception:
        logger.warning("request_log_insert_failed", exc_info=True)


async def insert_request_log(record: RequestLogRecord) -> None:
    async with get_engine().begin() as conn:
        await conn.execute(sa.insert(RequestLog).values(**record))


def build_request_log_record(
    *,
    request: Request,
    request_body: bytes,
    response_body: bytes,
    response_status: int,
    duration_ms: int,
) -> RequestLogRecord:
    headers = request.headers
    ip_addrs = extract_ip_addrs(headers, request.client.host if request.client else None)
    response_message, error_code = parse_response_envelope(response_body)
    user_id = extract_user_id(request)
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())

    return {
        "request_id": request_id_to_uuid(str(request_id)),
        "is_anonymous_user": user_id is None,
        "user_id": user_id,
        "device_id": first_header(headers, "x-device-id", "x-client-device-id"),
        "version": first_header(headers, "x-app-version", "x-client-version"),
        "device": classify_device(headers.get("user-agent")),
        "country": first_header(headers, "cf-ipcountry", "x-vercel-ip-country"),
        "region": first_header(
            headers, "x-vercel-ip-region", "x-vercel-ip-country-region"
        ),
        "ip_addrs": ip_addrs,
        "last_ip": ip_addrs[-1] if ip_addrs else None,
        "url": request.url.path,
        "parameter": query_params_to_dict(request.query_params),
        "method": request.method,
        "body": decode_body_bytes(
            request_body,
            content_type=headers.get("content-type"),
        ),
        "response_code": response_status,
        "response_message": response_message,
        "error_code": error_code,
        "duration_ms": duration_ms,
        "user_agent": headers.get("user-agent"),
        "referrer": headers.get("referer") or headers.get("referrer"),
    }


def request_id_to_uuid(request_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(request_id)
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, request_id)


def extract_user_id(request: Request) -> str | None:
    user = getattr(request.state, "user", None)
    if user is None:
        return None
    if isinstance(user, Mapping):
        value = user.get("id") or user.get("user_id") or user.get("sub")
    else:
        value = (
            getattr(user, "id", None)
            or getattr(user, "user_id", None)
            or getattr(user, "sub", None)
        )
    return str(value) if value is not None else None


def first_header(headers: Headers, *names: str) -> str | None:
    for name in names:
        value = headers.get(name)
        if value:
            return value
    return None


def classify_device(user_agent: str | None) -> str:
    if not user_agent:
        return "other"
    normalized = user_agent.lower()
    if "ipad" in normalized or "tablet" in normalized:
        return "tablet"
    if "notebook" in normalized or "laptop" in normalized:
        return "notebook"
    if "mobile" in normalized or "iphone" in normalized or "android" in normalized:
        return "mobile"
    if any(marker in normalized for marker in ("windows", "macintosh", "x11", "linux")):
        return "pc"
    return "other"


def extract_ip_addrs(headers: Headers, client_host: str | None) -> list[str]:
    xff = headers.get("x-forwarded-for", "")
    forwarded = [part.strip() for part in xff.split(",") if part.strip()]
    addrs = [client_host] if client_host else []
    addrs.extend(reversed(forwarded))
    return dedupe_preserve_order(addr for addr in addrs if addr)


def dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def query_params_to_dict(query_params: QueryParams) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in query_params:
        values = query_params.getlist(key)
        result[key] = values if len(values) > 1 else values[0]
    return redact_mapping(result)


def parse_response_envelope(response_body: bytes) -> tuple[str | None, str | None]:
    if not response_body:
        return None, None
    try:
        body = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, None
    if not isinstance(body, Mapping):
        return None, None

    error = body.get("error")
    if isinstance(error, Mapping):
        message = error.get("message")
        code = error.get("code")
        return (
            str(message) if message is not None else None,
            str(code) if code is not None else None,
        )

    message = body.get("message")
    return str(message) if message is not None else None, None

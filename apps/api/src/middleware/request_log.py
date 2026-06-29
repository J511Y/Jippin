from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

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

# Fly 헬스체크가 30초 간격으로 /healthz 를 호출해 request_logs 를 채우므로
# 기록 대상에서 제외한다. 헬스 상태는 Fly 체크 결과로 충분하다.
SKIP_PATHS: frozenset[str] = frozenset({"/healthz"})

# 본문(body)을 저장하지 않을 경로 substring. 에이전트 채팅(start/resume)은 자유 입력
# 텍스트(전체 주소·리모델링 상세 등 PII)를 담으므로 본문 로깅에서 제외한다 — 메타
# (메서드/상태/소요시간)는 그대로 남긴다. redactor 가 nested message.content 를 못
# 가리므로 경로 단위로 막는다.
BODY_SKIP_SUBSTRINGS: tuple[str, ...] = ("/agent/runs",)


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
        if scope["type"] != "http" or scope["path"] in SKIP_PATHS:
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
                # stdout 액세스 로그. 이 미들웨어는 RequestIDMiddleware 바깥(ASGI)에서
                # 응답을 내보내므로 contextvar 가 이미 비워져 있다 — request_id 는
                # request.state 에서 직접 읽어 붙인다. 본문/쿼리 값은 남기지 않고
                # 경로·메서드·상태·소요시간만 기록한다(PII 보호).
                emit = logger.warning if response_status >= 500 else logger.info
                emit(
                    "request_completed",
                    request_id=getattr(request.state, "request_id", None),
                    method=request.method,
                    path=request.url.path,
                    status=response_status,
                    duration_ms=pending_record["duration_ms"],
                )
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
    ip_addrs = extract_ip_addrs(
        headers, request.client.host if request.client else None
    )
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
        "body": (
            None
            if any(s in request.url.path for s in BODY_SKIP_SUBSTRINGS)
            else decode_body_bytes(
                request_body,
                content_type=headers.get("content-type"),
            )
        ),
        "response_code": response_status,
        "response_message": response_message,
        "error_code": error_code,
        "duration_ms": duration_ms,
        "user_agent": headers.get("user-agent"),
        "referrer": sanitize_referrer(first_header(headers, "referer", "referrer")),
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


def sanitize_referrer(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


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

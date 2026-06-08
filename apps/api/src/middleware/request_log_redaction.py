from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED_VALUE = "[REDACTED]"
TRUNCATED_MARKER = "[TRUNCATED]"
MAX_LOG_BODY_BYTES = 4096

SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "client_secret",
        "cookie",
        "id_token",
        "password",
        "refresh_token",
        "secret",
        "token",
        "x_api_key",
        # 상담 리드 PII (CMP-DIRECT) — 요청 로그 본문에 평문 저장 방지.
        "applicant_name",
        "applicant_phone",
        "message",
        "road_addr_part1",
        "road_addr_part2",
        "road_addr_detail",
        "expansion_location",
    }
)

SENSITIVE_HEADER_NAMES: frozenset[str] = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
    }
)


def is_sensitive_key(key: str) -> bool:
    normalized = key.replace("-", "_").lower()
    return normalized in SENSITIVE_KEYS or any(
        marker in normalized for marker in ("password", "secret", "token")
    )


def redact_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: REDACTED_VALUE if is_sensitive_key(key) else redact_value(value)
        for key, value in data.items()
    }


def redact_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return redact_mapping(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return [redact_value(item) for item in value]
    return value


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        key: REDACTED_VALUE if key.lower() in SENSITIVE_HEADER_NAMES else value
        for key, value in headers.items()
    }


def truncate_bytes(
    data: bytes, max_bytes: int = MAX_LOG_BODY_BYTES
) -> tuple[bytes, bool]:
    if len(data) <= max_bytes:
        return data, False
    return data[:max_bytes], True


def decode_body_bytes(
    data: bytes, *, content_type: str | None = None
) -> dict[str, Any] | None:
    if not data:
        return None

    truncated, was_truncated = truncate_bytes(data)
    normalized_content_type = (content_type or "").split(";", 1)[0].strip().lower()

    if normalized_content_type == "application/json":
        try:
            decoded: Any = json.loads(truncated.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            decoded = {
                "_unparsable": True,
                "_content_type": "application/json",
                "_bytes": len(data),
            }
    elif normalized_content_type.startswith("text/"):
        decoded = {
            "_content_type": normalized_content_type,
            "_bytes": len(data),
        }
    else:
        decoded = {
            "_content_type": normalized_content_type or "application/octet-stream",
            "_bytes": len(data),
        }

    if isinstance(decoded, Mapping):
        redacted = redact_mapping(decoded)
    elif isinstance(decoded, Sequence) and not isinstance(
        decoded, (str, bytes, bytearray)
    ):
        redacted = {"_json": redact_value(list(decoded))}
    else:
        redacted = {"_json": redact_value(decoded)}

    if was_truncated:
        redacted["_truncated"] = TRUNCATED_MARKER
        redacted["_original_bytes"] = len(data)
    return redacted

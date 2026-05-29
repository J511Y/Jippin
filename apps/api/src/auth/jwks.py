from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_GOOGLE_JWKS: dict[str, Any] | None = None
_GOOGLE_JWKS_EXPIRES_AT: datetime | None = None


async def get_google_jwks(http_client: httpx.AsyncClient) -> dict[str, Any]:
    global _GOOGLE_JWKS, _GOOGLE_JWKS_EXPIRES_AT
    now = datetime.now(UTC)
    if _GOOGLE_JWKS is not None and _GOOGLE_JWKS_EXPIRES_AT is not None:
        if _GOOGLE_JWKS_EXPIRES_AT > now:
            return _GOOGLE_JWKS

    response = await http_client.get(GOOGLE_JWKS_URL)
    response.raise_for_status()
    _GOOGLE_JWKS = response.json()
    _GOOGLE_JWKS_EXPIRES_AT = now + timedelta(hours=1)
    return _GOOGLE_JWKS


def clear_google_jwks_cache() -> None:
    global _GOOGLE_JWKS, _GOOGLE_JWKS_EXPIRES_AT
    _GOOGLE_JWKS = None
    _GOOGLE_JWKS_EXPIRES_AT = None


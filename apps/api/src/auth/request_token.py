"""Request-level Supabase access token verification (CMP-609).

`services.supabase_session.verify_supabase_access_token` is the conversion-only
verifier — it rejects Supabase Anonymous Sign-In tokens because the
``/auth/supabase/session`` bridge mints a backend session only for permanent
users. Phase A main-flow APIs (sessions/floorplans/chat) intentionally accept
both anonymous and non-anonymous Supabase tokens because the P0 product policy
is "비회원 사전검토 허용 via Supabase Anonymous Sign-In".

This module provides a sibling verifier and a FastAPI dependency that:

- Reuses the same JWKS-based RS256/ES256 verification path.
- Returns the Supabase ``sub`` (UUID) and ``is_anonymous`` flag verbatim.
- Does NOT call any backend ``public.users`` resolver. Phase A skeleton routes
  trust ``sub`` as the ownership key (matches the DB design note that
  ``sessions.user_id`` references ``auth.users.id``, not ``public.users``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import httpx
from fastapi import Request
from jose import ExpiredSignatureError, JWTError, jwt

from ..auth.jwks import get_supabase_jwks
from ..config import Settings, get_settings
from ..errors import ZippinException
from ..services.supabase_session import parse_bearer_token

_SUPPORTED_ALGORITHMS: tuple[str, ...] = ("RS256", "ES256")


@dataclass(frozen=True)
class RequestUser:
    """Phase A request-auth principal — Supabase ``sub`` plus anonymous flag."""

    user_id: uuid.UUID
    is_anonymous: bool


def _require_supabase_settings(settings: Settings) -> tuple[str, str, str]:
    if not settings.supabase_jwks_url or not settings.supabase_jwt_issuer:
        raise ZippinException(
            "Supabase request auth is not configured.",
            code="AUTH_SESSION_CONFIG_MISSING",
            http_status=503,
        )
    return (
        settings.supabase_jwks_url,
        settings.supabase_jwt_issuer,
        settings.supabase_jwt_audience,
    )


async def verify_supabase_request_token(
    access_token: str,
    *,
    http_client: httpx.AsyncClient,
    settings: Settings | None = None,
) -> RequestUser:
    """Verify a Supabase access token for request authentication.

    Unlike ``verify_supabase_access_token`` (conversion bridge), anonymous
    tokens are accepted — the caller is the Phase A main-flow router whose
    ownership key is ``auth.users.id`` regardless of anonymous/permanent.
    """

    settings = settings or get_settings()
    jwks_url, issuer, audience = _require_supabase_settings(settings)

    try:
        jwks = await get_supabase_jwks(http_client, jwks_url)
    except httpx.HTTPError as exc:
        raise ZippinException(
            "Could not fetch Supabase JWKS.",
            code="AUTH_SUPABASE_JWKS_UNAVAILABLE",
            http_status=503,
        ) from exc

    try:
        claims = jwt.decode(
            access_token,
            jwks,
            algorithms=list(_SUPPORTED_ALGORITHMS),
            audience=audience,
            issuer=issuer,
        )
    except ExpiredSignatureError as exc:
        raise ZippinException(
            "Supabase access token has expired.",
            code="AUTH_EXPIRED_TOKEN",
            http_status=401,
        ) from exc
    except JWTError as exc:
        raise ZippinException(
            "Supabase access token verification failed.",
            code="AUTH_INVALID_TOKEN",
            http_status=401,
        ) from exc

    subject = claims.get("sub")
    if not subject:
        raise ZippinException(
            "Supabase access token is missing the subject claim.",
            code="AUTH_INVALID_TOKEN",
            http_status=401,
        )
    try:
        user_id = uuid.UUID(str(subject))
    except ValueError as exc:
        raise ZippinException(
            "Supabase access token subject must be a UUID.",
            code="AUTH_INVALID_TOKEN",
            http_status=401,
        ) from exc

    return RequestUser(
        user_id=user_id,
        is_anonymous=claims.get("is_anonymous") is True,
    )


async def require_supabase_request_user(request: Request) -> RequestUser:
    """FastAPI dependency that resolves the Supabase request principal.

    Allows both Supabase anonymous and non-anonymous tokens. Use this for
    Phase A main-flow endpoints (sessions/addresses/floorplans/chat) and for
    consultation lead creation (``POST /leads``), which intentionally accepts
    anonymous submitters (CMP-DIRECT / ADR-0007; AGENTS §4.7 정정). Conversion
    endpoints that still require a permanent user (report share, payment, …)
    use the ``verify_supabase_access_token`` path instead — it rejects anonymous.
    """

    access_token = parse_bearer_token(request.headers.get("authorization"))
    async with httpx.AsyncClient(timeout=10.0) as http_client:
        principal = await verify_supabase_request_token(
            access_token,
            http_client=http_client,
        )
    # ``RequestLogMiddleware.extract_user_id`` 는 ``request.state.user`` 만 읽는다.
    # 인증된 Supabase principal 을 노출해 lead/Phase-A 요청이 request_logs 에
    # ``user_id=null`` 로 남지 않도록 한다(특히 PII 가 담긴 상담 리드 제출의 audit).
    request.state.user = {
        "id": str(principal.user_id),
        "is_anonymous": principal.is_anonymous,
    }
    return principal

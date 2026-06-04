from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response
from jose import ExpiredSignatureError, JWTError, jwt

from ..config import Settings, get_settings
from ..errors import ZippinException

SESSION_TOKEN_TYPE = "jippin_session"


@dataclass(frozen=True)
class SessionClaims:
    user_id: uuid.UUID
    pending_anonymous_user_id: uuid.UUID | None = None


def create_session_token(
    user_id: uuid.UUID,
    settings: Settings | None = None,
    *,
    pending_anonymous_user_id: uuid.UUID | None = None,
) -> str:
    settings = settings or get_settings()
    if not settings.auth_jwt_secret:
        raise ZippinException(
            "Session token signing secret is not configured.",
            code="AUTH_SESSION_CONFIG_MISSING",
            http_status=503,
        )
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=settings.auth_session_ttl_days)
    claims = {
        "sub": str(user_id),
        "typ": SESSION_TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    if pending_anonymous_user_id is not None:
        claims["pending_anonymous_user_id"] = str(pending_anonymous_user_id)
    return jwt.encode(
        claims,
        settings.auth_jwt_secret,
        algorithm=settings.auth_jwt_alg,
    )


def read_session_claims(
    request: Request,
    settings: Settings | None = None,
) -> SessionClaims:
    settings = settings or get_settings()
    token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        raise _unauthenticated()
    if not settings.auth_jwt_secret:
        raise ZippinException(
            "Session token signing secret is not configured.",
            code="AUTH_SESSION_CONFIG_MISSING",
            http_status=503,
        )
    try:
        payload = jwt.decode(
            token,
            settings.auth_jwt_secret,
            algorithms=[settings.auth_jwt_alg],
        )
    except (ExpiredSignatureError, JWTError) as exc:
        raise _unauthenticated() from exc

    if payload.get("typ") != SESSION_TOKEN_TYPE:
        raise _unauthenticated()
    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise _unauthenticated() from exc

    pending_anonymous_user_id = None
    if payload.get("pending_anonymous_user_id"):
        try:
            pending_anonymous_user_id = uuid.UUID(
                str(payload["pending_anonymous_user_id"])
            )
        except (TypeError, ValueError) as exc:
            raise _unauthenticated() from exc
    return SessionClaims(
        user_id=user_id,
        pending_anonymous_user_id=pending_anonymous_user_id,
    )


def set_session_cookie(
    response: Response,
    user_id: uuid.UUID,
    settings: Settings | None = None,
    *,
    pending_anonymous_user_id: uuid.UUID | None = None,
) -> None:
    settings = settings or get_settings()
    token = create_session_token(
        user_id,
        settings,
        pending_anonymous_user_id=pending_anonymous_user_id,
    )
    max_age = settings.auth_session_ttl_days * 24 * 60 * 60
    secure = (
        settings.app_env == "production"
        if settings.auth_cookie_secure is None
        else settings.auth_cookie_secure
    )
    response.set_cookie(
        settings.auth_cookie_name,
        token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        domain=settings.auth_cookie_domain,
    )


def clear_session_cookie(
    response: Response,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    response.delete_cookie(
        settings.auth_cookie_name,
        httponly=True,
        secure=(
            settings.app_env == "production"
            if settings.auth_cookie_secure is None
            else settings.auth_cookie_secure
        ),
        samesite="lax",
        domain=settings.auth_cookie_domain,
    )


def _unauthenticated() -> ZippinException:
    return ZippinException(
        "Authentication is required.",
        code="AUTH_UNAUTHENTICATED",
        http_status=401,
    )

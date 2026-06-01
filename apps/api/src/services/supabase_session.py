"""Supabase session bridge service.

Verifies a Supabase Auth access token (RS256/ES256 via Supabase JWKS) and
resolves the jippin user to mint a backend session cookie for. The link-writer
side (CMP-579 / CMP-583 link ladder) is responsible for populating
``auth_identities`` rows; this service is read-only and raises
``ZippinException`` for every off-happy-path branch so the router can convert
them into the canonical AGENTS.md §4.5 error envelope.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import httpx
import sqlalchemy as sa
from jose import ExpiredSignatureError, JWTError, jwt

from ..auth.jwks import get_supabase_jwks
from ..config import Settings, get_settings
from ..db import get_engine
from ..errors import ZippinException
from ..models import AuthIdentity, User

SUPABASE_PROVIDER = "supabase"
_SUPPORTED_ALGORITHMS: tuple[str, ...] = ("RS256", "ES256")


@dataclass(frozen=True)
class SupabaseBridgeResult:
    user_id: uuid.UUID


def parse_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise ZippinException(
            "Supabase bearer token is required.",
            code="SUPABASE_SESSION_BEARER_REQUIRED",
            http_status=401,
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ZippinException(
            "Supabase bearer token is required.",
            code="SUPABASE_SESSION_BEARER_REQUIRED",
            http_status=401,
        )
    return token.strip()


def _require_settings(settings: Settings) -> tuple[str, str, str]:
    if not settings.supabase_jwks_url or not settings.supabase_jwt_issuer:
        raise ZippinException(
            "Supabase bridge is not configured.",
            code="AUTH_SESSION_CONFIG_MISSING",
            http_status=503,
        )
    if not settings.auth_jwt_secret:
        raise ZippinException(
            "Session token signing secret is not configured.",
            code="AUTH_SESSION_CONFIG_MISSING",
            http_status=503,
        )
    return (
        settings.supabase_jwks_url,
        settings.supabase_jwt_issuer,
        settings.supabase_jwt_audience,
    )


async def verify_supabase_access_token(
    access_token: str,
    *,
    http_client: httpx.AsyncClient,
    settings: Settings | None = None,
) -> dict[str, object]:
    settings = settings or get_settings()
    jwks_url, issuer, audience = _require_settings(settings)

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
        raise _expired_token() from exc
    except JWTError as exc:
        raise _invalid_token("Supabase access token verification failed.") from exc

    if not claims.get("sub"):
        raise _invalid_token("Supabase access token is missing the subject claim.")
    if _is_anonymous_supabase_claims(claims):
        raise ZippinException(
            "Supabase anonymous access tokens cannot mint backend sessions.",
            code="AUTH_ANONYMOUS_TOKEN_NOT_ALLOWED",
            http_status=401,
        )
    return claims


async def resolve_jippin_user_for_supabase(
    *,
    supabase_subject: str,
    email_claim: str | None,
) -> SupabaseBridgeResult:
    async with get_engine().connect() as conn:
        row = await conn.execute(
            sa.select(AuthIdentity.user_id)
            .join(User, User.id == AuthIdentity.user_id)
            .where(
                AuthIdentity.provider == SUPABASE_PROVIDER,
                AuthIdentity.external_id == supabase_subject,
                User.status == "active",
            )
        )
        user_id = row.scalar_one_or_none()
        if user_id is not None:
            return SupabaseBridgeResult(user_id=user_id)

        if email_claim:
            normalized_email = email_claim.strip().lower()
            email_row = await conn.execute(
                sa.select(User.id)
                .where(
                    User.email.is_not(None),
                    User.status == "active",
                    sa.func.lower(User.email) == normalized_email,
                )
                .limit(1)
            )
            if email_row.scalar_one_or_none() is not None:
                raise ZippinException(
                    "Supabase identity is not linked to a jippin account.",
                    code="AUTH_IDENTITY_NOT_LINKED",
                    http_status=401,
                )

    raise ZippinException(
        "No jippin account exists for this Supabase identity. Sign up first.",
        code="AUTH_SIGNUP_REQUIRED",
        http_status=401,
    )


def _is_anonymous_supabase_claims(claims: dict[str, object]) -> bool:
    return claims.get("is_anonymous") is True


def _invalid_token(message: str) -> ZippinException:
    return ZippinException(
        message,
        code="AUTH_INVALID_TOKEN",
        http_status=401,
    )


def _expired_token() -> ZippinException:
    return ZippinException(
        "Supabase access token has expired.",
        code="AUTH_EXPIRED_TOKEN",
        http_status=401,
    )

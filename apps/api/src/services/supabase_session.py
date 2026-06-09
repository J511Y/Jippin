"""Supabase session bridge service.

Verifies a Supabase Auth access token (RS256/ES256 via Supabase JWKS) and
resolves it directly to the Jippin application profile keyed by
``auth.users.id``. CMP-604 removed the legacy ``auth_identities`` bridge table;
Supabase Auth is the identity SSOT and ``public.users`` is only a profile table.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import httpx
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from jose import ExpiredSignatureError, JWTError, jwt

from ..auth.jwks import get_supabase_jwks
from ..config import Settings, get_settings
from ..db import get_engine
from ..errors import ZippinException
from ..models import User

_SUPPORTED_ALGORITHMS: tuple[str, ...] = ("RS256", "ES256")
# 'email' = 자체 이메일/비밀번호 로그인(CMP-DIRECT). Supabase 가 이메일 로그인 토큰의
# app_metadata.provider 를 'email' 로 발급한다. 가입 시 내부 약관 동의(internal_signup)를
# 이미 기록하므로 별도 Kakao Sync 분기 없이 일반 약관 컨텍스트로 처리한다.
_ALLOWED_SUPABASE_UI_PROVIDERS: frozenset[str] = frozenset({"kakao", "email"})
_PROVIDER_ALIASES: dict[str, str] = {
    "custom:kakao": "kakao",
    "custom:naver": "naver",
}


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


def validate_supabase_provider_claims(
    *,
    claims: dict[str, object],
    requested_provider: str | None,
) -> None:
    if requested_provider is None:
        raise ZippinException(
            "Signed OAuth provider context is required.",
            code="AUTH_PROVIDER_REQUIRED",
            http_status=401,
        )
    if requested_provider not in _ALLOWED_SUPABASE_UI_PROVIDERS:
        raise ZippinException(
            "This Supabase provider is not enabled for Jippin sign-in.",
            code="AUTH_PROVIDER_NOT_ALLOWED",
            http_status=403,
        )

    token_providers = _supabase_token_providers(claims)
    if requested_provider not in token_providers:
        raise ZippinException(
            "Supabase token provider does not match the requested OAuth provider.",
            code="AUTH_PROVIDER_MISMATCH",
            http_status=401,
        )


async def resolve_jippin_user_for_supabase(
    *,
    supabase_subject: str,
    email_claim: str | None,  # noqa: ARG001 - email is not stored in public.users.
) -> SupabaseBridgeResult:
    try:
        supabase_user_id = uuid.UUID(supabase_subject)
    except ValueError as exc:
        raise _invalid_token("Supabase access token subject must be a UUID.") from exc

    async with get_engine().begin() as conn:
        await conn.execute(
            pg_insert(User)
            .values(id=supabase_user_id)
            .on_conflict_do_nothing(index_elements=[User.id])
        )
        row = await conn.execute(
            sa.select(User.id).where(
                User.id == supabase_user_id,
                User.status == "active",
            )
        )
        user_id = row.scalar_one_or_none()
        if user_id is not None:
            return SupabaseBridgeResult(user_id=user_id)

    raise ZippinException(
        "No active Jippin profile exists for this Supabase user.",
        code="AUTH_SIGNUP_REQUIRED",
        http_status=401,
    )


def _is_anonymous_supabase_claims(claims: dict[str, object]) -> bool:
    return claims.get("is_anonymous") is True


def _supabase_token_providers(claims: dict[str, object]) -> set[str]:
    providers: set[str] = set()
    app_metadata = claims.get("app_metadata")
    if isinstance(app_metadata, dict):
        providers.update(_provider_values(app_metadata.get("provider")))
        providers.update(_provider_values(app_metadata.get("providers")))
    providers.update(_provider_values(claims.get("provider")))
    providers.update(_provider_values(claims.get("providers")))
    return providers


def _provider_values(value: object) -> set[str]:
    if isinstance(value, str):
        normalized = _normalize_provider(value)
        return {normalized} if normalized else set()
    if isinstance(value, list):
        values: set[str] = set()
        for item in value:
            if isinstance(item, str):
                normalized = _normalize_provider(item)
                if normalized:
                    values.add(normalized)
        return values
    return set()


def _normalize_provider(value: str) -> str | None:
    provider = value.strip().lower()
    if not provider:
        return None
    return _PROVIDER_ALIASES.get(provider, provider)


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

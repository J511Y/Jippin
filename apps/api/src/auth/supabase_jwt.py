from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import httpx
from jose import ExpiredSignatureError, JWTError, jwt

from ..errors import ZippinException

DEFAULT_SUPABASE_JWT_AUDIENCE = "authenticated"
DEFAULT_SUPABASE_JWT_ALGORITHMS = ("RS256", "ES256")


@dataclass(frozen=True)
class SupabaseJwtConfig:
    project_url: str
    audience: str = DEFAULT_SUPABASE_JWT_AUDIENCE
    algorithms: Sequence[str] = DEFAULT_SUPABASE_JWT_ALGORITHMS

    @property
    def issuer(self) -> str:
        return f"{self.project_url.rstrip('/')}/auth/v1"

    @property
    def jwks_url(self) -> str:
        return f"{self.issuer}/.well-known/jwks.json"


@dataclass(frozen=True)
class SupabaseJwtClaims:
    user_id: uuid.UUID
    role: str
    is_anonymous: bool
    email: str | None
    session_id: str | None
    raw: Mapping[str, Any]


class SupabaseJwtVerifier:
    """PoC adapter for FastAPI-side Supabase Auth access-token validation."""

    def __init__(self, config: SupabaseJwtConfig) -> None:
        self._config = config

    async def fetch_jwks(self, http_client: httpx.AsyncClient) -> dict[str, Any]:
        response = await http_client.get(self._config.jwks_url)
        response.raise_for_status()
        return response.json()

    async def verify(
        self,
        token: str,
        *,
        http_client: httpx.AsyncClient,
    ) -> SupabaseJwtClaims:
        jwks = await self.fetch_jwks(http_client)
        try:
            payload = jwt.decode(
                token,
                jwks,
                algorithms=list(self._config.algorithms),
                audience=self._config.audience,
            )
        except ExpiredSignatureError as exc:
            raise ZippinException(
                "Supabase access token has expired.",
                code="TOKEN_EXPIRED",
                http_status=401,
            ) from exc
        except JWTError as exc:
            raise ZippinException(
                "Supabase access token is invalid.",
                code="TOKEN_INVALID",
                http_status=401,
            ) from exc

        if payload.get("iss") != self._config.issuer:
            raise ZippinException(
                "Supabase access token issuer is invalid.",
                code="TOKEN_INVALID",
                http_status=401,
            )
        try:
            user_id = uuid.UUID(str(payload["sub"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ZippinException(
                "Supabase access token subject is invalid.",
                code="TOKEN_INVALID",
                http_status=401,
            ) from exc

        is_anonymous = payload.get("is_anonymous")
        if not isinstance(is_anonymous, bool):
            raise ZippinException(
                "Supabase access token is missing is_anonymous.",
                code="TOKEN_INVALID",
                http_status=401,
            )

        role = payload.get("role")
        if role != "authenticated":
            raise ZippinException(
                "Supabase access token role is invalid.",
                code="TOKEN_INVALID",
                http_status=401,
            )

        return SupabaseJwtClaims(
            user_id=user_id,
            role=role,
            is_anonymous=is_anonymous,
            email=payload.get("email"),
            session_id=payload.get("session_id"),
            raw=payload,
        )

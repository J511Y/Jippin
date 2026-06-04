"""Shared Supabase JWKS / token helpers for Phase A skeleton tests (CMP-609).

Pytest does not auto-collect modules whose name begins with ``_``. This file
exists so each Phase A test module can mint RS256-signed Supabase tokens (both
anonymous and non-anonymous) and patch the JWKS fetch on the request-auth
dependency.
"""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt

ISSUER = "https://example-project.supabase.co/auth/v1"
AUDIENCE = "authenticated"
JWKS_URL = "https://example-project.supabase.co/auth/v1/.well-known/jwks.json"

_KAKAO_APP_METADATA = {"provider": "kakao", "providers": ["kakao"]}
_ANON_APP_METADATA = {"provider": "anonymous", "providers": ["anonymous"]}


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def rsa_keypair() -> tuple[str, dict[str, Any]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_numbers = private_key.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "kid": "test-key-1",
        "alg": "RS256",
        "use": "sig",
        "n": _b64url_uint(public_numbers.n),
        "e": _b64url_uint(public_numbers.e),
    }
    return pem, jwk


def mint_token(
    private_pem: str,
    kid: str,
    *,
    sub: str | None = None,
    is_anonymous: bool = False,
    expires_in: timedelta = timedelta(hours=1),
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, uuid.UUID]:
    """Return ``(token, subject_uuid)``.

    Anonymous tokens get the same shape as Supabase Anonymous Sign-In: a real
    UUID ``sub`` plus ``is_anonymous: true`` and ``app_metadata.providers=
    ['anonymous']``.
    """

    subject = uuid.UUID(sub) if sub else uuid.uuid4()
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": str(subject),
        "aud": AUDIENCE,
        "iss": ISSUER,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_in).timestamp()),
        "role": "authenticated",
    }
    if is_anonymous:
        claims["is_anonymous"] = True
        claims["app_metadata"] = dict(_ANON_APP_METADATA)
    else:
        claims["app_metadata"] = dict(_KAKAO_APP_METADATA)
    if extra_claims:
        claims.update(extra_claims)
    token = jwt.encode(
        claims,
        private_pem,
        algorithm="RS256",
        headers={"kid": kid},
    )
    return token, subject


def install_jwks(monkeypatch, jwks: dict[str, Any]) -> None:
    """Patch the JWKS fetch on the Phase A request-auth dependency."""

    async def fake_get_supabase_jwks(http_client, jwks_url):  # noqa: ARG001
        assert jwks_url == JWKS_URL
        return jwks

    # Phase A 라우터는 ``src.auth.request_token.get_supabase_jwks`` 만 사용한다.
    monkeypatch.setattr(
        "src.auth.request_token.get_supabase_jwks",
        fake_get_supabase_jwks,
    )


def set_supabase_env(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_JWT_ISSUER", ISSUER)
    monkeypatch.setenv("SUPABASE_JWKS_URL", JWKS_URL)
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-session-secret")

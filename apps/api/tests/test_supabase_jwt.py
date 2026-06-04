from __future__ import annotations

import uuid

import httpx
import pytest

from src.auth import supabase_jwt
from src.auth.supabase_jwt import SupabaseJwtConfig, SupabaseJwtVerifier
from src.errors import ZippinException


def test_supabase_jwt_config_derives_issuer_and_jwks_url():
    config = SupabaseJwtConfig("https://project-ref.supabase.co/")

    assert config.issuer == "https://project-ref.supabase.co/auth/v1"
    assert (
        config.jwks_url
        == "https://project-ref.supabase.co/auth/v1/.well-known/jwks.json"
    )


@pytest.mark.asyncio
async def test_supabase_jwt_verifier_fetches_jwks_and_maps_claims(monkeypatch):
    user_id = uuid.uuid4()
    config = SupabaseJwtConfig("https://project-ref.supabase.co")

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == config.jwks_url
        return httpx.Response(200, json={"keys": [{"kid": "test-key"}]})

    def fake_decode(token, key, *, algorithms, audience):
        assert token == "supabase-access-token"
        assert key == {"keys": [{"kid": "test-key"}]}
        assert algorithms == ["RS256", "ES256"]
        assert audience == "authenticated"
        return {
            "iss": config.issuer,
            "aud": "authenticated",
            "sub": str(user_id),
            "role": "authenticated",
            "email": "user@example.com",
            "session_id": "session-id",
            "is_anonymous": True,
        }

    monkeypatch.setattr(supabase_jwt.jwt, "decode", fake_decode)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        claims = await SupabaseJwtVerifier(config).verify(
            "supabase-access-token",
            http_client=client,
        )

    assert claims.user_id == user_id
    assert claims.role == "authenticated"
    assert claims.is_anonymous is True
    assert claims.email == "user@example.com"
    assert claims.session_id == "session-id"


@pytest.mark.asyncio
async def test_supabase_jwt_verifier_rejects_issuer_mismatch(monkeypatch):
    config = SupabaseJwtConfig("https://project-ref.supabase.co")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": []})

    def fake_decode(token, key, *, algorithms, audience):
        return {
            "iss": "https://other-project.supabase.co/auth/v1",
            "sub": str(uuid.uuid4()),
            "role": "authenticated",
            "is_anonymous": False,
        }

    monkeypatch.setattr(supabase_jwt.jwt, "decode", fake_decode)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ZippinException) as exc_info:
            await SupabaseJwtVerifier(config).verify("token", http_client=client)

    assert exc_info.value.code == "TOKEN_INVALID"


@pytest.mark.asyncio
async def test_supabase_jwt_verifier_requires_is_anonymous_claim(monkeypatch):
    config = SupabaseJwtConfig("https://project-ref.supabase.co")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": []})

    def fake_decode(token, key, *, algorithms, audience):
        return {
            "iss": config.issuer,
            "sub": str(uuid.uuid4()),
            "role": "authenticated",
        }

    monkeypatch.setattr(supabase_jwt.jwt, "decode", fake_decode)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ZippinException) as exc_info:
            await SupabaseJwtVerifier(config).verify("token", http_client=client)

    assert exc_info.value.code == "TOKEN_INVALID"

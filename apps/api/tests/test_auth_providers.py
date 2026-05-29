from __future__ import annotations

import httpx
import pytest

from src.auth.providers import google, kakao, naver
from src.auth.providers.base import OAuthProviderError
from src.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def provider_env(monkeypatch):
    values = {
        "KAKAO_REST_API_KEY": "kakao-client",
        "KAKAO_CLIENT_SECRET": "kakao-secret",
        "KAKAO_REDIRECT_URI": "http://localhost:8000/auth/callback/kakao",
        "GOOGLE_OAUTH_CLIENT_ID": "google-client",
        "GOOGLE_OAUTH_CLIENT_SECRET": "google-secret",
        "GOOGLE_OAUTH_REDIRECT_URI": "http://localhost:8000/auth/callback/google",
        "NAVER_OAUTH_CLIENT_ID": "naver-client",
        "NAVER_OAUTH_CLIENT_SECRET": "naver-secret",
        "NAVER_OAUTH_REDIRECT_URI": "http://localhost:8000/auth/callback/naver",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_kakao_adapter_exchanges_code_and_parses_userinfo(provider_env):
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == kakao.TOKEN_ENDPOINT:
            assert b"code=oauth-code" in request.content
            return httpx.Response(200, json={"access_token": "kakao-access"})
        if str(request.url) == kakao.USERINFO_ENDPOINT:
            assert request.headers["authorization"] == "Bearer kakao-access"
            return httpx.Response(
                200,
                json={
                    "id": 12345,
                    "kakao_account": {
                        "email": "kakao@example.com",
                        "profile": {
                            "nickname": "Kakao User",
                            "profile_image_url": "https://cdn.example/kakao.png",
                        },
                    },
                    "agreed_terms_tags": ["service_terms", "privacy_policy"],
                },
            )
        raise AssertionError(f"Unexpected URL: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tokens = await kakao.exchange_code(
            "oauth-code", http_client=client, settings=get_settings()
        )
        profile = await kakao.fetch_userinfo(
            tokens, http_client=client, settings=get_settings()
        )

    assert tokens.access_token == "kakao-access"
    assert profile.provider_subject == "12345"
    assert profile.email == "kakao@example.com"
    assert profile.agreed_terms_tags == ("service_terms", "privacy_policy")


@pytest.mark.asyncio
async def test_naver_adapter_exchanges_code_and_parses_userinfo(provider_env):
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == naver.TOKEN_ENDPOINT:
            assert b"code=oauth-code" in request.content
            return httpx.Response(200, json={"access_token": "naver-access"})
        if str(request.url) == naver.USERINFO_ENDPOINT:
            assert request.headers["authorization"] == "Bearer naver-access"
            return httpx.Response(
                200,
                json={
                    "response": {
                        "id": "naver-subject",
                        "email": "naver@example.com",
                        "name": "Naver User",
                        "profile_image": "https://cdn.example/naver.png",
                    }
                },
            )
        raise AssertionError(f"Unexpected URL: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tokens = await naver.exchange_code(
            "oauth-code", http_client=client, settings=get_settings()
        )
        profile = await naver.fetch_userinfo(
            tokens, http_client=client, settings=get_settings()
        )

    assert tokens.access_token == "naver-access"
    assert profile.provider_subject == "naver-subject"
    assert profile.email == "naver@example.com"


@pytest.mark.asyncio
async def test_google_adapter_exchanges_code_verifies_id_token_and_parses_userinfo(
    monkeypatch,
    provider_env,
):
    async def fake_verify_id_token(id_token, *, http_client, audience, expected_nonce):
        assert id_token == "google-id-token"
        assert audience == "google-client"
        assert expected_nonce == "nonce-value"
        return {
            "sub": "google-subject",
            "email": "id-token@example.com",
            "nonce": "nonce-value",
        }

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == google.TOKEN_ENDPOINT:
            assert b"code=oauth-code" in request.content
            return httpx.Response(
                200,
                json={
                    "access_token": "google-access",
                    "id_token": "google-id-token",
                },
            )
        if str(request.url) == google.USERINFO_ENDPOINT:
            assert request.headers["authorization"] == "Bearer google-access"
            return httpx.Response(
                200,
                json={
                    "sub": "google-subject",
                    "email": "google@example.com",
                    "name": "Google User",
                    "picture": "https://cdn.example/google.png",
                },
            )
        raise AssertionError(f"Unexpected URL: {request.url}")

    monkeypatch.setattr(google, "verify_id_token", fake_verify_id_token)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tokens = await google.exchange_code(
            "oauth-code", http_client=client, settings=get_settings()
        )
        profile = await google.fetch_userinfo(
            tokens,
            http_client=client,
            settings=get_settings(),
            expected_nonce="nonce-value",
        )

    assert tokens.access_token == "google-access"
    assert profile.provider_subject == "google-subject"
    assert profile.email == "google@example.com"


@pytest.mark.asyncio
async def test_google_id_token_rejects_nonce_mismatch(monkeypatch, provider_env):
    async def fake_get_google_jwks(http_client):
        del http_client
        return {"keys": []}

    def fake_decode(id_token, key, *, algorithms, audience):
        assert id_token == "google-id-token"
        assert key == {"keys": []}
        assert algorithms == ["RS256"]
        assert audience == "google-client"
        return {
            "iss": "https://accounts.google.com",
            "sub": "google-subject",
            "nonce": "different-nonce",
        }

    monkeypatch.setattr(google, "get_google_jwks", fake_get_google_jwks)
    monkeypatch.setattr(google.jwt, "decode", fake_decode)

    async with httpx.AsyncClient() as client:
        with pytest.raises(OAuthProviderError, match="nonce"):
            await google.verify_id_token(
                "google-id-token",
                http_client=client,
                audience="google-client",
                expected_nonce="expected-nonce",
            )

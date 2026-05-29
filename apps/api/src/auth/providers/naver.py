from __future__ import annotations

from urllib.parse import urlencode

import httpx

from ...config import Settings
from .base import OAuthProviderError, OAuthTokens, ProviderProfile

AUTHORIZATION_ENDPOINT = "https://nid.naver.com/oauth2.0/authorize"
TOKEN_ENDPOINT = "https://nid.naver.com/oauth2.0/token"
USERINFO_ENDPOINT = "https://openapi.naver.com/v1/nid/me"
DEFAULT_SCOPES: tuple[str, ...] = ("name", "email", "profile_image")


def build_authorization_url(
    client_id: str,
    redirect_uri: str,
    state: str,
    nonce: str,
    scope: tuple[str, ...] | list[str] | str | None = None,
) -> str:
    scopes = scope if scope is not None else DEFAULT_SCOPES
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes) if not isinstance(scopes, str) else scopes,
        "state": state,
        "nonce": nonce,
    }
    return f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"


async def exchange_code(
    code: str,
    *,
    http_client: httpx.AsyncClient,
    settings: Settings,
) -> OAuthTokens:
    if (
        not settings.naver_oauth_client_id
        or not settings.naver_oauth_client_secret
        or not settings.naver_oauth_redirect_uri
    ):
        raise OAuthProviderError("Naver OAuth provider is not configured.")
    response = await http_client.post(
        TOKEN_ENDPOINT,
        data={
            "grant_type": "authorization_code",
            "client_id": settings.naver_oauth_client_id,
            "client_secret": settings.naver_oauth_client_secret,
            "redirect_uri": settings.naver_oauth_redirect_uri,
            "code": code,
        },
    )
    if response.status_code >= 400:
        raise OAuthProviderError("Naver token exchange failed.")
    payload = response.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise OAuthProviderError("Naver token response did not include access_token.")
    return OAuthTokens(
        access_token=access_token,
        token_type=payload.get("token_type"),
        refresh_token=payload.get("refresh_token"),
        expires_in=payload.get("expires_in"),
    )


async def fetch_userinfo(
    tokens: OAuthTokens,
    *,
    http_client: httpx.AsyncClient,
    settings: Settings,
) -> ProviderProfile:
    del settings
    response = await http_client.get(
        USERINFO_ENDPOINT,
        headers={"Authorization": f"Bearer {tokens.access_token}"},
    )
    if response.status_code >= 400:
        raise OAuthProviderError("Naver userinfo request failed.")
    payload = response.json()
    profile = payload.get("response") or {}
    subject = profile.get("id")
    if not subject:
        raise OAuthProviderError("Naver userinfo response did not include response.id.")
    return ProviderProfile(
        provider_subject=str(subject),
        email=profile.get("email"),
        display_name=profile.get("name") or profile.get("nickname"),
        profile_image_url=profile.get("profile_image"),
    )

from __future__ import annotations

from urllib.parse import urlencode

import httpx

from ...config import Settings
from .base import OAuthProviderError, OAuthTokens, ProviderProfile

AUTHORIZATION_ENDPOINT = "https://kauth.kakao.com/oauth/authorize"
TOKEN_ENDPOINT = "https://kauth.kakao.com/oauth/token"
USERINFO_ENDPOINT = "https://kapi.kakao.com/v2/user/me"
# Kakao Sync consent item IDs are finalized after the tenant app is approved.
# Keep common Kakao profile/email scopes here as a placeholder for CMP-561.
DEFAULT_SCOPES: tuple[str, ...] = (
    "profile_nickname",
    "profile_image",
    "account_email",
)


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
    if not settings.kakao_rest_api_key or not settings.kakao_redirect_uri:
        raise OAuthProviderError("Kakao OAuth provider is not configured.")
    data = {
        "grant_type": "authorization_code",
        "client_id": settings.kakao_rest_api_key,
        "redirect_uri": settings.kakao_redirect_uri,
        "code": code,
    }
    if settings.kakao_client_secret:
        data["client_secret"] = settings.kakao_client_secret

    response = await http_client.post(TOKEN_ENDPOINT, data=data)
    if response.status_code >= 400:
        raise OAuthProviderError("Kakao token exchange failed.")
    payload = response.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise OAuthProviderError("Kakao token response did not include access_token.")
    return OAuthTokens(
        access_token=access_token,
        token_type=payload.get("token_type"),
        refresh_token=payload.get("refresh_token"),
        expires_in=payload.get("expires_in"),
        id_token=payload.get("id_token"),
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
        raise OAuthProviderError("Kakao userinfo request failed.")
    payload = response.json()
    subject = payload.get("id")
    if subject is None:
        raise OAuthProviderError("Kakao userinfo response did not include id.")

    kakao_account = payload.get("kakao_account") or {}
    profile = kakao_account.get("profile") or {}
    agreed_terms_tags = payload.get("agreed_terms_tags") or []
    return ProviderProfile(
        provider_subject=str(subject),
        email=kakao_account.get("email"),
        display_name=profile.get("nickname"),
        profile_image_url=profile.get("profile_image_url")
        or profile.get("thumbnail_image_url"),
        agreed_terms_tags=tuple(str(tag) for tag in agreed_terms_tags),
    )

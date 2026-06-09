from __future__ import annotations

from urllib.parse import urlencode

import httpx

from ...config import Settings
from ...logging import log_http_call
from .base import OAuthProviderError, OAuthTokens, ProviderProfile

AUTHORIZATION_ENDPOINT = "https://nid.naver.com/oauth2.0/authorize"
TOKEN_ENDPOINT = "https://nid.naver.com/oauth2.0/token"
USERINFO_ENDPOINT = "https://openapi.naver.com/v1/nid/me"

# CMP-584 round-4/5 봉인: Naver 공식 OAuth 2.0 가이드는 authorize 요청에
# `client_id` / `response_type` / `redirect_uri` / `state` 만 명시한다 — `scope`
# 파라미터는 정식 사양에 없으며, 사용자에게 보여줄 권한 범위는 Naver Developers
# 콘솔의 "동의 항목" UI 에서 별도 선언한다. 임의 토큰 (`account` / `name` /
# `email` / `profile_image` 등) 을 scope 로 보내면 Naver 가 `invalid_request`
# 로 거부할 수 있으므로 default 는 빈 튜플로 유지하고, build_authorization_url
# 이 scope 값이 비어 있으면 query string 에서 scope 파라미터 자체를 omit 한다.
# 명시 scope 가 정말 필요한 환경에서만 caller 가 `scope=` 인자로 검증된 토큰을 전달.
DEFAULT_SCOPES: tuple[str, ...] = ()


def build_authorization_url(
    client_id: str,
    redirect_uri: str,
    state: str,
    nonce: str,
    scope: tuple[str, ...] | list[str] | str | None = None,
) -> str:
    scopes = scope if scope is not None else DEFAULT_SCOPES
    params: dict[str, str] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
        "nonce": nonce,
    }
    scope_value = " ".join(scopes) if not isinstance(scopes, str) else scopes
    if scope_value:
        params["scope"] = scope_value
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
    response = await log_http_call(
        "naver",
        "exchange_code",
        lambda: http_client.post(
            TOKEN_ENDPOINT,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.naver_oauth_client_id,
                "client_secret": settings.naver_oauth_client_secret,
                "redirect_uri": settings.naver_oauth_redirect_uri,
                "code": code,
            },
        ),
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
    response = await log_http_call(
        "naver",
        "fetch_userinfo",
        lambda: http_client.get(
            USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {tokens.access_token}"},
        ),
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

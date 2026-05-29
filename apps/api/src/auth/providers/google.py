from __future__ import annotations

from urllib.parse import urlencode

import httpx
from jose import JWTError, jwt

from ...auth.jwks import get_google_jwks
from ...config import Settings
from .base import OAuthProviderError, OAuthTokens, ProviderProfile

AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
ALLOWED_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}
DEFAULT_SCOPES: tuple[str, ...] = ("openid", "email", "profile")


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
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"


async def exchange_code(
    code: str,
    *,
    http_client: httpx.AsyncClient,
    settings: Settings,
) -> OAuthTokens:
    if (
        not settings.google_oauth_client_id
        or not settings.google_oauth_client_secret
        or not settings.google_oauth_redirect_uri
    ):
        raise OAuthProviderError("Google OAuth provider is not configured.")
    response = await http_client.post(
        TOKEN_ENDPOINT,
        data={
            "grant_type": "authorization_code",
            "client_id": settings.google_oauth_client_id,
            "client_secret": settings.google_oauth_client_secret,
            "redirect_uri": settings.google_oauth_redirect_uri,
            "code": code,
        },
    )
    if response.status_code >= 400:
        raise OAuthProviderError("Google token exchange failed.")
    payload = response.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise OAuthProviderError("Google token response did not include access_token.")
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
    expected_nonce: str | None = None,
) -> ProviderProfile:
    id_claims = await verify_id_token(
        tokens.id_token,
        http_client=http_client,
        audience=settings.google_oauth_client_id,
        expected_nonce=expected_nonce,
    )
    response = await http_client.get(
        USERINFO_ENDPOINT,
        headers={"Authorization": f"Bearer {tokens.access_token}"},
    )
    if response.status_code >= 400:
        raise OAuthProviderError("Google userinfo request failed.")
    profile = response.json()
    if profile.get("sub") and profile["sub"] != id_claims["sub"]:
        raise OAuthProviderError("Google ID token and userinfo subject mismatch.")
    return ProviderProfile(
        provider_subject=str(id_claims["sub"]),
        email=profile.get("email") or id_claims.get("email"),
        display_name=profile.get("name") or id_claims.get("name"),
        profile_image_url=profile.get("picture") or id_claims.get("picture"),
    )


async def verify_id_token(
    id_token: str | None,
    *,
    http_client: httpx.AsyncClient,
    audience: str | None,
    expected_nonce: str | None = None,
) -> dict[str, object]:
    if not id_token:
        raise OAuthProviderError("Google token response did not include id_token.")
    if not audience:
        raise OAuthProviderError("Google OAuth audience is not configured.")
    try:
        claims = jwt.decode(
            id_token,
            await get_google_jwks(http_client),
            algorithms=["RS256"],
            audience=audience,
        )
    except JWTError as exc:
        raise OAuthProviderError("Google ID token verification failed.") from exc
    if claims.get("iss") not in ALLOWED_ISSUERS:
        raise OAuthProviderError("Google ID token issuer is invalid.")
    if not claims.get("sub"):
        raise OAuthProviderError("Google ID token subject is missing.")
    if expected_nonce is not None and claims.get("nonce") != expected_nonce:
        raise OAuthProviderError("Google ID token nonce is invalid.")
    return claims

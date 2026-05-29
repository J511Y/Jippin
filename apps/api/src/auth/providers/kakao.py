from __future__ import annotations

from urllib.parse import urlencode

AUTHORIZATION_ENDPOINT = "https://kauth.kakao.com/oauth/authorize"
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

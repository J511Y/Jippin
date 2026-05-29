from __future__ import annotations

from urllib.parse import urlencode

AUTHORIZATION_ENDPOINT = "https://nid.naver.com/oauth2.0/authorize"
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

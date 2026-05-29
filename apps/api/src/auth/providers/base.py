from __future__ import annotations

from dataclasses import dataclass

from ...errors import ZippinException


class OAuthProviderError(ZippinException):
    code = "OAUTH_PROVIDER_FAILED"
    http_status = 502


@dataclass(frozen=True)
class OAuthTokens:
    access_token: str
    token_type: str | None = None
    refresh_token: str | None = None
    expires_in: int | None = None
    id_token: str | None = None


@dataclass(frozen=True)
class ProviderProfile:
    provider_subject: str
    email: str | None = None
    display_name: str | None = None
    profile_image_url: str | None = None
    agreed_terms_tags: tuple[str, ...] = ()


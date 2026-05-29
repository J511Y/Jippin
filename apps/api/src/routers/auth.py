from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse

from ..auth.providers import PROVIDER_MODULES, OAuthProvider
from ..auth.state_store import OAuthStatePayload, get_oauth_state_store
from ..config import Settings, get_settings
from ..errors import ZippinException
from ..logging import get_logger
from ..schemas.auth import (
    AnonymousUserCreateRequest,
    AnonymousUserCreateResponse,
    OAuthStartResponse,
)
from ..services.auth import (
    create_or_reuse_anonymous_user,
    parse_existing_anonymous_user_id,
)

logger = get_logger("zippin.auth")
router = APIRouter(prefix="/auth", tags=["auth"])


@dataclass(frozen=True)
class _OAuthProviderSettings:
    client_id: str | None
    redirect_uri: str | None


def _provider_settings(
    provider: OAuthProvider, settings: Settings
) -> _OAuthProviderSettings:
    match provider:
        case OAuthProvider.KAKAO:
            return _OAuthProviderSettings(
                settings.kakao_rest_api_key,
                settings.kakao_redirect_uri,
            )
        case OAuthProvider.NAVER:
            return _OAuthProviderSettings(
                settings.naver_oauth_client_id,
                settings.naver_oauth_redirect_uri,
            )
        case OAuthProvider.GOOGLE:
            return _OAuthProviderSettings(
                settings.google_oauth_client_id,
                settings.google_oauth_redirect_uri,
            )


def _origin(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ZippinException(
            "return_url must be an absolute http(s) URL.",
            code="RETURN_URL_NOT_ALLOWED",
            http_status=400,
        )
    return f"{parsed.scheme}://{parsed.netloc}"


def _allowed_return_url_origins(settings: Settings) -> set[str]:
    urls = [
        settings.frontend_auth_success_url,
        settings.frontend_auth_failure_url,
        settings.kakao_redirect_uri,
        settings.google_oauth_redirect_uri,
        settings.naver_oauth_redirect_uri,
    ]
    urls.extend(origin for origin in settings.cors_allow_origins if origin != "*")
    return {_origin(url) for url in urls if url}


def _validate_return_url(return_url: str | None, settings: Settings) -> str | None:
    if return_url is None:
        return None
    if _origin(return_url) not in _allowed_return_url_origins(settings):
        raise ZippinException(
            "return_url origin is not allowed.",
            code="RETURN_URL_NOT_ALLOWED",
            http_status=400,
        )
    return return_url


@router.post("/anonymous-users", response_model=AnonymousUserCreateResponse)
async def create_anonymous_user(
    payload: AnonymousUserCreateRequest,
    request: Request,
) -> AnonymousUserCreateResponse:
    result = await create_or_reuse_anonymous_user(payload.existing_anonymous_user_id)
    logger.info(
        "anonymous_user_resolved",
        anonymous_user_id=str(result.anonymous_user_id),
        reused=result.reused,
        request_id=getattr(request.state, "request_id", "-"),
    )
    return AnonymousUserCreateResponse(
        anonymous_user_id=result.anonymous_user_id,
        reused=result.reused,
    )


@router.get(
    "/{provider}/start",
    response_model=OAuthStartResponse,
    responses={302: {"description": "Redirect to OAuth provider authorization URL."}},
)
async def start_oauth(
    provider: OAuthProvider,
    request: Request,
    anonymous_user_id: str | None = Query(default=None),
    return_url: str | None = Query(default=None),
    mode: Literal["redirect", "json"] = Query(default="redirect"),
) -> OAuthStartResponse | RedirectResponse:
    settings = get_settings()
    provider_settings = _provider_settings(provider, settings)
    if not provider_settings.client_id or not provider_settings.redirect_uri:
        raise ZippinException(
            f"OAuth provider {provider.value!r} is not configured.",
            code="OAUTH_PROVIDER_CONFIG_MISSING",
            http_status=503,
        )

    normalized_return_url = _validate_return_url(return_url, settings)
    parsed_anonymous_user_id = parse_existing_anonymous_user_id(anonymous_user_id)
    state = secrets.token_urlsafe(48)
    nonce = secrets.token_urlsafe(32)
    payload = OAuthStatePayload(
        anonymous_user_id=parsed_anonymous_user_id,
        provider=provider.value,
        return_url=normalized_return_url,
        nonce=nonce,
        created_at=datetime.now(UTC),
    )

    store = get_oauth_state_store()
    state_stored = await store.put(state, payload)
    if not state_stored:
        state = secrets.token_urlsafe(48)
        payload = OAuthStatePayload(
            anonymous_user_id=parsed_anonymous_user_id,
            provider=provider.value,
            return_url=normalized_return_url,
            nonce=nonce,
            created_at=datetime.now(UTC),
        )
        state_stored = await store.put(state, payload)
    if not state_stored:
        raise ZippinException(
            "Could not allocate OAuth state.",
            code="OAUTH_STATE_COLLISION",
            http_status=503,
        )

    provider_module = PROVIDER_MODULES[provider]
    authorization_url = provider_module.build_authorization_url(
        provider_settings.client_id,
        provider_settings.redirect_uri,
        state,
        nonce,
        provider_module.DEFAULT_SCOPES,
    )
    logger.info(
        "oauth_start",
        provider=provider.value,
        anonymous_user_id=(
            str(parsed_anonymous_user_id)
            if parsed_anonymous_user_id is not None
            else None
        ),
        mode=mode,
        request_id=getattr(request.state, "request_id", "-"),
    )

    if mode == "json":
        return OAuthStartResponse(authorization_url=authorization_url)
    return RedirectResponse(authorization_url, status_code=302)

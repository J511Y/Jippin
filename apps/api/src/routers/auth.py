from __future__ import annotations

import secrets
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse
from jose import jwt

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
    OAuthLoginResult,
    complete_oauth_login,
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
        settings.frontend_auth_terms_url,
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


@router.get(
    "/callback/{provider}",
    responses={
        302: {"description": "Redirect to the frontend auth success or terms URL."}
    },
)
async def oauth_callback(
    provider: OAuthProvider,
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    id_token: str | None = Query(default=None),
) -> RedirectResponse:
    settings = get_settings()
    provider_settings = _provider_settings(provider, settings)
    if not provider_settings.client_id or not provider_settings.redirect_uri:
        raise ZippinException(
            f"OAuth provider {provider.value!r} is not configured.",
            code="OAUTH_PROVIDER_CONFIG_MISSING",
            http_status=503,
        )

    state_payload = await get_oauth_state_store().consume(state)
    if state_payload is None or state_payload.provider != provider.value:
        raise ZippinException(
            "OAuth state is invalid or expired.",
            code="OAUTH_STATE_INVALID",
            http_status=422,
        )

    provider_module = PROVIDER_MODULES[provider]
    async with httpx.AsyncClient(timeout=10.0) as http_client:
        tokens = await provider_module.exchange_code(
            code,
            http_client=http_client,
            settings=settings,
        )
        if id_token and not tokens.id_token:
            tokens = replace(tokens, id_token=id_token)
        profile = await provider_module.fetch_userinfo(
            tokens,
            http_client=http_client,
            settings=settings,
        )

    login_result = await complete_oauth_login(
        provider=provider,
        profile=profile,
        anonymous_user_id=state_payload.anonymous_user_id,
    )
    response = RedirectResponse(
        _callback_redirect_url(state_payload, login_result, settings),
        status_code=302,
    )
    _set_session_cookie(response, login_result, settings)
    logger.info(
        "oauth_callback",
        provider=provider.value,
        user_id=str(login_result.user_id),
        signup_completed=login_result.signup_completed,
        anonymous_user_claimed=login_result.claimed_anonymous_user_id is not None,
        request_id=getattr(request.state, "request_id", "-"),
    )
    return response


def _callback_redirect_url(
    state_payload: OAuthStatePayload,
    login_result: OAuthLoginResult,
    settings: Settings,
) -> str:
    if login_result.signup_completed:
        return state_payload.return_url or settings.frontend_auth_success_url
    return settings.frontend_auth_terms_url


def _set_session_cookie(
    response: RedirectResponse,
    login_result: OAuthLoginResult,
    settings: Settings,
) -> None:
    token = _create_session_token(login_result, settings)
    max_age = settings.auth_session_ttl_days * 24 * 60 * 60
    secure = (
        settings.app_env == "production"
        if settings.auth_cookie_secure is None
        else settings.auth_cookie_secure
    )
    response.set_cookie(
        settings.auth_cookie_name,
        token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        domain=settings.auth_cookie_domain,
    )


def _create_session_token(login_result: OAuthLoginResult, settings: Settings) -> str:
    if not settings.auth_jwt_secret:
        raise ZippinException(
            "Session token signing secret is not configured.",
            code="AUTH_SESSION_CONFIG_MISSING",
            http_status=503,
        )
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=settings.auth_session_ttl_days)
    return jwt.encode(
        {
            "sub": str(login_result.user_id),
            "typ": "jippin_session",
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        },
        settings.auth_jwt_secret,
        algorithm=settings.auth_jwt_alg,
    )

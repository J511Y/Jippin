from __future__ import annotations

import secrets
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ..auth.providers import PROVIDER_MODULES, OAuthProvider
from ..auth.session import (
    clear_session_cookie,
    read_session_claims,
    set_session_cookie,
)
from ..auth.state_store import OAuthStatePayload, get_oauth_state_store
from ..config import Settings, get_settings
from ..errors import ZippinException
from ..logging import get_logger
from ..schemas.auth import (
    AnonymousUserCreateRequest,
    AnonymousUserCreateResponse,
    AuthLogoutResponse,
    AuthMeResponse,
    AuthUserResponse,
    KakaoSyncAuditRequest,
    KakaoSyncAuditResponse,
    OAuthStartResponse,
    SupabaseAccountLinkRequest,
    SupabaseAccountLinkResponse,
    SupabaseSessionBridgeRequest,
    SupabaseSessionBridgeResponse,
    TermsAcceptRequest,
    TermsAcceptResponse,
)
from ..services.auth import (
    OAuthLoginResult,
    SupabaseSessionBridgeResult,
    accept_required_terms,
    complete_oauth_login,
    create_or_reuse_anonymous_user,
    get_current_user_context,
    link_oauth_account,
    link_supabase_account,
    parse_existing_anonymous_user_id,
    record_kakao_sync_consent,
)
from ..services.supabase_session import (
    parse_bearer_token,
    resolve_jippin_user_for_supabase,
    validate_supabase_provider_claims,
    verify_supabase_access_token,
)

logger = get_logger("zippin.auth")
router = APIRouter(prefix="/auth", tags=["auth"])


def _legacy_oauth_flow_removed() -> ZippinException:
    return ZippinException(
        "Legacy OAuth routes were removed after Supabase Auth cutover.",
        code="AUTH_LEGACY_FLOW_REMOVED",
        http_status=410,
    )


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


@router.get("/me", response_model=AuthMeResponse)
async def get_me(request: Request) -> AuthMeResponse:
    claims = read_session_claims(request)
    context = await get_current_user_context(claims.user_id)
    return AuthMeResponse(
        user=AuthUserResponse(
            id=context.user_id,
            email=context.email,
            display_name=context.display_name,
            profile_image_url=context.profile_image_url,
            role=context.role,
        ),
        providers=context.providers,
        signup_complete=not context.missing_required_terms,
        missing_required_terms=context.missing_required_terms,
    )


@router.post("/logout", response_model=AuthLogoutResponse)
async def logout() -> JSONResponse:
    response = JSONResponse(AuthLogoutResponse().model_dump())
    clear_session_cookie(response)
    return response


async def complete_supabase_session(
    *,
    access_token: str,
    anonymous_user_id: str | None,  # noqa: ARG001 - legacy field ignored.
    requested_provider: str | None = None,
) -> SupabaseSessionBridgeResult:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as http_client:
        claims = await verify_supabase_access_token(
            access_token,
            http_client=http_client,
            settings=settings,
        )
    validate_supabase_provider_claims(
        claims=claims,
        requested_provider=requested_provider,
    )

    email_claim_raw = claims.get("email")
    email_claim = (
        email_claim_raw.strip().lower()
        if isinstance(email_claim_raw, str) and email_claim_raw.strip()
        else None
    )
    result = await resolve_jippin_user_for_supabase(
        supabase_subject=str(claims["sub"]),
        email_claim=email_claim,
    )
    # Kakao Sync 로그인은 Kakao 자체 동의 화면을 이미 거쳤으므로 필수 약관 동의를
    # source='kakao_sync' 로 기록하고 내부 약관 화면(/auth/terms)을 중복 노출하지
    # 않는다 (AGENTS §4.7 #5 / ADR-0004). 현재 브리지는 'kakao' provider 만 허용하지만
    # 향후 다른 provider 가 추가될 때를 대비해 분기로 둔다.
    if requested_provider == "kakao":
        missing_required_terms = await record_kakao_sync_consent(result.user_id)
    else:
        context = await get_current_user_context(result.user_id)
        missing_required_terms = context.missing_required_terms
    return SupabaseSessionBridgeResult(
        user_id=result.user_id,
        pending_anonymous_user_id=None,
        missing_required_terms=missing_required_terms,
    )


@router.post(
    "/terms/kakao-sync",
    response_model=KakaoSyncAuditResponse,
    status_code=202,
)
async def kakao_sync_audit_stub(
    payload: KakaoSyncAuditRequest,
    request: Request,
) -> KakaoSyncAuditResponse:
    """Phase 1 stub — `apps/web/lib/kakao-sync-audit.ts` 의 호출 대상 (CMP-581 round-13).

    web helper 가 `enabled: true` + 실제 backend route 를 가리키도록 하기 위한
    minimal stub. 본 핸들러는 다음만 수행한다:

    - Authorization: Bearer 헤더 존재 확인 (실 JWT 검증은 Backend/Auth 트랙).
    - payload schema 검증 (Pydantic).
    - 호출 사실을 logger 로 남김 — 운영이 Sentry breadcrumb 로 추적 가능.

    실 `terms_consents(source='kakao_sync')` upsert + Kakao OpenAPI 검증은
    Backend/Auth 트랙 (별 이슈) 의 책임. 본 stub 은 web 어댑터가 무조건 실패
    경로로 빠지는 회귀를 막기 위한 placeholder.

    응답은 202 Accepted + `stubbed: true` — callsite (callback Route Handler)
    가 stub 상태를 인지하고 success page 로 진입할지 별도 판단할 수 있게 한다.
    """
    authorization = request.headers.get("authorization", "")
    # 기존 API error contract (auth/session.py, services/auth.py) 와 정합:
    # uppercase stable code `AUTH_UNAUTHENTICATED` 사용 (CMP-581 round-16 항목 3).
    # round-17 항목 2 — `Bearer ` prefix 만 보고 통과시키면 빈 token 도 허용되어
    # 실제 인증이 없는 상태로 stub 가 200 을 반환하는 회귀. prefix + non-empty
    # value 둘 다 검증해야 한다.
    if not authorization.lower().startswith("bearer "):
        raise ZippinException(
            "Authorization: Bearer <supabase access_token> 헤더가 필요합니다.",
            code="AUTH_UNAUTHENTICATED",
            http_status=401,
        )
    bearer_value = authorization[len("Bearer ") :].strip()
    if not bearer_value:
        raise ZippinException(
            "Authorization Bearer token 이 비어 있습니다.",
            code="AUTH_UNAUTHENTICATED",
            http_status=401,
        )
    logger.info(
        "kakao_sync_audit_stub_received",
        supabase_user_id=payload.supabase_user_id,
        linked_provider=payload.linked_provider,
        has_provider_access_token=payload.provider_access_token is not None,
    )
    return KakaoSyncAuditResponse()


@router.post("/supabase/session", response_model=SupabaseSessionBridgeResponse)
async def bridge_supabase_session(
    request: Request,
    payload: SupabaseSessionBridgeRequest = Body(
        default_factory=SupabaseSessionBridgeRequest
    ),
) -> JSONResponse:
    settings = get_settings()
    access_token = parse_bearer_token(request.headers.get("authorization"))
    result = await complete_supabase_session(
        access_token=access_token,
        anonymous_user_id=(
            str(payload.anonymous_user_id)
            if payload.anonymous_user_id is not None
            else None
        ),
        requested_provider=payload.requested_provider,
    )
    response_body = SupabaseSessionBridgeResponse(
        signup_complete=not result.missing_required_terms,
        missing_required_terms=result.missing_required_terms,
        redirect_url=(
            None
            if not result.missing_required_terms
            else settings.frontend_auth_terms_url
        ),
    )
    response = JSONResponse(response_body.model_dump())
    set_session_cookie(
        response,
        result.user_id,
        settings,
        pending_anonymous_user_id=result.pending_anonymous_user_id,
    )
    logger.info(
        "supabase_session_minted",
        user_id=str(result.user_id),
        request_id=getattr(request.state, "request_id", "-"),
    )
    return response


@router.post("/supabase/link", response_model=SupabaseAccountLinkResponse)
async def link_supabase_identity(
    request: Request,
    payload: SupabaseAccountLinkRequest,
) -> SupabaseAccountLinkResponse:
    claims = read_session_claims(request)
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ZippinException(
            "Supabase bearer token is required.",
            code="SUPABASE_SESSION_BEARER_REQUIRED",
            http_status=401,
        )
    await link_supabase_account(
        access_token=token,
        linking_user_id=claims.user_id,
        requested_provider=payload.requested_provider,
    )
    return SupabaseAccountLinkResponse()


@router.post("/terms/accept", response_model=TermsAcceptResponse)
async def accept_terms(
    payload: TermsAcceptRequest,
    request: Request,
) -> TermsAcceptResponse:
    claims = read_session_claims(request)
    result = await accept_required_terms(
        user_id=claims.user_id,
        agreed_term_ids={
            str(consent.term_id) for consent in payload.consents if consent.agreed
        },
        pending_anonymous_user_id=claims.pending_anonymous_user_id,
    )
    response = TermsAcceptResponse(
        signup_complete=result.signup_complete,
        missing_required_terms=result.missing_required_terms,
        claimed_anonymous_user=result.claimed_anonymous_user,
    )
    return response


@router.post(
    "/sso-accounts/{provider}/link",
    response_model=OAuthStartResponse,
    responses={302: {"description": "Redirect to OAuth provider authorization URL."}},
)
async def link_sso_account(
    provider: OAuthProvider,
    request: Request,
    return_url: str | None = Query(default=None),
    mode: Literal["redirect", "json"] = Query(default="redirect"),
) -> OAuthStartResponse | RedirectResponse:
    raise _legacy_oauth_flow_removed()
    claims = read_session_claims(request)
    settings = get_settings()
    provider_settings = _provider_settings(provider, settings)
    if not provider_settings.client_id or not provider_settings.redirect_uri:
        raise ZippinException(
            f"OAuth provider {provider.value!r} is not configured.",
            code="OAUTH_PROVIDER_CONFIG_MISSING",
            http_status=503,
        )

    normalized_return_url = _validate_return_url(return_url, settings)
    state = secrets.token_urlsafe(48)
    nonce = secrets.token_urlsafe(32)
    payload = OAuthStatePayload(
        anonymous_user_id=None,
        provider=provider.value,
        return_url=normalized_return_url,
        nonce=nonce,
        created_at=datetime.now(UTC),
        linking_user_id=claims.user_id,
    )
    state_stored = await get_oauth_state_store().put(state, payload)
    if not state_stored:
        state = secrets.token_urlsafe(48)
        state_stored = await get_oauth_state_store().put(state, payload)
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
        "oauth_link_start",
        provider=provider.value,
        user_id=str(claims.user_id),
        mode=mode,
        request_id=getattr(request.state, "request_id", "-"),
    )

    if mode == "json":
        return OAuthStartResponse(authorization_url=authorization_url)
    return RedirectResponse(authorization_url, status_code=302)


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
    raise _legacy_oauth_flow_removed()
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
    raise _legacy_oauth_flow_removed()
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
        if provider == OAuthProvider.GOOGLE:
            profile = await provider_module.fetch_userinfo(
                tokens,
                http_client=http_client,
                settings=settings,
                expected_nonce=state_payload.nonce,
            )
        else:
            profile = await provider_module.fetch_userinfo(
                tokens,
                http_client=http_client,
                settings=settings,
            )

    if state_payload.linking_user_id is not None:
        await link_oauth_account(
            linking_user_id=state_payload.linking_user_id,
            provider=provider,
            profile=profile,
        )
        response = RedirectResponse(
            state_payload.return_url or settings.frontend_auth_success_url,
            status_code=302,
        )
        logger.info(
            "oauth_link_callback",
            provider=provider.value,
            user_id=str(state_payload.linking_user_id),
            request_id=getattr(request.state, "request_id", "-"),
        )
        return response

    login_result = await complete_oauth_login(
        provider=provider,
        profile=profile,
        anonymous_user_id=state_payload.anonymous_user_id,
    )
    response = RedirectResponse(
        _callback_redirect_url(state_payload, login_result, settings),
        status_code=302,
    )
    _set_session_cookie(response, state_payload, login_result, settings)
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
    state_payload: OAuthStatePayload,
    login_result: OAuthLoginResult,
    settings: Settings,
) -> None:
    pending_anonymous_user_id = (
        state_payload.anonymous_user_id if not login_result.signup_completed else None
    )
    set_session_cookie(
        response,
        login_result.user_id,
        settings,
        pending_anonymous_user_id=pending_anonymous_user_id,
    )

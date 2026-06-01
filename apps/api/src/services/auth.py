from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from jose import JWTError, jwt

from ..config import get_settings
from ..db import get_engine
from ..auth.providers import OAuthProvider, ProviderProfile
from ..errors import ZippinException
from ..models import AnonymousUser, ExternalSsoAccount, TermsConsent, User

INTERNAL_TERMS_SOURCE = "internal_signup"
INTERNAL_TERMS_VERSION = "internal_signup"


@dataclass(frozen=True)
class AnonymousUserResult:
    anonymous_user_id: uuid.UUID
    reused: bool


@dataclass(frozen=True)
class OAuthLoginResult:
    user_id: uuid.UUID
    signup_completed: bool
    claimed_anonymous_user_id: uuid.UUID | None


@dataclass(frozen=True)
class SupabaseSessionBridgeResult:
    user_id: uuid.UUID
    pending_anonymous_user_id: uuid.UUID | None
    missing_required_terms: list[str]


@dataclass(frozen=True)
class CurrentUserContext:
    user_id: uuid.UUID
    email: str | None
    display_name: str | None
    profile_image_url: str | None
    role: str
    providers: list[str]
    missing_required_terms: list[str]


@dataclass(frozen=True)
class TermsAcceptResult:
    signup_complete: bool
    missing_required_terms: list[str]
    claimed_anonymous_user: bool


def parse_existing_anonymous_user_id(value: str | None) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except (TypeError, ValueError, AttributeError):
        return None


async def create_or_reuse_anonymous_user(
    existing_anonymous_user_id: str | None,
) -> AnonymousUserResult:
    parsed_id = parse_existing_anonymous_user_id(existing_anonymous_user_id)
    cutoff = datetime.now(UTC) - timedelta(days=get_settings().anon_session_ttl_days)

    async with get_engine().begin() as conn:
        if parsed_id is not None:
            existing = await conn.execute(
                sa.select(AnonymousUser.id).where(
                    AnonymousUser.id == parsed_id,
                    AnonymousUser.converted_user_id.is_(None),
                    AnonymousUser.last_seen_at >= cutoff,
                )
            )
            if existing.scalar_one_or_none() is not None:
                await conn.execute(
                    sa.update(AnonymousUser)
                    .where(
                        AnonymousUser.id == parsed_id,
                        AnonymousUser.converted_user_id.is_(None),
                    )
                    .values(
                        last_seen_at=sa.func.now(),
                        updated_at=sa.func.now(),
                    )
                )
                return AnonymousUserResult(
                    anonymous_user_id=parsed_id,
                    reused=True,
                )

        inserted = await conn.execute(
            sa.insert(AnonymousUser).values().returning(AnonymousUser.id)
        )
        return AnonymousUserResult(
            anonymous_user_id=inserted.scalar_one(),
            reused=False,
        )


async def complete_oauth_login(
    *,
    provider: OAuthProvider,
    profile: ProviderProfile,
    anonymous_user_id: uuid.UUID | None,
) -> OAuthLoginResult:
    settings = get_settings()
    signup_completed = _signup_completed(provider, profile, settings)
    claimed_anonymous_user_id: uuid.UUID | None = None

    async with get_engine().begin() as conn:
        existing_account = await conn.execute(
            sa.select(ExternalSsoAccount.user_id).where(
                ExternalSsoAccount.provider == provider.value,
                ExternalSsoAccount.provider_subject == profile.provider_subject,
            )
        )
        user_id = existing_account.scalar_one_or_none()
        if user_id is None:
            inserted_user = await conn.execute(
                sa.insert(User)
                .values(
                    email=profile.email,
                    display_name=profile.display_name,
                    profile_image_url=profile.profile_image_url,
                    last_login_at=sa.func.now(),
                )
                .returning(User.id)
            )
            user_id = inserted_user.scalar_one()
            await conn.execute(
                sa.insert(ExternalSsoAccount).values(
                    user_id=user_id,
                    provider=provider.value,
                    provider_subject=profile.provider_subject,
                    provider_email=profile.email,
                    display_name=profile.display_name,
                    profile_image_url=profile.profile_image_url,
                )
            )
        else:
            await conn.execute(
                sa.update(ExternalSsoAccount)
                .where(
                    ExternalSsoAccount.provider == provider.value,
                    ExternalSsoAccount.provider_subject == profile.provider_subject,
                )
                .values(
                    provider_email=profile.email,
                    display_name=profile.display_name,
                    profile_image_url=profile.profile_image_url,
                    updated_at=sa.func.now(),
                )
            )
            await conn.execute(
                sa.update(User)
                .where(User.id == user_id)
                .values(
                    display_name=profile.display_name,
                    profile_image_url=profile.profile_image_url,
                    last_login_at=sa.func.now(),
                    updated_at=sa.func.now(),
                )
            )

        if provider == OAuthProvider.KAKAO and profile.agreed_terms_tags:
            consent_rows = [
                {
                    "user_id": user_id,
                    "term_id": tag,
                    "version": "kakao_sync",
                    "source": "kakao_sync",
                    "agreed_at": sa.func.now(),
                }
                for tag in profile.agreed_terms_tags
            ]
            await conn.execute(
                pg_insert(TermsConsent)
                .values(consent_rows)
                .on_conflict_do_nothing(
                    index_elements=[
                        TermsConsent.user_id,
                        TermsConsent.term_id,
                        TermsConsent.version,
                    ]
                )
            )

        if signup_completed and anonymous_user_id is not None:
            await conn.execute(
                sa.update(AnonymousUser)
                .where(
                    AnonymousUser.id == anonymous_user_id,
                    AnonymousUser.converted_user_id.is_(None),
                )
                .values(
                    converted_user_id=user_id,
                    converted_at=sa.func.now(),
                    updated_at=sa.func.now(),
                )
            )
            claimed_anonymous_user_id = anonymous_user_id

    return OAuthLoginResult(
        user_id=user_id,
        signup_completed=signup_completed,
        claimed_anonymous_user_id=claimed_anonymous_user_id,
    )


async def complete_supabase_session(
    *,
    access_token: str,
    anonymous_user_id: str | None,
) -> SupabaseSessionBridgeResult:
    settings = get_settings()
    claims = _decode_supabase_access_token(access_token, settings)
    provider, profile = _supabase_provider_profile(claims)
    parsed_anonymous_user_id = parse_existing_anonymous_user_id(anonymous_user_id)
    login_result = await complete_oauth_login(
        provider=provider,
        profile=profile,
        anonymous_user_id=parsed_anonymous_user_id,
    )
    context = await get_current_user_context(login_result.user_id)
    pending_anonymous_user_id = (
        parsed_anonymous_user_id if context.missing_required_terms else None
    )
    return SupabaseSessionBridgeResult(
        user_id=login_result.user_id,
        pending_anonymous_user_id=pending_anonymous_user_id,
        missing_required_terms=context.missing_required_terms,
    )


async def link_supabase_account(
    *,
    access_token: str,
    linking_user_id: uuid.UUID,
) -> None:
    settings = get_settings()
    claims = _decode_supabase_access_token(access_token, settings)
    provider, profile = _supabase_provider_profile(claims)
    await link_oauth_account(
        linking_user_id=linking_user_id,
        provider=provider,
        profile=profile,
    )


async def get_current_user_context(user_id: uuid.UUID) -> CurrentUserContext:
    settings = get_settings()
    async with get_engine().begin() as conn:
        user_row = (
            await conn.execute(
                sa.select(
                    User.id,
                    User.email,
                    User.display_name,
                    User.profile_image_url,
                    User.role,
                ).where(User.id == user_id, User.status == "active")
            )
        ).one_or_none()
        if user_row is None:
            raise ZippinException(
                "Authentication is required.",
                code="AUTH_UNAUTHENTICATED",
                http_status=401,
            )

        providers = (
            (
                await conn.execute(
                    sa.select(ExternalSsoAccount.provider)
                    .where(ExternalSsoAccount.user_id == user_id)
                    .order_by(ExternalSsoAccount.provider)
                )
            )
            .scalars()
            .all()
        )
        missing_terms = await _missing_required_terms(conn, user_id, settings)

    return CurrentUserContext(
        user_id=user_row.id,
        email=user_row.email,
        display_name=user_row.display_name,
        profile_image_url=user_row.profile_image_url,
        role=user_row.role,
        providers=list(providers),
        missing_required_terms=missing_terms,
    )


async def link_oauth_account(
    *,
    linking_user_id: uuid.UUID,
    provider: OAuthProvider,
    profile: ProviderProfile,
) -> None:
    async with get_engine().begin() as conn:
        user_exists = (
            await conn.execute(
                sa.select(User.id).where(
                    User.id == linking_user_id,
                    User.status == "active",
                )
            )
        ).scalar_one_or_none()
        if user_exists is None:
            raise ZippinException(
                "Authentication is required.",
                code="AUTH_UNAUTHENTICATED",
                http_status=401,
            )

        existing_subject_user_id = (
            await conn.execute(
                sa.select(ExternalSsoAccount.user_id).where(
                    ExternalSsoAccount.provider == provider.value,
                    ExternalSsoAccount.provider_subject == profile.provider_subject,
                )
            )
        ).scalar_one_or_none()
        if existing_subject_user_id is not None:
            if existing_subject_user_id != linking_user_id:
                raise ZippinException(
                    "This SSO account is already linked to another user.",
                    code="SSO_ALREADY_LINKED_TO_OTHER_USER",
                    http_status=409,
                )
            raise ZippinException(
                "This SSO provider is already linked to the current user.",
                code="SSO_PROVIDER_ALREADY_LINKED",
                http_status=409,
            )

        existing_provider = (
            await conn.execute(
                sa.select(ExternalSsoAccount.id).where(
                    ExternalSsoAccount.user_id == linking_user_id,
                    ExternalSsoAccount.provider == provider.value,
                )
            )
        ).scalar_one_or_none()
        if existing_provider is not None:
            raise ZippinException(
                "This SSO provider is already linked to the current user.",
                code="SSO_PROVIDER_ALREADY_LINKED",
                http_status=409,
            )

        await conn.execute(
            sa.insert(ExternalSsoAccount).values(
                user_id=linking_user_id,
                provider=provider.value,
                provider_subject=profile.provider_subject,
                provider_email=profile.email,
                display_name=profile.display_name,
                profile_image_url=profile.profile_image_url,
            )
        )


async def accept_required_terms(
    *,
    user_id: uuid.UUID,
    agreed_term_ids: set[str],
    pending_anonymous_user_id: uuid.UUID | None,
) -> TermsAcceptResult:
    settings = get_settings()
    required_term_ids = _required_term_ids(settings)
    missing_from_payload = [
        term_id for term_id in required_term_ids if term_id not in agreed_term_ids
    ]
    if missing_from_payload:
        raise ZippinException(
            "Required terms are missing.",
            code="TERMS_REQUIRED_MISSING",
            http_status=422,
            details={"missing_required_terms": missing_from_payload},
        )

    claimed_anonymous_user = False
    async with get_engine().begin() as conn:
        user_exists = (
            await conn.execute(
                sa.select(User.id).where(User.id == user_id, User.status == "active")
            )
        ).scalar_one_or_none()
        if user_exists is None:
            raise ZippinException(
                "Authentication is required.",
                code="AUTH_UNAUTHENTICATED",
                http_status=401,
            )

        if agreed_term_ids:
            consent_rows = [
                {
                    "user_id": user_id,
                    "term_id": term_id,
                    "version": INTERNAL_TERMS_VERSION,
                    "source": INTERNAL_TERMS_SOURCE,
                    "agreed_at": sa.func.now(),
                    "updated_at": sa.func.now(),
                }
                for term_id in sorted(agreed_term_ids)
            ]
            await conn.execute(
                pg_insert(TermsConsent)
                .values(consent_rows)
                .on_conflict_do_update(
                    index_elements=[
                        TermsConsent.user_id,
                        TermsConsent.term_id,
                        TermsConsent.version,
                    ],
                    set_={
                        "source": INTERNAL_TERMS_SOURCE,
                        "agreed_at": sa.func.now(),
                        "updated_at": sa.func.now(),
                    },
                )
            )

        missing_terms = await _missing_required_terms(conn, user_id, settings)
        if not missing_terms and pending_anonymous_user_id is not None:
            result = await conn.execute(
                sa.update(AnonymousUser)
                .where(
                    AnonymousUser.id == pending_anonymous_user_id,
                    AnonymousUser.converted_user_id.is_(None),
                )
                .values(
                    converted_user_id=user_id,
                    converted_at=sa.func.now(),
                    updated_at=sa.func.now(),
                )
                .returning(AnonymousUser.id)
            )
            claimed_anonymous_user = result.scalar_one_or_none() is not None

    return TermsAcceptResult(
        signup_complete=not missing_terms,
        missing_required_terms=missing_terms,
        claimed_anonymous_user=claimed_anonymous_user,
    )


def _signup_completed(
    provider: OAuthProvider,
    profile: ProviderProfile,
    settings,
) -> bool:
    if provider != OAuthProvider.KAKAO:
        return False
    required_tags = set(settings.kakao_sync_required_term_tags)
    if not required_tags:
        return True
    return required_tags.issubset(set(profile.agreed_terms_tags))


def _decode_supabase_access_token(access_token: str, settings) -> dict[str, Any]:
    if not settings.supabase_jwt_secret:
        raise ZippinException(
            "Supabase JWT verification secret is not configured.",
            code="SUPABASE_SESSION_CONFIG_MISSING",
            http_status=503,
        )
    try:
        claims = jwt.decode(
            access_token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience=settings.supabase_jwt_audience,
        )
    except JWTError as exc:
        raise ZippinException(
            "Supabase access token is invalid.",
            code="SUPABASE_SESSION_INVALID",
            http_status=401,
        ) from exc
    if not claims.get("sub"):
        raise ZippinException(
            "Supabase access token is missing subject.",
            code="SUPABASE_SESSION_INVALID",
            http_status=401,
        )
    return claims


def _supabase_provider_from_claims(claims: dict[str, Any]) -> OAuthProvider:
    app_metadata = claims.get("app_metadata")
    if not isinstance(app_metadata, dict):
        app_metadata = {}
    candidates = [
        app_metadata.get("provider"),
        *(
            app_metadata.get("providers")
            if isinstance(app_metadata.get("providers"), list)
            else []
        ),
    ]
    for candidate in candidates:
        normalized = _normalize_supabase_provider(candidate)
        if normalized is not None:
            return normalized
    raise ZippinException(
        "Supabase access token does not contain a supported OAuth provider.",
        code="SUPABASE_PROVIDER_UNSUPPORTED",
        http_status=422,
    )


def _normalize_supabase_provider(value: object) -> OAuthProvider | None:
    if not isinstance(value, str):
        return None
    normalized = value.removeprefix("custom:").lower()
    if normalized in {provider.value for provider in OAuthProvider}:
        return OAuthProvider(normalized)
    return None


def _supabase_provider_profile(
    claims: dict[str, Any],
) -> tuple[OAuthProvider, ProviderProfile]:
    provider = _supabase_provider_from_claims(claims)
    metadata = _supabase_user_metadata(claims)
    return provider, ProviderProfile(
        provider_subject=_supabase_provider_subject(claims, provider, metadata),
        email=_optional_str(claims.get("email"))
        or _optional_str(metadata.get("email")),
        display_name=_supabase_display_name(metadata),
        profile_image_url=_supabase_avatar_url(metadata),
        agreed_terms_tags=tuple(
            _string_list(metadata.get("agreed_terms_tags"))
            or _string_list(claims.get("agreed_terms_tags"))
        ),
    )


def _supabase_provider_subject(
    claims: dict[str, Any],
    provider: OAuthProvider,
    metadata: dict[str, Any],
) -> str:
    provider_key = provider.value
    for key in (
        "provider_id",
        f"{provider_key}_id",
        f"{provider_key}_subject",
        "sub",
        "id",
    ):
        value = _optional_str(metadata.get(key))
        if value:
            return value

    for identity in [
        *_dict_list(claims.get("identities")),
        *_dict_list(metadata.get("identities")),
    ]:
        identity_provider = _normalize_supabase_provider(
            identity.get("provider") or identity.get("identity_provider")
        )
        if identity_provider != provider:
            continue
        identity_data = identity.get("identity_data")
        if not isinstance(identity_data, dict):
            identity_data = {}
        for key in ("provider_id", "sub", "id"):
            value = _optional_str(identity_data.get(key)) or _optional_str(
                identity.get(key)
            )
            if value:
                return value

    return str(claims["sub"])


def _supabase_user_metadata(claims: dict[str, Any]) -> dict[str, Any]:
    metadata = claims.get("user_metadata")
    return metadata if isinstance(metadata, dict) else {}


def _supabase_display_name(metadata: dict[str, Any]) -> str | None:
    for key in ("name", "full_name", "display_name"):
        value = _optional_str(metadata.get(key))
        if value:
            return value
    return None


def _supabase_avatar_url(metadata: dict[str, Any]) -> str | None:
    for key in ("avatar_url", "picture", "profile_image_url"):
        value = _optional_str(metadata.get(key))
        if value:
            return value
    return None


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


async def _missing_required_terms(conn, user_id: uuid.UUID, settings) -> list[str]:
    required_terms = _required_term_ids(settings)
    if not required_terms:
        return []
    agreed_terms = set(
        (
            await conn.execute(
                sa.select(TermsConsent.term_id).where(
                    TermsConsent.user_id == user_id,
                    TermsConsent.term_id.in_(required_terms),
                )
            )
        )
        .scalars()
        .all()
    )
    return [term_id for term_id in required_terms if term_id not in agreed_terms]


def _required_term_ids(settings) -> list[str]:
    return list(dict.fromkeys(settings.kakao_sync_required_term_tags))

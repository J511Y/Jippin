from __future__ import annotations

import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..config import get_settings
from ..db import get_engine
from ..errors import ZippinException
from ..models import TermsConsent, User

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
    """Parse legacy anonymous ids only for request compatibility.

    CMP-604 removes ``public.anonymous_users``. Callers may still send the old
    field during rollout, but it no longer drives database writes.
    """

    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except (TypeError, ValueError, AttributeError):
        return None


def _legacy_auth_removed() -> ZippinException:
    return ZippinException(
        "Legacy public auth tables were removed after Supabase Auth cutover.",
        code="AUTH_LEGACY_FLOW_REMOVED",
        http_status=410,
    )


async def create_or_reuse_anonymous_user(
    existing_anonymous_user_id: str | None,  # noqa: ARG001
) -> AnonymousUserResult:
    raise _legacy_auth_removed()


async def complete_oauth_login(**kwargs) -> OAuthLoginResult:  # noqa: ANN003, ARG001
    raise _legacy_auth_removed()


async def link_oauth_account(**kwargs) -> None:  # noqa: ANN003, ARG001
    raise _legacy_auth_removed()


async def _claim_anonymous_user(**kwargs) -> None:  # noqa: ANN003, ARG001
    # No-op compatibility shim. Supabase Anonymous Sign-In preserves ownership
    # by keeping the same auth.users.id through identity linking.
    return None


async def complete_supabase_session(
    *,
    access_token: str,  # noqa: ARG001 - verified in routers.auth before lookup.
    anonymous_user_id: str | None,  # noqa: ARG001 - legacy field ignored.
    requested_provider: str | None = None,  # noqa: ARG001 - auth.identities is SSOT.
) -> SupabaseSessionBridgeResult:
    raise ZippinException(
        "Use routers.auth.complete_supabase_session with JWKS verification.",
        code="AUTH_SESSION_INTERNAL_ERROR",
        http_status=500,
    )


async def link_supabase_account(
    *,
    access_token: str,  # noqa: ARG001
    linking_user_id: uuid.UUID,  # noqa: ARG001
    requested_provider: str | None = None,  # noqa: ARG001
) -> None:
    raise ZippinException(
        "Provider linking is owned by Supabase Auth linkIdentity().",
        code="AUTH_LINKING_OWNED_BY_SUPABASE",
        http_status=410,
    )


async def get_current_user_context(user_id: uuid.UUID) -> CurrentUserContext:
    settings = get_settings()
    async with get_engine().begin() as conn:
        user_row = (
            await conn.execute(
                sa.select(
                    User.id,
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

        missing_terms = await _missing_required_terms(conn, user_id, settings)

    return CurrentUserContext(
        user_id=user_row.id,
        email=None,
        display_name=user_row.display_name,
        profile_image_url=user_row.profile_image_url,
        role=user_row.role,
        providers=[],
        missing_required_terms=missing_terms,
    )


async def accept_required_terms(
    *,
    user_id: uuid.UUID,
    agreed_term_ids: set[str],
    pending_anonymous_user_id: uuid.UUID | None,  # noqa: ARG001 - legacy field ignored.
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

    return TermsAcceptResult(
        signup_complete=not missing_terms,
        missing_required_terms=missing_terms,
        claimed_anonymous_user=False,
    )


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

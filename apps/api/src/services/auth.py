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

# Kakao Sync 동의는 우리 내부 약관 동의와 source/version 으로 분리 저장한다
# (AGENTS §4.7 #5 봉인 / terms_consents.source CHECK 의 'kakao_sync').
KAKAO_SYNC_TERMS_SOURCE = "kakao_sync"
KAKAO_SYNC_TERMS_VERSION = "kakao_sync"

# 만 14세 이상 자기확인(개인정보보호법) — 생년월일은 수집하지 않고 체크박스 attestation 만
# terms_consents 에 timestamp 와 함께 남긴다(감사 추적). 법정 요건이라 env
# (KAKAO_SYNC_REQUIRED_TERM_TAGS)로 끌 수 없게 코드에 고정하며, 이메일 가입
# (services/account.py)과 OAuth 브리지/terms-accept 경로 모두에 공통 강제된다.
AGE_OVER_14_TERM_ID = "age_over_14"


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


async def record_kakao_sync_consent(user_id: uuid.UUID) -> list[str]:
    """Kakao Sync 로 가입한 사용자의 필수 약관 동의를 ``source='kakao_sync'`` 로 기록.

    AGENTS §4.7 #5: Kakao 는 자체 동의 화면(Kakao Sync)에서 필수 약관 동의를 받으므로,
    우리 내부 약관 화면(``/auth/terms``)을 중복 노출하지 않고 Kakao 동의를 별도 source
    로 저장한다. 따라서 Supabase Kakao 브리지 로그인 시 필수 태그(``kakao_sync_required_
    term_tags``)에 대한 동의 row 를 upsert 한 뒤 잔여 누락 약관을 반환한다.

    한계(후속 트랙): 사용자가 Kakao 측에서 *어떤* 태그에 동의했는지의 정밀 검증은
    Kakao ``/v2/user/service_terms`` API + 관리자 키로만 가능하다(ADR-0004 rev8 reconciliation
    / ``POST /auth/terms/kakao-sync`` 감사 스텁). 본 함수는 필수 태그 동의를 baseline 으로
    기록하고, 태그 단위 정합/불일치 audit 은 그 트랙이 담당한다.

    이미 ``internal_signup`` 으로 받은 동의가 있어도 version 이 다르므로 충돌 없이 공존하며,
    재호출은 ``on_conflict_do_nothing`` 으로 idempotent 하다.

    예외: ``age_over_14`` 는 Kakao Sync 가 대신 동의할 수 없는 항목(법정 자기확인)이라
    auto-record 에서 제외한다 — missing 으로 남아 사용자가 ``/auth/terms`` 에서 직접
    확인하게 된다.
    """

    settings = get_settings()
    # 만 14세 확인은 사용자가 우리 약관 화면에서 직접 체크해야 하므로 Kakao Sync
    # 자동 동의 기록 대상에서 제외한다 (missing_required_terms 에 남아 /auth/terms 라우팅).
    required_terms = [
        term_id
        for term_id in _required_term_ids(settings)
        if term_id != AGE_OVER_14_TERM_ID
    ]
    async with get_engine().begin() as conn:
        if required_terms:
            consent_rows = [
                {
                    "user_id": user_id,
                    "term_id": term_id,
                    "version": KAKAO_SYNC_TERMS_VERSION,
                    "source": KAKAO_SYNC_TERMS_SOURCE,
                    "agreed_at": sa.func.now(),
                    "updated_at": sa.func.now(),
                }
                for term_id in required_terms
            ]
            await conn.execute(
                pg_insert(TermsConsent)
                .values(consent_rows)
                .on_conflict_do_nothing(
                    index_elements=[
                        TermsConsent.user_id,
                        TermsConsent.term_id,
                        TermsConsent.version,
                    ],
                )
            )
        missing_terms = await _missing_required_terms(conn, user_id, settings)
    return missing_terms


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
    # age_over_14 는 법정 요건(개인정보보호법)이라 env(KAKAO_SYNC_REQUIRED_TERM_TAGS)로
    # 끌 수 없게 코드에 고정한다 — 이메일/OAuth 모든 가입 경로에서 항상 필수.
    return list(
        dict.fromkeys([*settings.kakao_sync_required_term_tags, AGE_OVER_14_TERM_ID])
    )

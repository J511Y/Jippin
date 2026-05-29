from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..config import get_settings
from ..db import get_engine
from ..auth.providers import OAuthProvider, ProviderProfile
from ..models import AnonymousUser, ExternalSsoAccount, TermsConsent, User


@dataclass(frozen=True)
class AnonymousUserResult:
    anonymous_user_id: uuid.UUID
    reused: bool


@dataclass(frozen=True)
class OAuthLoginResult:
    user_id: uuid.UUID
    signup_completed: bool
    claimed_anonymous_user_id: uuid.UUID | None


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
                        TermsConsent.source,
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

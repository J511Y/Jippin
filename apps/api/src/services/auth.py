from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from ..config import get_settings
from ..db import get_engine
from ..models import AnonymousUser


@dataclass(frozen=True)
class AnonymousUserResult:
    anonymous_user_id: uuid.UUID
    reused: bool


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

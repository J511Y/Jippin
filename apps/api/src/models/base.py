"""Shared SQLAlchemy model base and audit column mixins."""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import MetaData
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp for Python-side ORM defaults."""

    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base for all ORM models with deterministic constraint/index names."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class CreatedAtMixin:
    """Adds a UTC-aware creation timestamp."""

    created_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=sa.func.now(),
    )


class TimestampMixin(CreatedAtMixin):
    """Adds UTC-aware creation and update timestamps."""

    updated_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=sa.func.now(),
    )


class CreatedByMixin(CreatedAtMixin):
    """Adds a creation timestamp and nullable creator identifier.

    AUTH user storage is not finalized yet, so creator identifiers stay as text
    without a foreign key until the user table contract is sealed.
    """

    created_by: Mapped[str | None] = mapped_column(sa.Text)


class AuditMixin(TimestampMixin):
    """Adds timestamps plus nullable creator/updater identifiers."""

    created_by: Mapped[str | None] = mapped_column(sa.Text)
    updated_by: Mapped[str | None] = mapped_column(sa.Text)


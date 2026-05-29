from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin

EXTERNAL_SSO_PROVIDER_VALUES = ("kakao", "naver", "google")

external_sso_provider_enum = postgresql.ENUM(
    *EXTERNAL_SSO_PROVIDER_VALUES,
    name="external_sso_provider",
    native_enum=True,
    create_type=True,
)


class User(TimestampMixin, Base):
    """OAuth-only user account. Password columns are intentionally forbidden."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    email: Mapped[str | None] = mapped_column(sa.Text)
    display_name: Mapped[str | None] = mapped_column(sa.Text)
    profile_image_url: Mapped[str | None] = mapped_column(sa.Text)
    role: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        server_default=sa.text("'user'"),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True)
    )


class AnonymousUser(TimestampMixin, Base):
    """Anonymous pre-review actor that can later be converted to a User."""

    __tablename__ = "anonymous_users"

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    converted_user_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    converted_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True)
    )


class ExternalSsoAccount(TimestampMixin, Base):
    """Provider account linked to a local OAuth-only user."""

    __tablename__ = "external_sso_accounts"
    __table_args__ = (
        sa.UniqueConstraint("provider", "provider_subject"),
        sa.UniqueConstraint("user_id", "provider"),
    )

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.Identity(),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(external_sso_provider_enum, nullable=False)
    provider_subject: Mapped[str] = mapped_column(sa.Text, nullable=False)
    email: Mapped[str | None] = mapped_column(sa.Text)
    display_name: Mapped[str | None] = mapped_column(sa.Text)
    profile_image_url: Mapped[str | None] = mapped_column(sa.Text)
    raw_profile: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )


class Term(TimestampMixin, Base):
    """Versioned legal term shown during signup or captured from Kakao Sync."""

    __tablename__ = "terms"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    title: Mapped[str] = mapped_column(sa.Text, nullable=False)
    body_url: Mapped[str | None] = mapped_column(sa.Text)
    is_required: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("true"),
    )
    effective_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    retired_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True)
    )


class UserTermConsent(TimestampMixin, Base):
    """Audit row for a user's consent to a specific term version."""

    __tablename__ = "user_term_consents"
    __table_args__ = (
        sa.CheckConstraint(
            "source IN ('kakao_sync', 'internal_signup')",
            name="user_term_consents_source_allowed",
        ),
        sa.UniqueConstraint("user_id", "term_id"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    term_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("terms.id"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(sa.Text, nullable=False)
    agreed_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    raw: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )


sa.Index(None, AnonymousUser.last_seen_at)

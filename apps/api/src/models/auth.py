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
    """OAuth-only user account; role authorization is separate from lifecycle status."""

    __tablename__ = "users"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'deleted')",
            name="users_status_allowed",
        ),
    )

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
    status: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        server_default=sa.text("'active'"),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True)
    )


class AnonymousUser(TimestampMixin, Base):
    """Anonymous pre-review actor. Only HMAC IP/UA hashes are stored."""

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
    ip_hash: Mapped[bytes | None] = mapped_column(postgresql.BYTEA)
    ua_hash: Mapped[bytes | None] = mapped_column(postgresql.BYTEA)
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
    provider_email: Mapped[str | None] = mapped_column(sa.Text)
    linked_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    display_name: Mapped[str | None] = mapped_column(sa.Text)
    profile_image_url: Mapped[str | None] = mapped_column(sa.Text)


class TermsConsent(TimestampMixin, Base):
    """Canonical consent row plus TimestampMixin audit columns outside ADR-0003."""

    __tablename__ = "terms_consents"
    __table_args__ = (
        sa.CheckConstraint(
            "source IN ('kakao_sync', 'internal_signup')",
            name="terms_consents_source_allowed",
        ),
        sa.UniqueConstraint("user_id", "term_id", "version", "source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    term_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    source: Mapped[str] = mapped_column(sa.Text, nullable=False)
    agreed_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


sa.Index(None, AnonymousUser.last_seen_at)

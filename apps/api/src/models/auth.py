from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    """Application profile keyed by Supabase Auth's ``auth.users.id``."""

    __tablename__ = "users"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'deleted')",
            name="users_status_allowed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("auth.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
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


class TermsConsent(TimestampMixin, Base):
    """Product consent audit row keyed by Supabase Auth user id."""

    __tablename__ = "terms_consents"
    __table_args__ = (
        sa.CheckConstraint(
            "source IN ('kakao_sync', 'internal_signup')",
            name="terms_consents_source_allowed",
        ),
        sa.UniqueConstraint("user_id", "term_id", "version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("auth.users.id", ondelete="CASCADE"),
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

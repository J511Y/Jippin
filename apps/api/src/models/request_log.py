from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base


class RequestLog(Base):
    """Raw API request/response log row for later middleware ingestion."""

    __tablename__ = "request_logs"

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        index=True,
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    is_anonymous_user: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    user_id: Mapped[str | None] = mapped_column(sa.Text)
    device_id: Mapped[str | None] = mapped_column(sa.Text)
    version: Mapped[str | None] = mapped_column(sa.Text)
    device: Mapped[str | None] = mapped_column(sa.Text)
    country: Mapped[str | None] = mapped_column(sa.Text)
    region: Mapped[str | None] = mapped_column(sa.Text)
    ip_addrs: Mapped[list[str]] = mapped_column(
        postgresql.ARRAY(sa.Text),
        nullable=False,
        server_default=sa.text("'{}'::text[]"),
    )
    last_ip: Mapped[str | None] = mapped_column(
        postgresql.INET,
    )
    url: Mapped[str] = mapped_column(sa.Text, nullable=False)
    parameter: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    method: Mapped[str] = mapped_column(sa.Text, nullable=False)
    body: Mapped[dict[str, object] | None] = mapped_column(postgresql.JSONB)
    response_code: Mapped[int] = mapped_column(sa.Integer, nullable=False, index=True)
    response_message: Mapped[str | None] = mapped_column(sa.Text)
    error_code: Mapped[str | None] = mapped_column(sa.Text)
    duration_ms: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(sa.Text)
    referrer: Mapped[str | None] = mapped_column(sa.Text)


sa.Index(None, RequestLog.user_id, RequestLog.created_at.desc())

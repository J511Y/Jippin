from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, CreatedAtMixin, TimestampMixin


def uuid_pk():
    return mapped_column(
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def auth_user_fk(ondelete: str = "CASCADE") -> sa.ForeignKey:
    return sa.ForeignKey("auth.users.id", ondelete=ondelete)


class Floorplan(TimestampMixin, Base):
    """Reusable candidate floorplan catalog metadata."""

    __tablename__ = "floorplans"
    __table_args__ = (
        sa.CheckConstraint(
            "source IN ('internal', 'external_candidate', 'promoted_upload')",
            name="floorplans_source_allowed",
        ),
        sa.CheckConstraint(
            "visibility IN ('public_catalog', 'admin_only', 'private')",
            name="floorplans_visibility_allowed",
        ),
        sa.CheckConstraint(
            "quality_status IN ('unverified', 'verified', 'rejected', 'needs_review')",
            name="floorplans_quality_status_allowed",
        ),
        sa.Index(None, "apartment_name", "building_dong", "size_type"),
        sa.Index(None, "source", "quality_status"),
        sa.Index(None, "created_by", sa.text("created_at DESC")),
        sa.Index(
            "uq_floorplans_promoted_from_upload_id_not_null",
            "promoted_from_upload_id",
            unique=True,
            postgresql_where=sa.text("promoted_from_upload_id IS NOT NULL"),
        ),
        sa.Index(
            None,
            "address_fingerprint",
            postgresql_where=sa.text("address_fingerprint IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        auth_user_fk("SET NULL"),
    )
    source: Mapped[str] = mapped_column(sa.Text, nullable=False)
    visibility: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        server_default=sa.text("'admin_only'"),
    )
    apartment_name: Mapped[str | None] = mapped_column(sa.Text)
    building_dong: Mapped[str | None] = mapped_column(sa.Text)
    size_type: Mapped[str | None] = mapped_column(sa.Text)
    exclusive_area_m2: Mapped[float | None] = mapped_column(sa.Numeric(8, 2))
    layout_family: Mapped[str | None] = mapped_column(sa.Text)
    address_fingerprint: Mapped[str | None] = mapped_column(sa.Text)
    promoted_from_upload_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("floorplan_uploads.id", ondelete="SET NULL"),
    )
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        postgresql.JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    quality_status: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        server_default=sa.text("'unverified'"),
    )


class Session(TimestampMixin, Base):
    """One pre-review workflow session owned by a Supabase Auth user."""

    __tablename__ = "sessions"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ("
            "'draft', 'address_ready', 'floorplan_selected', 'analyzing', "
            "'awaiting_overlay', 'collecting_info', 'ready_for_rule', "
            "'report_ready', 'handoff', 'expired', 'deleted'"
            ")",
            name="sessions_status_allowed",
        ),
        sa.CheckConstraint(
            "completion_decision IS NULL OR completion_decision IN ("
            "'ASK_MORE', 'REQUEST_OVERLAY_REVIEW', 'PROCEED_RULE', "
            "'HOLD_OR_HANDOFF'"
            ")",
            name="sessions_completion_decision_allowed",
        ),
        sa.Index(None, "user_id", sa.text("created_at DESC")),
        sa.Index(None, "status", "last_activity_at"),
        sa.Index(None, "address_id"),
        sa.Index(None, "selected_floorplan_id"),
        sa.Index(None, "selected_floorplan_upload_id"),
        sa.Index(None, "selected_floorplan_asset_id"),
        sa.Index(
            "ix_sessions_expires_at_active",
            "expires_at",
            postgresql_where=sa.text("status NOT IN ('expired', 'deleted')"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        auth_user_fk(),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        server_default=sa.text("'draft'"),
    )
    address_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("session_addresses.id", ondelete="SET NULL"),
    )
    selected_floorplan_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("floorplans.id", ondelete="SET NULL"),
    )
    selected_floorplan_upload_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("floorplan_uploads.id", ondelete="SET NULL"),
    )
    selected_floorplan_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("floorplan_assets.id", ondelete="SET NULL"),
    )
    judgment_schema: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    judgment_schema_version: Mapped[str | None] = mapped_column(sa.Text)
    completion_decision: Mapped[str | None] = mapped_column(sa.Text)
    last_activity_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True)
    )


class SessionAddress(CreatedAtMixin, Base):
    """Address and unit identity normalized for a review session."""

    __tablename__ = "session_addresses"
    __table_args__ = (
        sa.UniqueConstraint("session_id"),
        sa.Index(None, "user_id", sa.text("created_at DESC")),
        sa.Index(None, "apartment_name", "building_dong", "size_type"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        auth_user_fk(),
        nullable=False,
    )
    road_address: Mapped[str | None] = mapped_column(sa.Text)
    jibun_address: Mapped[str | None] = mapped_column(sa.Text)
    apartment_name: Mapped[str | None] = mapped_column(sa.Text)
    building_dong: Mapped[str | None] = mapped_column(sa.Text)
    unit_ho: Mapped[str | None] = mapped_column(sa.Text)
    floor_no: Mapped[int | None] = mapped_column(sa.Integer)
    exclusive_area_m2: Mapped[float | None] = mapped_column(sa.Numeric(8, 2))
    size_type: Mapped[str | None] = mapped_column(sa.Text)
    building_identity: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    address_provider: Mapped[str | None] = mapped_column(sa.Text)
    normalized_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True)
    )


class FloorplanUpload(TimestampMixin, Base):
    """User-uploaded floorplan record scoped to one review session."""

    __tablename__ = "floorplan_uploads"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ("
            "'uploaded', 'scan_pending', 'scan_failed', 'ready_for_processing', "
            "'processing', 'processed', 'rejected', 'promoted_to_catalog'"
            ")",
            name="floorplan_uploads_status_allowed",
        ),
        sa.Index(None, "session_id", sa.text("created_at DESC")),
        sa.Index(None, "user_id", sa.text("created_at DESC")),
        sa.Index(None, "status", sa.text("created_at DESC")),
        sa.Index(None, "original_asset_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        auth_user_fk(),
        nullable=False,
    )
    original_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("floorplan_assets.id", ondelete="SET NULL"),
    )
    status: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        server_default=sa.text("'uploaded'"),
    )
    file_name: Mapped[str | None] = mapped_column(sa.Text)
    source_note: Mapped[str | None] = mapped_column(sa.Text)
    upload_metadata: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )


class FloorplanAsset(TimestampMixin, Base):
    """R2/S3 object metadata for floorplan and report artifacts."""

    __tablename__ = "floorplan_assets"
    __table_args__ = (
        sa.CheckConstraint(
            "kind IN ("
            "'original', 'thumbnail', 'preview', 'masked', 'ocr_debug', "
            "'segmentation_mask', 'overlay', 'report_pdf'"
            ")",
            name="floorplan_assets_kind_allowed",
        ),
        sa.CheckConstraint(
            "storage_provider IN ('r2', 's3')",
            name="floorplan_assets_storage_provider_allowed",
        ),
        sa.UniqueConstraint("storage_provider", "bucket", "object_key"),
        sa.Index(None, "session_id", sa.text("created_at DESC")),
        sa.Index(None, "user_id", sa.text("created_at DESC")),
        sa.Index(None, "floorplan_id"),
        sa.Index(None, "upload_id"),
        sa.Index(None, "kind", sa.text("created_at DESC")),
        sa.Index(None, "sha256", postgresql_where=sa.text("sha256 IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("sessions.id", ondelete="CASCADE"),
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        auth_user_fk(),
    )
    floorplan_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("floorplans.id", ondelete="SET NULL"),
    )
    upload_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("floorplan_uploads.id", ondelete="CASCADE"),
    )
    kind: Mapped[str] = mapped_column(sa.Text, nullable=False)
    storage_provider: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        server_default=sa.text("'r2'"),
    )
    bucket: Mapped[str] = mapped_column(sa.Text, nullable=False)
    object_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    content_type: Mapped[str | None] = mapped_column(sa.Text)
    byte_size: Mapped[int | None] = mapped_column(sa.BigInteger)
    sha256: Mapped[str | None] = mapped_column(sa.Text)
    width_px: Mapped[int | None] = mapped_column(sa.Integer)
    height_px: Mapped[int | None] = mapped_column(sa.Integer)
    page_count: Mapped[int | None] = mapped_column(sa.Integer)
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        postgresql.JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )


class FloorplanCandidate(CreatedAtMixin, Base):
    """A candidate floorplan snapshot presented within a session."""

    __tablename__ = "floorplan_candidates"
    __table_args__ = (
        sa.UniqueConstraint("session_id", "lookup_revision", "rank"),
        sa.Index(None, "session_id", "lookup_revision", "rank"),
        sa.Index(None, "user_id", sa.text("created_at DESC")),
        sa.Index(None, "floorplan_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        auth_user_fk(),
        nullable=False,
    )
    floorplan_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("floorplans.id", ondelete="SET NULL"),
    )
    lookup_revision: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("1"),
    )
    rank: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    confidence: Mapped[float | None] = mapped_column(sa.Numeric(5, 4))
    candidate_snapshot: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    presented_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    selected_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True)
    )
    rejected_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True)
    )


class ChatMessage(CreatedAtMixin, Base):
    """Session transcript message."""

    __tablename__ = "chat_messages"
    __table_args__ = (
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system', 'tool')",
            name="chat_messages_role_allowed",
        ),
        sa.UniqueConstraint("session_id", "message_order"),
        sa.Index(None, "session_id", "message_order"),
        sa.Index(None, "user_id", sa.text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        auth_user_fk(),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(sa.Text, nullable=False)
    content: Mapped[str | None] = mapped_column(sa.Text)
    content_json: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    message_order: Mapped[int] = mapped_column(sa.Integer, nullable=False)


class ChatToolCall(CreatedAtMixin, Base):
    """Audit row for tool calls backing chat and A2UI orchestration."""

    __tablename__ = "chat_tool_calls"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('started', 'succeeded', 'failed', 'cancelled', 'timeout')",
            name="chat_tool_calls_status_allowed",
        ),
        sa.Index(None, "session_id", sa.text("created_at DESC")),
        sa.Index(None, "user_id", sa.text("created_at DESC")),
        sa.Index(None, "message_id"),
        sa.Index(None, "tool_name", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        auth_user_fk(),
        nullable=False,
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("chat_messages.id", ondelete="SET NULL"),
    )
    tool_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        server_default=sa.text("'started'"),
    )
    input: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    output: Mapped[dict[str, object] | None] = mapped_column(postgresql.JSONB)
    error_code: Mapped[str | None] = mapped_column(sa.Text)
    error_message: Mapped[str | None] = mapped_column(sa.Text)
    duration_ms: Mapped[int | None] = mapped_column(sa.Integer)
    started_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True)
    )


class ProcessingJob(TimestampMixin, Base):
    """Observable async processing job for queues/workers."""

    __tablename__ = "processing_jobs"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', "
            "'cancelled', 'retrying')",
            name="processing_jobs_status_allowed",
        ),
        sa.CheckConstraint(
            "attempts >= 0 AND max_attempts > 0 AND attempts <= max_attempts",
            name="processing_jobs_attempts_allowed",
        ),
        sa.Index(None, "session_id", sa.text("created_at DESC")),
        sa.Index(None, "user_id", sa.text("created_at DESC")),
        sa.Index(
            "ix_processing_jobs_ready_queue",
            "priority",
            "run_after",
            "created_at",
            postgresql_where=sa.text("status IN ('queued', 'retrying')"),
        ),
        sa.Index(
            "ix_processing_jobs_locked_running",
            "locked_at",
            postgresql_where=sa.text("status = 'running'"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("sessions.id", ondelete="CASCADE"),
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        auth_user_fk(),
    )
    job_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        server_default=sa.text("'queued'"),
    )
    priority: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("100"),
    )
    attempts: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
    )
    max_attempts: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("3"),
    )
    payload: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    result: Mapped[dict[str, object] | None] = mapped_column(postgresql.JSONB)
    error_code: Mapped[str | None] = mapped_column(sa.Text)
    error_message: Mapped[str | None] = mapped_column(sa.Text)
    run_after: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True)
    )
    locked_by: Mapped[str | None] = mapped_column(sa.Text)
    started_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True)
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True)
    )


class WebhookDelivery(TimestampMixin, Base):
    """Webhook delivery attempts and response metadata."""

    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('pending', 'delivering', 'delivered', 'failed', 'cancelled')",
            name="webhook_deliveries_status_allowed",
        ),
        sa.Index(None, "session_id", sa.text("created_at DESC")),
        sa.Index(None, "user_id", sa.text("created_at DESC")),
        sa.Index(
            "ix_webhook_deliveries_retry",
            "next_retry_at",
            postgresql_where=sa.text("status IN ('pending', 'failed')"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("sessions.id", ondelete="CASCADE"),
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        auth_user_fk(),
    )
    event_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    endpoint_url: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        server_default=sa.text("'pending'"),
    )
    attempt_count: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
    )
    payload: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    response_status: Mapped[int | None] = mapped_column(sa.Integer)
    response_body: Mapped[str | None] = mapped_column(sa.Text)
    error_message: Mapped[str | None] = mapped_column(sa.Text)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True)
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True)
    )


class ScheduledTaskRun(CreatedAtMixin, Base):
    """Cron/scheduled task execution audit row."""

    __tablename__ = "scheduled_task_runs"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('started', 'succeeded', 'failed', 'skipped')",
            name="scheduled_task_runs_status_allowed",
        ),
        sa.Index("ix_scheduled_task_runs_task_key_started_at", "task_key", "started_at"),
        sa.Index("ix_scheduled_task_runs_status_started_at", "status", "started_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    task_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        server_default=sa.text("'started'"),
    )
    lock_key: Mapped[str | None] = mapped_column(sa.Text)
    started_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True)
    )
    duration_ms: Mapped[int | None] = mapped_column(sa.Integer)
    summary: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    error_message: Mapped[str | None] = mapped_column(sa.Text)


class ExternalSyncRecord(TimestampMixin, Base):
    """Provider/resource sync cursor and status."""

    __tablename__ = "external_sync_records"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('pending', 'synced', 'failed', 'stale', 'ignored')",
            name="external_sync_records_status_allowed",
        ),
        sa.UniqueConstraint("provider", "resource_type", "resource_key"),
        sa.Index(None, "session_id", sa.text("created_at DESC")),
        sa.Index(None, "user_id", sa.text("created_at DESC")),
        sa.Index(None, "status", "last_synced_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("sessions.id", ondelete="CASCADE"),
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        auth_user_fk(),
    )
    provider: Mapped[str] = mapped_column(sa.Text, nullable=False)
    resource_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    resource_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        server_default=sa.text("'pending'"),
    )
    external_updated_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True)
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True)
    )
    cursor_value: Mapped[str | None] = mapped_column(sa.Text)
    payload: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    error_message: Mapped[str | None] = mapped_column(sa.Text)

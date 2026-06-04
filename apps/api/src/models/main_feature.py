from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, CreatedAtMixin, TimestampMixin


jsonb_empty_object = sa.text("'{}'::jsonb")
jsonb_empty_array = sa.text("'[]'::jsonb")


class Session(TimestampMixin, Base):
    """A single pre-check workflow owned by a Supabase Auth user."""

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
        server_default=jsonb_empty_object,
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
    """Normalized address and unit identifiers captured for a session."""

    __tablename__ = "session_addresses"

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    road_address: Mapped[str | None] = mapped_column(sa.Text)
    jibun_address: Mapped[str | None] = mapped_column(sa.Text)
    apartment_name: Mapped[str | None] = mapped_column(sa.Text)
    building_dong: Mapped[str | None] = mapped_column(sa.Text)
    unit_ho: Mapped[str | None] = mapped_column(sa.Text)
    floor_no: Mapped[int | None] = mapped_column(sa.Integer)
    exclusive_area_m2: Mapped[Decimal | None] = mapped_column(sa.Numeric(8, 2))
    size_type: Mapped[str | None] = mapped_column(sa.Text)
    building_identity: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        server_default=jsonb_empty_object,
    )
    address_provider: Mapped[str | None] = mapped_column(sa.Text)
    normalized_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True)
    )


class Floorplan(TimestampMixin, Base):
    """Reusable catalog floorplan candidate metadata."""

    __tablename__ = "floorplans"
    __table_args__ = (
        sa.CheckConstraint(
            "source IN ('internal', 'external_candidate', 'promoted_upload')",
            name="floorplans_source_allowed",
        ),
        sa.CheckConstraint(
            "visibility IN ('public_catalog', 'admin_only')",
            name="floorplans_visibility_allowed",
        ),
        sa.CheckConstraint(
            "quality_status IN ('unverified', 'verified', 'rejected', 'needs_review')",
            name="floorplans_quality_status_allowed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("auth.users.id", ondelete="SET NULL"),
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
    exclusive_area_m2: Mapped[Decimal | None] = mapped_column(sa.Numeric(8, 2))
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
        server_default=jsonb_empty_object,
    )
    quality_status: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        server_default=sa.text("'unverified'"),
    )


class FloorplanUpload(TimestampMixin, Base):
    """A user-uploaded floorplan tied to one pre-check session."""

    __tablename__ = "floorplan_uploads"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ("
            "'uploaded', 'scan_pending', 'scan_failed', 'ready_for_processing', "
            "'processing', 'processed', 'rejected', 'promoted_to_catalog'"
            ")",
            name="floorplan_uploads_status_allowed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("auth.users.id", ondelete="CASCADE"),
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
        server_default=jsonb_empty_object,
    )


class FloorplanAsset(TimestampMixin, Base):
    """R2/S3 object metadata. Signed URLs and tokens are intentionally absent."""

    __tablename__ = "floorplan_assets"
    __table_args__ = (
        sa.CheckConstraint(
            "kind IN ("
            "'original', 'thumbnail', 'preview', 'masked', 'ocr_debug', "
            "'segmentation_mask', 'overlay', 'report_pdf', 'report_image'"
            ")",
            name="floorplan_assets_kind_allowed",
        ),
        sa.CheckConstraint(
            "storage_provider IN ('r2', 's3')",
            name="floorplan_assets_storage_provider_allowed",
        ),
        sa.CheckConstraint(
            "scan_status IN ('pending', 'clean', 'infected', 'failed', 'not_required')",
            name="floorplan_assets_scan_status_allowed",
        ),
        sa.CheckConstraint("byte_size >= 0", name="floorplan_assets_byte_size_nonnegative"),
        sa.UniqueConstraint("bucket", "object_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    floorplan_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("floorplans.id", ondelete="CASCADE"),
    )
    floorplan_upload_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("floorplan_uploads.id", ondelete="CASCADE"),
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("sessions.id", ondelete="CASCADE"),
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("auth.users.id", ondelete="CASCADE"),
    )
    kind: Mapped[str] = mapped_column(sa.Text, nullable=False)
    storage_provider: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        server_default=sa.text("'r2'"),
    )
    bucket: Mapped[str] = mapped_column(sa.Text, nullable=False)
    object_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    content_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    sha256_hex: Mapped[str | None] = mapped_column(sa.Text)
    width_px: Mapped[int | None] = mapped_column(sa.Integer)
    height_px: Mapped[int | None] = mapped_column(sa.Integer)
    page_count: Mapped[int | None] = mapped_column(sa.Integer)
    scan_status: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        server_default=sa.text("'pending'"),
    )


class FloorplanCandidate(CreatedAtMixin, Base):
    """A candidate snapshot actually presented to the user in a session."""

    __tablename__ = "floorplan_candidates"
    __table_args__ = (
        sa.CheckConstraint("lookup_revision > 0", name="floorplan_candidates_lookup_revision_positive"),
        sa.CheckConstraint("rank > 0", name="floorplan_candidates_rank_positive"),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="floorplan_candidates_confidence_range",
        ),
        sa.UniqueConstraint("session_id", "lookup_revision", "floorplan_id"),
        sa.UniqueConstraint("session_id", "lookup_revision", "rank"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    lookup_revision: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("1"),
    )
    floorplan_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("floorplans.id", ondelete="SET NULL"),
    )
    rank: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(sa.Numeric(5, 4), nullable=False)
    match_reasons: Mapped[list[object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        server_default=jsonb_empty_array,
    )
    lookup_input: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        server_default=jsonb_empty_object,
    )
    floorplan_snapshot: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        server_default=jsonb_empty_object,
    )
    selected_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True)
    )
    rejected_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True)
    )


class ChatMessage(CreatedAtMixin, Base):
    """A2UI chat transcript row, with redaction state made explicit."""

    __tablename__ = "chat_messages"
    __table_args__ = (
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system', 'tool')",
            name="chat_messages_role_allowed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("auth.users.id", ondelete="SET NULL"),
    )
    role: Mapped[str] = mapped_column(sa.Text, nullable=False)
    content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    content_redacted: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("false"),
    )
    ui_components: Mapped[list[object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        server_default=jsonb_empty_array,
    )
    judgment_snapshot: Mapped[dict[str, object] | None] = mapped_column(
        postgresql.JSONB
    )
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        postgresql.JSONB,
        nullable=False,
        server_default=jsonb_empty_object,
    )


class ChatToolCall(Base):
    """Tool call ledger for CHAT/A2UI agents with redacted payload storage."""

    __tablename__ = "chat_tool_calls"
    __table_args__ = (
        sa.CheckConstraint(
            "tool_kind IN ("
            "'retrieval', 'db_query', 'external_api', 'ai_model', "
            "'rule_engine', 'render', 'notification', 'other'"
            ")",
            name="chat_tool_calls_tool_kind_allowed",
        ),
        sa.CheckConstraint(
            "status IN ('started', 'succeeded', 'failed', 'cancelled')",
            name="chat_tool_calls_status_allowed",
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="chat_tool_calls_duration_ms_nonnegative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("chat_messages.id", ondelete="SET NULL"),
    )
    parent_tool_call_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("chat_tool_calls.id", ondelete="SET NULL"),
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("auth.users.id", ondelete="SET NULL"),
    )
    tool_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    tool_kind: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        server_default=sa.text("'started'"),
    )
    input: Mapped[dict[str, object]] = mapped_column(
        postgresql.JSONB,
        nullable=False,
        server_default=jsonb_empty_object,
    )
    output: Mapped[dict[str, object] | None] = mapped_column(postgresql.JSONB)
    output_summary: Mapped[str | None] = mapped_column(sa.Text)
    error_code: Mapped[str | None] = mapped_column(sa.Text)
    error_message: Mapped[str | None] = mapped_column(sa.Text)
    duration_ms: Mapped[int | None] = mapped_column(sa.Integer)
    started_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True)
    )
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        postgresql.JSONB,
        nullable=False,
        server_default=jsonb_empty_object,
    )


sa.Index(None, Session.user_id, Session.created_at.desc())
sa.Index(None, Session.status, Session.last_activity_at)
sa.Index(None, Session.address_id)
sa.Index(None, Session.selected_floorplan_id)
sa.Index(None, Session.selected_floorplan_upload_id)
sa.Index(None, Session.selected_floorplan_asset_id)
sa.Index(
    "ix_sessions_expires_at_active",
    Session.expires_at,
    postgresql_where=Session.status.not_in(["expired", "deleted"]),
)

sa.Index(None, SessionAddress.user_id, SessionAddress.created_at.desc())
sa.Index(None, SessionAddress.apartment_name, SessionAddress.building_dong, SessionAddress.size_type)
sa.Index(None, SessionAddress.session_id)

sa.Index(None, Floorplan.apartment_name, Floorplan.building_dong, Floorplan.size_type)
sa.Index(None, Floorplan.source, Floorplan.quality_status)
sa.Index(None, Floorplan.created_by, Floorplan.created_at.desc())
sa.Index(
    "ix_floorplans_address_fingerprint_present",
    Floorplan.address_fingerprint,
    postgresql_where=Floorplan.address_fingerprint.is_not(None),
)
sa.Index(
    "uq_floorplans_promoted_from_upload_id_present",
    Floorplan.promoted_from_upload_id,
    unique=True,
    postgresql_where=Floorplan.promoted_from_upload_id.is_not(None),
)

sa.Index(None, FloorplanUpload.session_id, FloorplanUpload.created_at.desc())
sa.Index(None, FloorplanUpload.user_id, FloorplanUpload.created_at.desc())
sa.Index(None, FloorplanUpload.status, FloorplanUpload.created_at.desc())
sa.Index(None, FloorplanUpload.original_asset_id)

sa.Index(None, FloorplanAsset.floorplan_id, FloorplanAsset.kind)
sa.Index(None, FloorplanAsset.floorplan_upload_id, FloorplanAsset.kind)
sa.Index(None, FloorplanAsset.session_id, FloorplanAsset.kind)
sa.Index(None, FloorplanAsset.owner_user_id, FloorplanAsset.created_at.desc())
sa.Index(
    "ix_floorplan_assets_scan_status_pending_failed",
    FloorplanAsset.scan_status,
    FloorplanAsset.created_at,
    postgresql_where=FloorplanAsset.scan_status.in_(["pending", "failed"]),
)

sa.Index(
    None,
    FloorplanCandidate.session_id,
    FloorplanCandidate.lookup_revision,
    FloorplanCandidate.confidence.desc(),
)
sa.Index(None, FloorplanCandidate.floorplan_id)

sa.Index(None, ChatMessage.session_id, ChatMessage.created_at)
sa.Index(None, ChatMessage.user_id, ChatMessage.created_at.desc())

sa.Index(None, ChatToolCall.session_id, ChatToolCall.started_at)
sa.Index(None, ChatToolCall.message_id, ChatToolCall.started_at)
sa.Index(None, ChatToolCall.tool_name, ChatToolCall.started_at.desc())
sa.Index(None, ChatToolCall.status, ChatToolCall.started_at.desc())
sa.Index(None, ChatToolCall.parent_tool_call_id)
sa.Index(None, ChatToolCall.user_id)

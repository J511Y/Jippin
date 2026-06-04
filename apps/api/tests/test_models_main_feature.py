from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, Text, UniqueConstraint
from sqlalchemy.dialects import postgresql

from src.models import (
    Base,
    ChatMessage,
    ChatToolCall,
    ExternalSyncRecord,
    Floorplan,
    FloorplanAsset,
    FloorplanCandidate,
    FloorplanUpload,
    ProcessingJob,
    ScheduledTaskRun,
    Session,
    SessionAddress,
    WebhookDelivery,
)


PHASE_A_TABLES = {
    "sessions",
    "session_addresses",
    "floorplans",
    "floorplan_uploads",
    "floorplan_assets",
    "floorplan_candidates",
    "chat_messages",
    "chat_tool_calls",
    "processing_jobs",
    "webhook_deliveries",
    "scheduled_task_runs",
    "external_sync_records",
}


def _check_sql(table: object) -> dict[str, str]:
    return {
        constraint.name: str(constraint.sqltext)
        for constraint in table.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }


def _unique_columns(table: object) -> dict[str, tuple[str, ...]]:
    return {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in table.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _index_columns(table: object) -> dict[str, tuple[str, ...]]:
    return {
        index.name: tuple(column.name for column in index.columns)
        for index in table.__table__.indexes
        if isinstance(index, Index)
    }


def test_phase_a_tables_are_registered() -> None:
    assert PHASE_A_TABLES.issubset(Base.metadata.tables)


def test_user_owned_models_reference_supabase_auth_users() -> None:
    user_owned = [
        Session,
        SessionAddress,
        FloorplanUpload,
        FloorplanCandidate,
        ChatMessage,
        ChatToolCall,
    ]

    for model in user_owned:
        fk = next(iter(model.__table__.c.user_id.foreign_keys))
        assert fk.target_fullname == "auth.users.id"
        assert fk.ondelete == "CASCADE"
        assert model.__table__.c.user_id.nullable is False


def test_sessions_keep_anonymous_user_ownership_and_completion_contract() -> None:
    table = Session.__table__
    checks = _check_sql(Session)

    assert table.c.user_id.nullable is False
    assert isinstance(table.c.status.type, Text)
    assert table.c.status.server_default is not None
    assert "draft" in checks["ck_sessions_sessions_status_allowed"]
    assert (
        "REQUEST_OVERLAY_REVIEW"
        in checks["ck_sessions_sessions_completion_decision_allowed"]
    )
    assert isinstance(table.c.judgment_schema.type, postgresql.JSONB)
    assert "ix_sessions_expires_at_active" in _index_columns(Session)


def test_floorplan_catalog_is_separate_from_uploads_and_assets() -> None:
    checks = _check_sql(Floorplan)
    uniques = _unique_columns(FloorplanAsset)

    assert Floorplan.__table__.c.created_by.foreign_keys
    assert "promoted_upload" in checks["ck_floorplans_floorplans_source_allowed"]
    assert "public_catalog" in checks["ck_floorplans_floorplans_visibility_allowed"]
    assert FloorplanUpload.__table__.c.original_asset_id.foreign_keys
    assert FloorplanAsset.__table__.c.object_key.nullable is False
    assert uniques["uq_floorplan_assets_storage_provider_bucket_object_key"] == (
        "storage_provider",
        "bucket",
        "object_key",
    )


def test_floorplan_candidates_are_session_snapshots() -> None:
    uniques = _unique_columns(FloorplanCandidate)
    indexes = _index_columns(FloorplanCandidate)

    assert uniques["uq_floorplan_candidates_session_id_lookup_revision_rank"] == (
        "session_id",
        "lookup_revision",
        "rank",
    )
    assert indexes["ix_floorplan_candidates_session_id_lookup_revision_rank"] == (
        "session_id",
        "lookup_revision",
        "rank",
    )


def test_chat_transcript_and_tool_calls_are_split() -> None:
    message_checks = _check_sql(ChatMessage)
    tool_checks = _check_sql(ChatToolCall)

    assert "assistant" in message_checks["ck_chat_messages_chat_messages_role_allowed"]
    assert "timeout" in tool_checks["ck_chat_tool_calls_chat_tool_calls_status_allowed"]
    assert ChatToolCall.__table__.c.input.nullable is False
    assert isinstance(ChatToolCall.__table__.c.output.type, postgresql.JSONB)


def test_async_observability_tables_have_queue_retry_indexes() -> None:
    processing_indexes = _index_columns(ProcessingJob)
    webhook_indexes = _index_columns(WebhookDelivery)

    assert processing_indexes["ix_processing_jobs_ready_queue"] == (
        "priority",
        "run_after",
        "created_at",
    )
    assert processing_indexes["ix_processing_jobs_locked_running"] == ("locked_at",)
    assert webhook_indexes["ix_webhook_deliveries_retry"] == ("next_retry_at",)
    assert _index_columns(ScheduledTaskRun)[
        "ix_scheduled_task_runs_task_key_started_at"
    ] == ("task_key", "started_at")
    assert _unique_columns(ExternalSyncRecord)[
        "uq_external_sync_records_provider_resource_type_resource_key"
    ] == ("provider", "resource_type", "resource_key")

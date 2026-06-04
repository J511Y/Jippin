from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, Text, UniqueConstraint
from sqlalchemy.dialects import postgresql

from src.models import (
    Base,
    ChatMessage,
    ChatToolCall,
    Floorplan,
    FloorplanAsset,
    FloorplanCandidate,
    FloorplanUpload,
    Session,
    SessionAddress,
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
}


def test_phase_a_tables_are_registered() -> None:
    assert PHASE_A_TABLES.issubset(Base.metadata.tables)


def test_phase_a_user_owned_tables_reference_supabase_auth_users() -> None:
    fk_columns = [
        Session.__table__.c.user_id,
        SessionAddress.__table__.c.user_id,
        Floorplan.__table__.c.created_by,
        FloorplanUpload.__table__.c.user_id,
        FloorplanAsset.__table__.c.owner_user_id,
        ChatMessage.__table__.c.user_id,
        ChatToolCall.__table__.c.user_id,
    ]

    for column in fk_columns:
        fk = next(iter(column.foreign_keys))
        assert fk.target_fullname == "auth.users.id"

    assert next(iter(Session.__table__.c.user_id.foreign_keys)).ondelete == "CASCADE"
    assert Session.__table__.c.user_id.nullable is False
    assert FloorplanUpload.__table__.c.user_id.nullable is False


def test_floorplan_uploads_and_assets_do_not_shadow_catalog_or_signed_urls() -> None:
    upload_table = FloorplanUpload.__table__
    asset_table = FloorplanAsset.__table__

    assert next(iter(upload_table.c.session_id.foreign_keys)).target_fullname == "sessions.id"
    assert next(iter(upload_table.c.original_asset_id.foreign_keys)).target_fullname == (
        "floorplan_assets.id"
    )
    assert next(iter(asset_table.c.floorplan_upload_id.foreign_keys)).target_fullname == (
        "floorplan_uploads.id"
    )
    assert {"signed_url", "presigned_url", "access_token", "secret"}.isdisjoint(
        asset_table.c.keys()
    )
    assert isinstance(asset_table.c.object_key.type, Text)
    assert isinstance(asset_table.c.byte_size.type, BigInteger)


def test_floorplan_candidates_keep_presented_snapshot_contract() -> None:
    table = FloorplanCandidate.__table__
    unique_constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert unique_constraints[
        "uq_floorplan_candidates_session_id_lookup_revision_floorplan_id"
    ] == ("session_id", "lookup_revision", "floorplan_id")
    assert unique_constraints["uq_floorplan_candidates_session_id_lookup_revision_rank"] == (
        "session_id",
        "lookup_revision",
        "rank",
    )
    assert isinstance(table.c.match_reasons.type, postgresql.JSONB)
    assert isinstance(table.c.lookup_input.type, postgresql.JSONB)


def test_chat_tool_calls_store_redacted_payload_surfaces() -> None:
    table = ChatToolCall.__table__

    assert isinstance(table.c.input.type, postgresql.JSONB)
    assert table.c.input.nullable is False
    assert isinstance(table.c.output.type, postgresql.JSONB)
    assert "output_summary" in table.c
    assert "duration_ms" in table.c
    assert next(iter(table.c.message_id.foreign_keys)).target_fullname == "chat_messages.id"


def test_phase_a_status_values_use_text_check_constraints() -> None:
    expected_check_names = {
        "sessions": {
            "ck_sessions_sessions_status_allowed",
            "ck_sessions_sessions_completion_decision_allowed",
        },
        "floorplans": {
            "ck_floorplans_floorplans_source_allowed",
            "ck_floorplans_floorplans_visibility_allowed",
            "ck_floorplans_floorplans_quality_status_allowed",
        },
        "floorplan_uploads": {"ck_floorplan_uploads_floorplan_uploads_status_allowed"},
        "floorplan_assets": {
            "ck_floorplan_assets_floorplan_assets_kind_allowed",
            "ck_floorplan_assets_floorplan_assets_scan_status_allowed",
            "ck_floorplan_assets_floorplan_assets_storage_provider_allowed",
        },
        "chat_messages": {"ck_chat_messages_chat_messages_role_allowed"},
        "chat_tool_calls": {
            "ck_chat_tool_calls_chat_tool_calls_tool_kind_allowed",
            "ck_chat_tool_calls_chat_tool_calls_status_allowed",
        },
    }

    for table_name, check_names in expected_check_names.items():
        table = Base.metadata.tables[table_name]
        actual = {
            constraint.name
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint)
        }
        assert check_names.issubset(actual)


def test_all_phase_a_foreign_key_columns_are_indexed() -> None:
    for table_name in PHASE_A_TABLES:
        table = Base.metadata.tables[table_name]
        indexed_columns = {
            column.name
            for index in table.indexes
            for column in index.columns
        }
        unique_columns = {
            column.name
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
            for column in constraint.columns
        }

        for column in table.c:
            if column.foreign_keys:
                assert column.name in indexed_columns | unique_columns, (
                    f"{table_name}.{column.name} is a foreign key without an index"
                )

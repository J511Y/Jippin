from __future__ import annotations

from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "supabase"
    / "migrations"
    / "20260604070000_0008_main_feature_phase_a.sql"
)


def test_phase_a_migration_exists_and_defines_expected_tables() -> None:
    sql = MIGRATION_PATH.read_text(encoding="utf-8")

    for table_name in [
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
    ]:
        assert f"create table public.{table_name}" in sql


def test_phase_a_migration_preserves_supabase_auth_as_owner_source() -> None:
    sql = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "references auth.users (id)" in sql
    assert "create table public.anonymous_users" not in sql
    assert "create table public.external_sso_accounts" not in sql
    assert "create table public.auth_identities" not in sql
    assert "password" not in sql.lower()


def test_phase_a_migration_enables_rls_with_auth_uid_pattern() -> None:
    sql = MIGRATION_PATH.read_text(encoding="utf-8")

    for table_name in [
        "sessions",
        "session_addresses",
        "floorplan_uploads",
        "floorplan_assets",
        "floorplan_candidates",
        "chat_messages",
        "chat_tool_calls",
        "processing_jobs",
    ]:
        assert f"alter table public.{table_name} enable row level security;" in sql

    assert "(select auth.uid())" in sql
    assert "status in ('queued', 'retrying')" in sql
    assert "where status = 'running'" in sql

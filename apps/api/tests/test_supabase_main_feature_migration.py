from __future__ import annotations

from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "supabase"
    / "migrations"
    / "20260604073000_0008_main_feature_phase_a.sql"
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


def migration_sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_phase_a_supabase_migration_creates_required_tables() -> None:
    sql = migration_sql()

    for table_name in PHASE_A_TABLES:
        assert f"create table public.{table_name}" in sql


def test_phase_a_supabase_migration_uses_auth_users_ownership() -> None:
    sql = migration_sql()

    assert "references auth.users (id)" in sql
    assert (
        "sessions (\n  id uuid not null default gen_random_uuid(),\n  user_id uuid not null"
        in sql
    )
    assert "floorplan_uploads (\n  id uuid not null default gen_random_uuid()," in sql
    assert "user_id uuid not null" in sql


def test_phase_a_supabase_migration_enables_rls_for_user_owned_tables() -> None:
    sql = migration_sql()

    for table_name in PHASE_A_TABLES:
        assert f"alter table public.{table_name} enable row level security;" in sql

    assert "(select auth.uid())" in sql


def test_public_catalog_rls_requires_verified_floorplans() -> None:
    sql = migration_sql()

    assert "visibility = 'public_catalog'\n      and quality_status = 'verified'" in sql
    assert (
        "f.visibility = 'public_catalog'\n            and f.quality_status = 'verified'"
        in sql
    )


def test_phase_a_supabase_migration_keeps_chat_tool_payload_columns() -> None:
    sql = migration_sql()

    assert "input jsonb not null default '{}'::jsonb" in sql
    assert "output jsonb" in sql
    assert "duration_ms integer" in sql
    assert "do not store provider tokens, signed urls, or raw pii" in sql


def test_phase_a_supabase_migration_does_not_reintroduce_legacy_auth_tables() -> None:
    sql = migration_sql()

    assert "create table public.anonymous_users" not in sql
    assert "create table public.external_sso_accounts" not in sql
    assert "password_hash" not in sql
    assert " password " not in sql

from __future__ import annotations

import re
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


def policy_sql(sql: str, policy_name: str) -> str:
    pattern = (
        rf"create policy {re.escape(policy_name)}\b"
        r".*?(?=\ncreate policy |\ncreate trigger |\Z)"
    )
    match = re.search(pattern, sql, flags=re.DOTALL)
    assert match is not None, f"policy {policy_name} not found"
    return match.group(0)


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


def test_floorplan_asset_public_catalog_read_is_select_only() -> None:
    sql = migration_sql()
    read_policy = policy_sql(sql, "floorplan_assets_owner_or_session_read")
    insert_policy = policy_sql(sql, "floorplan_assets_owner_or_session_insert")
    update_policy = policy_sql(sql, "floorplan_assets_owner_or_session_update")
    delete_policy = policy_sql(sql, "floorplan_assets_owner_or_session_delete")

    assert "\n  for select\n" in read_policy
    assert (
        "f.visibility = 'public_catalog'\n            and f.quality_status = 'verified'"
        in read_policy
    )
    assert "create policy floorplan_assets_owner_or_session_all" not in sql

    assert "\n  for insert\n" in insert_policy
    assert "\n  for update\n" in update_policy
    assert "\n  for delete\n" in delete_policy
    for mutation_policy in (insert_policy, update_policy, delete_policy):
        assert "owner_user_id = (select auth.uid())" in mutation_policy
        assert "floorplan_id is null" in mutation_policy
        assert "floorplan_upload_id is null" in mutation_policy
        assert "session_id is null" in mutation_policy
        assert "f.created_by = (select auth.uid())" in mutation_policy
        assert "f.visibility = 'admin_only'" in mutation_policy
        assert "u.user_id = (select auth.uid())" in mutation_policy
        assert "or f.created_by = (select auth.uid())" not in mutation_policy
        assert "visibility = 'public_catalog'" not in mutation_policy
        assert "quality_status = 'verified'" not in mutation_policy


def test_sessions_reference_pointers_are_guarded_by_trigger() -> None:
    sql = migration_sql()

    assert "create or replace function public.enforce_session_reference_scope()" in sql
    assert "create trigger trg_sessions_reference_scope" in sql
    assert "before insert or update of" in sql
    assert "sa.session_id = new.id" in sql
    assert "u.session_id = new.id" in sql
    assert "a.session_id = new.id" in sql
    assert (
        "f.visibility = 'public_catalog'\n          and f.quality_status = 'verified'"
        in sql
    )
    assert (
        "sessions.selected_floorplan_upload_id must reference a same-session upload"
        in sql
    )


def test_chat_browser_writes_are_limited_to_user_messages() -> None:
    sql = migration_sql()
    insert_policy = policy_sql(sql, "chat_messages_user_insert")
    update_policy = policy_sql(sql, "chat_messages_user_update")
    tool_read_policy = policy_sql(sql, "chat_tool_calls_session_owner_read")

    assert "create policy chat_messages_session_owner_all" not in sql
    assert "create policy chat_tool_calls_session_owner_all" not in sql
    assert "\n  for insert\n" in insert_policy
    assert "\n  for update\n" in update_policy
    assert "role = 'user'" in insert_policy
    assert "role = 'user'" in update_policy
    assert "user_id = (select auth.uid())" in insert_policy
    assert "user_id = (select auth.uid())" in update_policy
    assert "\n  for select\n" in tool_read_policy
    assert "create policy chat_tool_calls" in sql
    assert not re.search(
        r"create policy chat_tool_calls_\w+.*?\n  for (insert|update|delete|all)\n",
        sql,
        flags=re.DOTALL,
    )


def test_catalog_verification_is_not_user_mutable() -> None:
    sql = migration_sql()
    insert_policy = policy_sql(sql, "floorplans_owner_insert")
    update_policy = policy_sql(sql, "floorplans_owner_update")

    for mutation_policy in (insert_policy, update_policy):
        assert "created_by = (select auth.uid())" in mutation_policy
        assert "visibility = 'admin_only'" in mutation_policy
        assert "quality_status in ('unverified', 'rejected', 'needs_review')" in (
            mutation_policy
        )
        assert "quality_status = 'verified'" not in mutation_policy
        assert "visibility = 'public_catalog'" not in mutation_policy


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

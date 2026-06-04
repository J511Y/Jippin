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
    assert "and scan_status = 'pending'" in delete_policy
    assert "u.original_asset_id = public.floorplan_assets.id" in delete_policy
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


def test_selected_asset_matches_selected_source() -> None:
    sql = migration_sql()

    assert "new.selected_floorplan_id is null" in sql
    assert "or a.floorplan_id = new.selected_floorplan_id" in sql
    assert "new.selected_floorplan_upload_id is null" in sql
    assert "or a.floorplan_upload_id = new.selected_floorplan_upload_id" in sql
    assert "a.session_id = new.id" in sql
    assert "a.owner_user_id = new.user_id" in sql


def test_session_workflow_result_fields_are_service_controlled() -> None:
    sql = migration_sql()

    assert (
        "create or replace function public.prevent_session_client_service_field_mutation()"
        in sql
    )
    assert "create trigger trg_sessions_service_fields_client_guard" in sql
    assert "current_role <> 'authenticated'" in sql
    assert "new.last_activity_at := now()" in sql
    assert "new.status <> 'draft'" in sql
    assert "new.judgment_schema <> '{}'::jsonb" in sql
    assert "new.completion_decision is not null" in sql
    assert "new.status is distinct from old.status" in sql
    assert "new.judgment_schema is distinct from old.judgment_schema" in sql
    assert "new.completion_decision is distinct from old.completion_decision" in sql
    assert "new.last_activity_at is distinct from old.last_activity_at" in sql


def test_floorplan_catalog_promotion_is_service_owned() -> None:
    sql = migration_sql()
    insert_policy = policy_sql(sql, "floorplans_owner_insert")
    update_policy = policy_sql(sql, "floorplans_owner_update")
    delete_policy = policy_sql(sql, "floorplans_owner_delete")

    assert (
        "create or replace function public.prevent_floorplan_client_catalog_promotion()"
        in sql
    )
    assert "create trigger trg_floorplans_client_catalog_promotion_guard" in sql
    assert "old.source = 'promoted_upload'" in sql
    assert "old.visibility = 'public_catalog'" in sql
    assert "old.quality_status = 'verified'" in sql
    assert "old.promoted_from_upload_id is not null" in sql
    assert "new.promoted_from_upload_id is not null" in sql
    assert "authenticated clients cannot promote catalog floorplans" in sql

    for mutation_policy in (insert_policy, update_policy, delete_policy):
        assert "source in ('internal', 'external_candidate')" in mutation_policy
        assert "visibility = 'admin_only'" in mutation_policy
        assert "promoted_from_upload_id is null" in mutation_policy
        assert "quality_status in ('unverified', 'rejected', 'needs_review')" in (
            mutation_policy
        )
        assert "visibility = 'public_catalog'" not in mutation_policy
        assert "quality_status = 'verified'" not in mutation_policy


def test_session_address_session_and_user_are_client_immutable() -> None:
    sql = migration_sql()

    assert (
        "create or replace function public.prevent_session_address_client_reparent()"
        in sql
    )
    assert "create trigger trg_session_addresses_client_reparent_guard" in sql
    assert "current_role = 'authenticated'" in sql
    assert "new.session_id is distinct from old.session_id" in sql
    assert "new.user_id is distinct from old.user_id" in sql


def test_floorplan_upload_original_asset_is_same_owner_original() -> None:
    sql = migration_sql()

    assert (
        "create or replace function public.enforce_floorplan_upload_original_asset_scope()"
        in sql
    )
    assert "create trigger trg_floorplan_uploads_original_asset_scope" in sql
    assert "a.id = new.original_asset_id" in sql
    assert "a.session_id = new.session_id" in sql
    assert "a.owner_user_id = new.user_id" in sql
    assert "a.kind = 'original'" in sql


def test_floorplan_upload_status_is_service_controlled_after_initial_write() -> None:
    sql = migration_sql()

    assert (
        "create or replace function public.prevent_floorplan_upload_client_service_mutation()"
        in sql
    )
    assert "create trigger trg_floorplan_uploads_client_service_guard" in sql
    assert "new.status not in ('uploaded', 'scan_pending')" in sql
    assert "old.status not in ('uploaded', 'scan_pending')" in sql
    assert "new.status is distinct from old.status" in sql
    assert "authenticated clients cannot mutate service-controlled upload rows" in sql
    assert "authenticated clients cannot change service-controlled upload status" in sql


def test_floorplan_upload_policies_split_read_insert_update_without_delete() -> None:
    sql = migration_sql()
    read_policy = policy_sql(sql, "floorplan_uploads_owner_read")
    insert_policy = policy_sql(sql, "floorplan_uploads_owner_insert")
    update_policy = policy_sql(sql, "floorplan_uploads_owner_update")

    assert "create policy floorplan_uploads_owner_all" not in sql
    assert "\n  for select\n" in read_policy
    assert "\n  for insert\n" in insert_policy
    assert "\n  for update\n" in update_policy
    assert "status in ('uploaded', 'scan_pending')" in insert_policy
    assert "status in ('uploaded', 'scan_pending')" in update_policy
    upload_policy_modes = re.findall(
        r"create policy floorplan_uploads_\w+\n"
        r"  on public\.floorplan_uploads\n"
        r"  for (\w+)",
        sql,
    )
    assert sorted(upload_policy_modes) == ["insert", "select", "update"]


def test_asset_upload_session_comparison_is_outer_row_qualified() -> None:
    sql = migration_sql()

    assert "or u.session_id = session_id" not in sql
    assert (
        "public.floorplan_assets.session_id is null\n            or u.session_id = public.floorplan_assets.session_id"
        in sql
    )


def test_floorplan_candidates_are_read_only_for_clients() -> None:
    sql = migration_sql()
    read_policy = policy_sql(sql, "floorplan_candidates_session_owner_read")

    assert "create policy floorplan_candidates_session_owner_all" not in sql
    assert "\n  for select\n" in read_policy
    candidate_policy_names = re.findall(
        r"create policy (floorplan_candidates_\w+)", sql
    )
    assert candidate_policy_names == ["floorplan_candidates_session_owner_read"]


def test_chat_browser_writes_are_limited_to_user_messages() -> None:
    sql = migration_sql()
    insert_policy = policy_sql(sql, "chat_messages_user_insert")
    tool_read_policy = policy_sql(sql, "chat_tool_calls_session_owner_read")

    assert "create policy chat_messages_session_owner_all" not in sql
    assert "create policy chat_messages_user_update" not in sql
    assert "create policy chat_tool_calls_session_owner_all" not in sql
    assert "\n  for insert\n" in insert_policy
    assert "role = 'user'" in insert_policy
    assert "user_id = (select auth.uid())" in insert_policy
    assert "\n  for select\n" in tool_read_policy
    assert "create policy chat_tool_calls" in sql
    chat_policy_names = re.findall(r"create policy (chat_messages_\w+)", sql)
    assert sorted(chat_policy_names) == [
        "chat_messages_session_owner_read",
        "chat_messages_user_insert",
    ]
    assert (
        "create or replace function public.force_chat_message_client_created_at()"
        in sql
    )
    assert "create trigger trg_chat_messages_client_created_at" in sql
    assert "new.created_at := now()" in sql
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
        assert "source in ('internal', 'external_candidate')" in mutation_policy
        assert "visibility = 'admin_only'" in mutation_policy
        assert "promoted_from_upload_id is null" in mutation_policy
        assert "quality_status in ('unverified', 'rejected', 'needs_review')" in (
            mutation_policy
        )
        assert "quality_status = 'verified'" not in mutation_policy
        assert "visibility = 'public_catalog'" not in mutation_policy


def test_chat_tool_call_message_is_same_session() -> None:
    sql = migration_sql()

    assert (
        "create or replace function public.enforce_chat_tool_call_message_scope()"
        in sql
    )
    assert "create trigger trg_chat_tool_calls_message_scope" in sql
    assert "from public.chat_messages as m" in sql
    assert "m.id = new.message_id" in sql
    assert "m.session_id = new.session_id" in sql
    assert (
        "chat_tool_calls.message_id must reference a message in the same session" in sql
    )


def test_authenticated_asset_writes_cannot_mark_scan_results() -> None:
    sql = migration_sql()
    insert_policy = policy_sql(sql, "floorplan_assets_owner_or_session_insert")
    update_policy = policy_sql(sql, "floorplan_assets_owner_or_session_update")
    delete_policy = policy_sql(sql, "floorplan_assets_owner_or_session_delete")

    assert "scan_status text not null default 'pending'" in sql
    assert (
        "scan_status in ('pending', 'clean', 'infected', 'failed', 'not_required')"
        in sql
    )
    assert "and scan_status = 'pending'" in insert_policy
    assert "and scan_status = 'pending'" in update_policy
    assert "scan_status = 'clean'" not in insert_policy
    assert "scan_status = 'clean'" not in update_policy
    assert "scan_status = 'not_required'" not in insert_policy
    assert "scan_status = 'not_required'" not in update_policy
    assert "and scan_status = 'pending'" in delete_policy


def test_referenced_original_asset_invariants_are_client_immutable() -> None:
    sql = migration_sql()

    assert (
        "create or replace function public.prevent_referenced_original_asset_client_mutation()"
        in sql
    )
    assert "create trigger trg_floorplan_assets_referenced_original_client_guard" in sql
    assert "u.original_asset_id = old.id" in sql
    assert "new.kind is distinct from old.kind" in sql
    assert "new.scan_status is distinct from old.scan_status" in sql
    assert "new.session_id is distinct from old.session_id" in sql
    assert "new.owner_user_id is distinct from old.owner_user_id" in sql
    assert "new.floorplan_upload_id is distinct from old.floorplan_upload_id" in sql
    assert "new.floorplan_id is distinct from old.floorplan_id" in sql
    assert "new.kind = 'original'" in sql
    assert "new.session_id = u.session_id" in sql
    assert "new.owner_user_id = u.user_id" in sql
    assert (
        "authenticated clients cannot mutate referenced original asset invariants"
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

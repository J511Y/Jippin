-- CMP-608 Phase A main feature schema.
-- Supabase Auth is the ownership SSOT: user-owned rows reference auth.users(id).
-- Large binaries and signed URLs stay out of Postgres; only object metadata is stored.

create table public.sessions (
  id uuid not null default gen_random_uuid(),
  user_id uuid not null,
  status text not null default 'draft',
  address_id uuid,
  selected_floorplan_id uuid,
  selected_floorplan_upload_id uuid,
  selected_floorplan_asset_id uuid,
  judgment_schema jsonb not null default '{}'::jsonb,
  judgment_schema_version text,
  completion_decision text,
  last_activity_at timestamp with time zone not null default now(),
  expires_at timestamp with time zone,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint pk_sessions primary key (id),
  constraint ck_sessions_sessions_status_allowed check (
    status in (
      'draft',
      'address_ready',
      'floorplan_selected',
      'analyzing',
      'awaiting_overlay',
      'collecting_info',
      'ready_for_rule',
      'report_ready',
      'handoff',
      'expired',
      'deleted'
    )
  ),
  constraint ck_sessions_sessions_completion_decision_allowed check (
    completion_decision is null
    or completion_decision in (
      'ASK_MORE',
      'REQUEST_OVERLAY_REVIEW',
      'PROCEED_RULE',
      'HOLD_OR_HANDOFF'
    )
  ),
  constraint fk_sessions_user_id_users
    foreign key (user_id)
    references auth.users (id)
    on delete cascade
);

create table public.session_addresses (
  id uuid not null default gen_random_uuid(),
  session_id uuid not null,
  user_id uuid not null,
  road_address text,
  jibun_address text,
  apartment_name text,
  building_dong text,
  unit_ho text,
  floor_no integer,
  exclusive_area_m2 numeric(8, 2),
  size_type text,
  building_identity jsonb not null default '{}'::jsonb,
  address_provider text,
  normalized_at timestamp with time zone,
  created_at timestamp with time zone not null default now(),
  constraint pk_session_addresses primary key (id),
  constraint uq_session_addresses_session_id unique (session_id),
  constraint fk_session_addresses_session_id_sessions
    foreign key (session_id)
    references public.sessions (id)
    on delete cascade,
  constraint fk_session_addresses_user_id_users
    foreign key (user_id)
    references auth.users (id)
    on delete cascade
);

create table public.floorplans (
  id uuid not null default gen_random_uuid(),
  created_by uuid,
  source text not null,
  visibility text not null default 'admin_only',
  apartment_name text,
  building_dong text,
  size_type text,
  exclusive_area_m2 numeric(8, 2),
  layout_family text,
  address_fingerprint text,
  promoted_from_upload_id uuid,
  metadata jsonb not null default '{}'::jsonb,
  quality_status text not null default 'unverified',
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint pk_floorplans primary key (id),
  constraint ck_floorplans_floorplans_source_allowed check (
    source in ('internal', 'external_candidate', 'promoted_upload')
  ),
  constraint ck_floorplans_floorplans_visibility_allowed check (
    visibility in ('public_catalog', 'admin_only')
  ),
  constraint ck_floorplans_floorplans_quality_status_allowed check (
    quality_status in ('unverified', 'verified', 'rejected', 'needs_review')
  ),
  constraint fk_floorplans_created_by_users
    foreign key (created_by)
    references auth.users (id)
    on delete set null
);

create table public.floorplan_uploads (
  id uuid not null default gen_random_uuid(),
  session_id uuid not null,
  user_id uuid not null,
  original_asset_id uuid,
  status text not null default 'uploaded',
  file_name text,
  source_note text,
  upload_metadata jsonb not null default '{}'::jsonb,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint pk_floorplan_uploads primary key (id),
  constraint ck_floorplan_uploads_floorplan_uploads_status_allowed check (
    status in (
      'uploaded',
      'scan_pending',
      'scan_failed',
      'ready_for_processing',
      'processing',
      'processed',
      'rejected',
      'promoted_to_catalog'
    )
  ),
  constraint fk_floorplan_uploads_session_id_sessions
    foreign key (session_id)
    references public.sessions (id)
    on delete cascade,
  constraint fk_floorplan_uploads_user_id_users
    foreign key (user_id)
    references auth.users (id)
    on delete cascade
);

create table public.floorplan_assets (
  id uuid not null default gen_random_uuid(),
  floorplan_id uuid,
  floorplan_upload_id uuid,
  session_id uuid,
  owner_user_id uuid,
  kind text not null,
  storage_provider text not null default 'r2',
  bucket text not null,
  object_key text not null,
  content_type text not null,
  byte_size bigint not null,
  sha256_hex text,
  width_px integer,
  height_px integer,
  page_count integer,
  scan_status text not null default 'pending',
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint pk_floorplan_assets primary key (id),
  constraint ck_floorplan_assets_floorplan_assets_kind_allowed check (
    kind in (
      'original',
      'thumbnail',
      'preview',
      'masked',
      'ocr_debug',
      'segmentation_mask',
      'overlay',
      'report_pdf',
      'report_image'
    )
  ),
  constraint ck_floorplan_assets_floorplan_assets_storage_provider_allowed check (
    storage_provider in ('r2', 's3')
  ),
  constraint ck_floorplan_assets_floorplan_assets_scan_status_allowed check (
    scan_status in ('pending', 'clean', 'infected', 'failed', 'not_required')
  ),
  constraint ck_floorplan_assets_floorplan_assets_byte_size_nonnegative check (
    byte_size >= 0
  ),
  constraint uq_floorplan_assets_bucket_object_key unique (bucket, object_key),
  constraint fk_floorplan_assets_floorplan_id_floorplans
    foreign key (floorplan_id)
    references public.floorplans (id)
    on delete cascade,
  constraint fk_floorplan_assets_floorplan_upload_id_floorplan_uploads
    foreign key (floorplan_upload_id)
    references public.floorplan_uploads (id)
    on delete cascade,
  constraint fk_floorplan_assets_session_id_sessions
    foreign key (session_id)
    references public.sessions (id)
    on delete cascade,
  constraint fk_floorplan_assets_owner_user_id_users
    foreign key (owner_user_id)
    references auth.users (id)
    on delete cascade
);

create table public.floorplan_candidates (
  id uuid not null default gen_random_uuid(),
  session_id uuid not null,
  lookup_revision integer not null default 1,
  floorplan_id uuid,
  rank integer not null,
  confidence numeric(5, 4) not null,
  match_reasons jsonb not null default '[]'::jsonb,
  lookup_input jsonb not null default '{}'::jsonb,
  floorplan_snapshot jsonb not null default '{}'::jsonb,
  selected_at timestamp with time zone,
  rejected_at timestamp with time zone,
  created_at timestamp with time zone not null default now(),
  constraint pk_floorplan_candidates primary key (id),
  constraint ck_floorplan_candidates_floorplan_candidates_lookup_revision_positive check (
    lookup_revision > 0
  ),
  constraint ck_floorplan_candidates_floorplan_candidates_rank_positive check (
    rank > 0
  ),
  constraint ck_floorplan_candidates_floorplan_candidates_confidence_range check (
    confidence >= 0 and confidence <= 1
  ),
  constraint fk_floorplan_candidates_session_id_sessions
    foreign key (session_id)
    references public.sessions (id)
    on delete cascade,
  constraint fk_floorplan_candidates_floorplan_id_floorplans
    foreign key (floorplan_id)
    references public.floorplans (id)
    on delete set null,
  constraint uq_floorplan_candidates_session_id_lookup_revision_floorplan_id
    unique (session_id, lookup_revision, floorplan_id),
  constraint uq_floorplan_candidates_session_id_lookup_revision_rank
    unique (session_id, lookup_revision, rank)
);

create table public.chat_messages (
  id uuid not null default gen_random_uuid(),
  session_id uuid not null,
  user_id uuid,
  role text not null,
  content text not null,
  content_redacted boolean not null default false,
  ui_components jsonb not null default '[]'::jsonb,
  judgment_snapshot jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamp with time zone not null default now(),
  constraint pk_chat_messages primary key (id),
  constraint ck_chat_messages_chat_messages_role_allowed check (
    role in ('user', 'assistant', 'system', 'tool')
  ),
  constraint fk_chat_messages_session_id_sessions
    foreign key (session_id)
    references public.sessions (id)
    on delete cascade,
  constraint fk_chat_messages_user_id_users
    foreign key (user_id)
    references auth.users (id)
    on delete set null
);

create table public.chat_tool_calls (
  id uuid not null default gen_random_uuid(),
  session_id uuid not null,
  message_id uuid,
  parent_tool_call_id uuid,
  user_id uuid,
  tool_name text not null,
  tool_kind text not null,
  status text not null default 'started',
  input jsonb not null default '{}'::jsonb,
  output jsonb,
  output_summary text,
  error_code text,
  error_message text,
  duration_ms integer,
  started_at timestamp with time zone not null default now(),
  completed_at timestamp with time zone,
  metadata jsonb not null default '{}'::jsonb,
  constraint pk_chat_tool_calls primary key (id),
  constraint ck_chat_tool_calls_chat_tool_calls_tool_kind_allowed check (
    tool_kind in (
      'retrieval',
      'db_query',
      'external_api',
      'ai_model',
      'rule_engine',
      'render',
      'notification',
      'other'
    )
  ),
  constraint ck_chat_tool_calls_chat_tool_calls_status_allowed check (
    status in ('started', 'succeeded', 'failed', 'cancelled')
  ),
  constraint ck_chat_tool_calls_chat_tool_calls_duration_ms_nonnegative check (
    duration_ms is null or duration_ms >= 0
  ),
  constraint fk_chat_tool_calls_session_id_sessions
    foreign key (session_id)
    references public.sessions (id)
    on delete cascade,
  constraint fk_chat_tool_calls_message_id_chat_messages
    foreign key (message_id)
    references public.chat_messages (id)
    on delete set null,
  constraint fk_chat_tool_calls_parent_tool_call_id_chat_tool_calls
    foreign key (parent_tool_call_id)
    references public.chat_tool_calls (id)
    on delete set null,
  constraint fk_chat_tool_calls_user_id_users
    foreign key (user_id)
    references auth.users (id)
    on delete set null
);

alter table public.sessions
  add constraint fk_sessions_address_id_session_addresses
  foreign key (address_id)
  references public.session_addresses (id)
  on delete set null;

alter table public.sessions
  add constraint fk_sessions_selected_floorplan_id_floorplans
  foreign key (selected_floorplan_id)
  references public.floorplans (id)
  on delete set null;

alter table public.sessions
  add constraint fk_sessions_selected_floorplan_upload_id_floorplan_uploads
  foreign key (selected_floorplan_upload_id)
  references public.floorplan_uploads (id)
  on delete set null;

alter table public.sessions
  add constraint fk_sessions_selected_floorplan_asset_id_floorplan_assets
  foreign key (selected_floorplan_asset_id)
  references public.floorplan_assets (id)
  on delete set null;

alter table public.floorplans
  add constraint fk_floorplans_promoted_from_upload_id_floorplan_uploads
  foreign key (promoted_from_upload_id)
  references public.floorplan_uploads (id)
  on delete set null;

alter table public.floorplan_uploads
  add constraint fk_floorplan_uploads_original_asset_id_floorplan_assets
  foreign key (original_asset_id)
  references public.floorplan_assets (id)
  on delete set null;

create index ix_sessions_user_id_created_at
  on public.sessions (user_id, created_at desc);
create index ix_sessions_status_last_activity_at
  on public.sessions (status, last_activity_at);
create index ix_sessions_address_id
  on public.sessions (address_id);
create index ix_sessions_selected_floorplan_id
  on public.sessions (selected_floorplan_id);
create index ix_sessions_selected_floorplan_upload_id
  on public.sessions (selected_floorplan_upload_id);
create index ix_sessions_selected_floorplan_asset_id
  on public.sessions (selected_floorplan_asset_id);
create index ix_sessions_expires_at_active
  on public.sessions (expires_at)
  where status not in ('expired', 'deleted');

create index ix_session_addresses_user_id_created_at
  on public.session_addresses (user_id, created_at desc);
create index ix_session_addresses_apartment_name_building_dong_size_type
  on public.session_addresses (apartment_name, building_dong, size_type);
create index ix_session_addresses_session_id
  on public.session_addresses (session_id);

create index ix_floorplans_apartment_name_building_dong_size_type
  on public.floorplans (apartment_name, building_dong, size_type);
create index ix_floorplans_source_quality_status
  on public.floorplans (source, quality_status);
create index ix_floorplans_created_by_created_at
  on public.floorplans (created_by, created_at desc);
create index ix_floorplans_address_fingerprint_present
  on public.floorplans (address_fingerprint)
  where address_fingerprint is not null;
create unique index uq_floorplans_promoted_from_upload_id_present
  on public.floorplans (promoted_from_upload_id)
  where promoted_from_upload_id is not null;

create index ix_floorplan_uploads_session_id_created_at
  on public.floorplan_uploads (session_id, created_at desc);
create index ix_floorplan_uploads_user_id_created_at
  on public.floorplan_uploads (user_id, created_at desc);
create index ix_floorplan_uploads_status_created_at
  on public.floorplan_uploads (status, created_at desc);
create index ix_floorplan_uploads_original_asset_id
  on public.floorplan_uploads (original_asset_id);

create index ix_floorplan_assets_floorplan_id_kind
  on public.floorplan_assets (floorplan_id, kind);
create index ix_floorplan_assets_floorplan_upload_id_kind
  on public.floorplan_assets (floorplan_upload_id, kind);
create index ix_floorplan_assets_session_id_kind
  on public.floorplan_assets (session_id, kind);
create index ix_floorplan_assets_owner_user_id_created_at
  on public.floorplan_assets (owner_user_id, created_at desc);
create index ix_floorplan_assets_scan_status_pending_failed
  on public.floorplan_assets (scan_status, created_at)
  where scan_status in ('pending', 'failed');

create index ix_floorplan_candidates_session_id_lookup_revision_confidence
  on public.floorplan_candidates (session_id, lookup_revision, confidence desc);
create index ix_floorplan_candidates_floorplan_id
  on public.floorplan_candidates (floorplan_id);

create index ix_chat_messages_session_id_created_at
  on public.chat_messages (session_id, created_at);
create index ix_chat_messages_user_id_created_at
  on public.chat_messages (user_id, created_at desc);

create index ix_chat_tool_calls_session_id_started_at
  on public.chat_tool_calls (session_id, started_at);
create index ix_chat_tool_calls_message_id_started_at
  on public.chat_tool_calls (message_id, started_at);
create index ix_chat_tool_calls_tool_name_started_at
  on public.chat_tool_calls (tool_name, started_at desc);
create index ix_chat_tool_calls_status_started_at
  on public.chat_tool_calls (status, started_at desc);
create index ix_chat_tool_calls_parent_tool_call_id
  on public.chat_tool_calls (parent_tool_call_id);
create index ix_chat_tool_calls_user_id
  on public.chat_tool_calls (user_id);

comment on table public.floorplans is
  'Reusable catalog floorplan candidates. User uploads are stored in floorplan_uploads and floorplan_assets.';
comment on table public.floorplan_assets is
  'R2/S3 object metadata only. Do not store signed URLs, provider tokens, or raw binary payloads.';
comment on column public.chat_messages.content_redacted is
  'True when message content was redacted before storage.';
comment on column public.chat_tool_calls.input is
  'Redacted tool input only. Do not store provider tokens, signed URLs, or raw PII.';
comment on column public.chat_tool_calls.output is
  'Redacted tool output only. Store large outputs in object storage and keep pointers/summaries here.';

create or replace function public.enforce_session_reference_scope()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if new.selected_floorplan_id is not null
    and new.selected_floorplan_upload_id is not null
  then
    raise exception 'sessions must select exactly one floorplan source'
      using errcode = '23514';
  end if;

  if new.status in (
    'analyzing',
    'awaiting_overlay',
    'collecting_info',
    'ready_for_rule',
    'report_ready',
    'handoff'
  )
    and new.selected_floorplan_id is null
    and new.selected_floorplan_upload_id is null
  then
    raise exception 'sessions entering analysis must select a floorplan source'
      using errcode = '23514';
  end if;

  if new.status in (
    'analyzing',
    'awaiting_overlay',
    'collecting_info',
    'ready_for_rule',
    'report_ready',
    'handoff'
  )
    and new.address_id is null
  then
    raise exception 'sessions entering analysis must reference a same-session address'
      using errcode = '23514';
  end if;

  if new.address_id is not null and not exists (
    select 1
    from public.session_addresses as sa
    where sa.id = new.address_id
      and sa.session_id = new.id
      and sa.user_id = new.user_id
  ) then
    raise exception 'sessions.address_id must reference the same session address row'
      using errcode = '23514';
  end if;

  if new.selected_floorplan_id is not null and not exists (
    select 1
    from public.floorplans as f
    where f.id = new.selected_floorplan_id
      and (
        (
          f.visibility = 'public_catalog'
          and f.quality_status = 'verified'
        )
        or f.created_by = new.user_id
      )
  ) then
    raise exception 'sessions.selected_floorplan_id must reference a readable floorplan'
      using errcode = '23514';
  end if;

  if new.selected_floorplan_upload_id is not null and not exists (
    select 1
    from public.floorplan_uploads as u
    where u.id = new.selected_floorplan_upload_id
      and u.session_id = new.id
      and u.user_id = new.user_id
  ) then
    raise exception 'sessions.selected_floorplan_upload_id must reference a same-session upload'
      using errcode = '23514';
  end if;

  if new.status in (
    'analyzing',
    'awaiting_overlay',
    'collecting_info',
    'ready_for_rule',
    'report_ready',
    'handoff'
  )
    and new.selected_floorplan_upload_id is not null
    and not exists (
      select 1
      from public.floorplan_uploads as u
      join public.floorplan_assets as a
        on a.id = u.original_asset_id
      where u.id = new.selected_floorplan_upload_id
        and u.session_id = new.id
        and u.user_id = new.user_id
        and u.status in (
          'ready_for_processing',
          'processing',
          'processed',
          'promoted_to_catalog'
        )
        and a.floorplan_upload_id = u.id
        and a.session_id = u.session_id
        and a.owner_user_id = u.user_id
        and a.kind = 'original'
        and a.scan_status = 'clean'
    )
  then
    raise exception 'sessions.selected_floorplan_upload_id must reference a clean processable upload for analysis'
      using errcode = '23514';
  end if;

  if new.selected_floorplan_asset_id is not null and not exists (
    select 1
    from public.floorplan_assets as a
    where a.id = new.selected_floorplan_asset_id
      and (
        new.selected_floorplan_id is null
        or a.floorplan_id = new.selected_floorplan_id
      )
      and (
        new.selected_floorplan_upload_id is null
        or a.floorplan_upload_id = new.selected_floorplan_upload_id
      )
      and (
        new.selected_floorplan_id is not null
        or new.selected_floorplan_upload_id is not null
        or a.session_id = new.id
      )
      and (
        (
          a.session_id = new.id
          and (
            a.owner_user_id is null
            or a.owner_user_id = new.user_id
          )
        )
        or (
          a.owner_user_id = new.user_id
          and (
            a.session_id is null
            or a.session_id = new.id
          )
        )
        or exists (
          select 1
          from public.floorplan_uploads as u
          where u.id = a.floorplan_upload_id
            and u.session_id = new.id
            and u.user_id = new.user_id
        )
        or exists (
          select 1
          from public.floorplans as f
          where f.id = a.floorplan_id
            and (
              (
                f.visibility = 'public_catalog'
                and f.quality_status = 'verified'
              )
              or f.created_by = new.user_id
            )
        )
      )
  ) then
    raise exception 'sessions.selected_floorplan_asset_id must reference a same-session or readable asset'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

create trigger trg_sessions_reference_scope
  before insert or update of
    status,
    user_id,
    address_id,
    selected_floorplan_id,
    selected_floorplan_upload_id,
    selected_floorplan_asset_id
  on public.sessions
  for each row
  execute function public.enforce_session_reference_scope();

create or replace function public.prevent_session_client_service_field_mutation()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if current_role <> 'authenticated' then
    return new;
  end if;

  if tg_op = 'INSERT' then
    new.created_at := now();
    new.updated_at := new.created_at;
    new.last_activity_at := new.created_at;

    if new.status <> 'draft'
      or new.judgment_schema <> '{}'::jsonb
      or new.judgment_schema_version is not null
      or new.completion_decision is not null
      or new.expires_at is not null
    then
      raise exception 'authenticated clients cannot set service-controlled session fields'
        using errcode = '42501';
    end if;
  elsif new.created_at is distinct from old.created_at then
    raise exception 'authenticated clients cannot change session audit timestamps'
      using errcode = '42501';
  elsif new.status is distinct from old.status
    or new.judgment_schema is distinct from old.judgment_schema
    or new.judgment_schema_version is distinct from old.judgment_schema_version
    or new.completion_decision is distinct from old.completion_decision
    or new.last_activity_at is distinct from old.last_activity_at
    or new.expires_at is distinct from old.expires_at
  then
    raise exception 'authenticated clients cannot change service-controlled session fields'
      using errcode = '42501';
  end if;

  if tg_op = 'UPDATE' then
    new.updated_at := now();
  end if;

  return new;
end;
$$;

create trigger trg_sessions_service_fields_client_guard
  before insert or update
  on public.sessions
  for each row
  execute function public.prevent_session_client_service_field_mutation();

create or replace function public.prevent_completed_session_client_pointer_mutation()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if current_role = 'authenticated'
    and old.status in (
      'analyzing',
      'awaiting_overlay',
      'collecting_info',
      'ready_for_rule',
      'report_ready',
      'handoff'
    )
    and (
      new.address_id is distinct from old.address_id
      or new.selected_floorplan_id is distinct from old.selected_floorplan_id
      or new.selected_floorplan_upload_id is distinct from old.selected_floorplan_upload_id
      or new.selected_floorplan_asset_id is distinct from old.selected_floorplan_asset_id
    )
  then
    raise exception 'authenticated clients cannot change session inputs after rule/report readiness'
      using errcode = '42501';
  end if;

  return new;
end;
$$;

create trigger trg_sessions_completed_pointer_client_guard
  before update of
    address_id,
    selected_floorplan_id,
    selected_floorplan_upload_id,
    selected_floorplan_asset_id
  on public.sessions
  for each row
  execute function public.prevent_completed_session_client_pointer_mutation();

create or replace function public.prevent_active_session_client_delete()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if current_role = 'authenticated'
    and old.status not in ('draft', 'expired', 'deleted')
  then
    raise exception 'authenticated clients cannot hard-delete active sessions'
      using errcode = '42501';
  end if;

  return old;
end;
$$;

create trigger trg_sessions_active_delete_client_guard
  before delete
  on public.sessions
  for each row
  execute function public.prevent_active_session_client_delete();

create or replace function public.prevent_session_address_client_reparent()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if current_role = 'authenticated'
    and (
      new.session_id is distinct from old.session_id
      or new.user_id is distinct from old.user_id
    )
  then
    raise exception 'authenticated clients cannot move session address ownership'
      using errcode = '42501';
  end if;

  return new;
end;
$$;

create trigger trg_session_addresses_client_reparent_guard
  before update of
    session_id,
    user_id
  on public.session_addresses
  for each row
  execute function public.prevent_session_address_client_reparent();

create or replace function public.prevent_session_address_client_created_at_mutation()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if current_role <> 'authenticated' then
    return new;
  end if;

  if tg_op = 'INSERT' then
    new.created_at := now();
  elsif new.created_at is distinct from old.created_at then
    raise exception 'authenticated clients cannot change address audit timestamps'
      using errcode = '42501';
  end if;

  return new;
end;
$$;

create trigger trg_session_addresses_created_at_client_guard
  before insert or update of
    created_at
  on public.session_addresses
  for each row
  execute function public.prevent_session_address_client_created_at_mutation();

create or replace function public.prevent_session_address_client_normalized_mutation()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if current_role <> 'authenticated' then
    return new;
  end if;

  if tg_op = 'INSERT' then
    new.building_identity := '{}'::jsonb;
    new.address_provider := null;
    new.normalized_at := null;
  elsif new.building_identity is distinct from old.building_identity
    or new.address_provider is distinct from old.address_provider
    or new.normalized_at is distinct from old.normalized_at
  then
    raise exception 'authenticated clients cannot change normalized address fields'
      using errcode = '42501';
  end if;

  return new;
end;
$$;

create trigger trg_session_addresses_normalized_client_guard
  before insert or update of
    building_identity,
    address_provider,
    normalized_at
  on public.session_addresses
  for each row
  execute function public.prevent_session_address_client_normalized_mutation();

create or replace function public.reset_session_address_client_normalization()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if current_role = 'authenticated'
    and (
      new.road_address is distinct from old.road_address
      or new.jibun_address is distinct from old.jibun_address
      or new.apartment_name is distinct from old.apartment_name
      or new.building_dong is distinct from old.building_dong
      or new.unit_ho is distinct from old.unit_ho
      or new.floor_no is distinct from old.floor_no
      or new.exclusive_area_m2 is distinct from old.exclusive_area_m2
      or new.size_type is distinct from old.size_type
    )
  then
    new.building_identity := '{}'::jsonb;
    new.address_provider := null;
    new.normalized_at := null;
  end if;

  return new;
end;
$$;

create trigger trg_session_addresses_input_normalization_reset
  before update of
    road_address,
    jibun_address,
    apartment_name,
    building_dong,
    unit_ho,
    floor_no,
    exclusive_area_m2,
    size_type
  on public.session_addresses
  for each row
  execute function public.reset_session_address_client_normalization();

create or replace function public.prevent_active_session_address_client_mutation()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if current_role = 'authenticated'
    and exists (
      select 1
      from public.sessions as s
      where s.address_id = old.id
        and s.status in (
          'analyzing',
          'awaiting_overlay',
          'collecting_info',
          'ready_for_rule',
          'report_ready',
          'handoff'
        )
    )
  then
    raise exception 'authenticated clients cannot change current address after analysis starts'
      using errcode = '42501';
  end if;

  return new;
end;
$$;

create trigger trg_session_addresses_active_client_guard
  before update of
    road_address,
    jibun_address,
    apartment_name,
    building_dong,
    unit_ho,
    floor_no,
    exclusive_area_m2,
    size_type
  on public.session_addresses
  for each row
  execute function public.prevent_active_session_address_client_mutation();

create or replace function public.prevent_active_session_address_client_delete()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if current_role = 'authenticated'
    and exists (
      select 1
      from public.sessions as s
      where s.address_id = old.id
        or (
          s.id = old.session_id
          and s.status in (
            'analyzing',
            'awaiting_overlay',
            'collecting_info',
            'ready_for_rule',
            'report_ready',
            'handoff'
          )
        )
    )
  then
    raise exception 'authenticated clients cannot delete current or active session addresses'
      using errcode = '42501';
  end if;

  return old;
end;
$$;

create trigger trg_session_addresses_active_delete_client_guard
  before delete
  on public.session_addresses
  for each row
  execute function public.prevent_active_session_address_client_delete();

create or replace function public.prevent_floorplan_client_catalog_promotion()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if current_role <> 'authenticated' then
    return new;
  end if;

  if tg_op = 'INSERT' then
    new.created_at := now();
    new.updated_at := new.created_at;
  elsif new.created_at is distinct from old.created_at then
    raise exception 'authenticated clients cannot change floorplan audit timestamps'
      using errcode = '42501';
  end if;

  if tg_op = 'UPDATE' and (
    old.source = 'promoted_upload'
    or old.visibility = 'public_catalog'
    or old.quality_status = 'verified'
    or old.promoted_from_upload_id is not null
  ) then
    raise exception 'authenticated clients cannot mutate service-owned catalog floorplans'
      using errcode = '42501';
  end if;

  if new.source = 'promoted_upload'
    or new.visibility = 'public_catalog'
    or new.quality_status = 'verified'
    or new.promoted_from_upload_id is not null
  then
    raise exception 'authenticated clients cannot promote catalog floorplans'
      using errcode = '42501';
  end if;

  if tg_op = 'UPDATE' then
    new.updated_at := now();
  end if;

  return new;
end;
$$;

create trigger trg_floorplans_client_catalog_promotion_guard
  before insert or update
  on public.floorplans
  for each row
  execute function public.prevent_floorplan_client_catalog_promotion();

create or replace function public.prevent_selected_floorplan_client_mutation()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if current_role = 'authenticated'
    and exists (
      select 1
      from public.sessions as s
      where s.selected_floorplan_id = old.id
        and s.status in (
          'analyzing',
          'awaiting_overlay',
          'collecting_info',
          'ready_for_rule',
          'report_ready',
          'handoff'
        )
    )
  then
    raise exception 'authenticated clients cannot mutate selected floorplans after analysis starts'
      using errcode = '42501';
  end if;

  return new;
end;
$$;

create trigger trg_floorplans_selected_client_guard
  before update of
    source,
    apartment_name,
    building_dong,
    size_type,
    exclusive_area_m2,
    layout_family,
    address_fingerprint,
    promoted_from_upload_id,
    metadata,
    quality_status,
    visibility
  on public.floorplans
  for each row
  execute function public.prevent_selected_floorplan_client_mutation();

create or replace function public.prevent_selected_floorplan_client_delete()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if current_role = 'authenticated'
    and exists (
      select 1
      from public.sessions as s
      where s.selected_floorplan_id = old.id
        and s.status in (
          'analyzing',
          'awaiting_overlay',
          'collecting_info',
          'ready_for_rule',
          'report_ready',
          'handoff'
        )
    )
  then
    raise exception 'authenticated clients cannot delete selected floorplans after analysis starts'
      using errcode = '42501';
  end if;

  return old;
end;
$$;

create trigger trg_floorplans_selected_delete_client_guard
  before delete
  on public.floorplans
  for each row
  execute function public.prevent_selected_floorplan_client_delete();

create or replace function public.enforce_floorplan_upload_original_asset_scope()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if new.status in (
    'scan_pending',
    'ready_for_processing',
    'processing',
    'processed',
    'promoted_to_catalog'
  )
    and new.original_asset_id is null
  then
    raise exception 'floorplan_uploads queue-visible status requires an original asset'
      using errcode = '23514';
  end if;

  if new.original_asset_id is not null and not exists (
    select 1
    from public.floorplan_assets as a
    where a.id = new.original_asset_id
      and a.floorplan_upload_id = new.id
      and a.session_id = new.session_id
      and a.owner_user_id = new.user_id
      and a.kind = 'original'
  ) then
    raise exception 'floorplan_uploads.original_asset_id must reference a same-session owner original asset'
      using errcode = '23514';
  end if;

  if new.status in (
    'ready_for_processing',
    'processing',
    'processed',
    'promoted_to_catalog'
  )
    and not exists (
      select 1
      from public.floorplan_assets as a
      where a.id = new.original_asset_id
        and a.floorplan_upload_id = new.id
        and a.session_id = new.session_id
        and a.owner_user_id = new.user_id
        and a.kind = 'original'
        and a.scan_status = 'clean'
    )
  then
    raise exception 'floorplan_uploads processing status requires a clean original asset'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

create trigger trg_floorplan_uploads_original_asset_scope
  before insert or update of
    session_id,
    user_id,
    original_asset_id,
    status
  on public.floorplan_uploads
  for each row
  execute function public.enforce_floorplan_upload_original_asset_scope();

create or replace function public.prevent_floorplan_upload_client_service_mutation()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if current_role <> 'authenticated' then
    return new;
  end if;

  if tg_op = 'INSERT' then
    new.created_at := now();
    new.updated_at := new.created_at;

    if new.status <> 'uploaded' then
      raise exception 'authenticated clients cannot set service-controlled upload status'
        using errcode = '42501';
    end if;
  elsif new.created_at is distinct from old.created_at then
    raise exception 'authenticated clients cannot change upload audit timestamps'
      using errcode = '42501';
  elsif new.session_id is distinct from old.session_id then
    raise exception 'authenticated clients cannot move floorplan uploads between sessions'
      using errcode = '42501';
  elsif old.status <> 'uploaded' then
    raise exception 'authenticated clients cannot mutate service-controlled upload rows'
      using errcode = '42501';
  elsif new.status is distinct from old.status then
    raise exception 'authenticated clients cannot change service-controlled upload status'
      using errcode = '42501';
  end if;

  if tg_op = 'UPDATE' then
    new.updated_at := now();
  end if;

  return new;
end;
$$;

create trigger trg_floorplan_uploads_client_service_guard
  before insert or update
  on public.floorplan_uploads
  for each row
  execute function public.prevent_floorplan_upload_client_service_mutation();

create or replace function public.prevent_floorplan_asset_client_timestamp_mutation()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if current_role <> 'authenticated' then
    return new;
  end if;

  if tg_op = 'INSERT' then
    new.created_at := now();
    new.updated_at := new.created_at;
  elsif new.created_at is distinct from old.created_at then
    raise exception 'authenticated clients cannot change asset audit timestamps'
      using errcode = '42501';
  end if;

  if tg_op = 'UPDATE' then
    new.updated_at := now();
  end if;

  return new;
end;
$$;

create trigger trg_floorplan_assets_audit_timestamps_client_guard
  before insert or update
  on public.floorplan_assets
  for each row
  execute function public.prevent_floorplan_asset_client_timestamp_mutation();

create or replace function public.prevent_referenced_original_asset_client_mutation()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if current_role <> 'authenticated' then
    return new;
  end if;

  if exists (
    select 1
    from public.floorplan_uploads as u
    where u.original_asset_id = old.id
  ) then
    if new.kind is distinct from old.kind
      or new.scan_status is distinct from old.scan_status
      or new.session_id is distinct from old.session_id
      or new.owner_user_id is distinct from old.owner_user_id
      or new.floorplan_upload_id is distinct from old.floorplan_upload_id
      or new.floorplan_id is distinct from old.floorplan_id
      or new.storage_provider is distinct from old.storage_provider
      or new.bucket is distinct from old.bucket
      or new.object_key is distinct from old.object_key
      or new.content_type is distinct from old.content_type
      or new.byte_size is distinct from old.byte_size
      or new.sha256_hex is distinct from old.sha256_hex
      or new.width_px is distinct from old.width_px
      or new.height_px is distinct from old.height_px
      or new.page_count is distinct from old.page_count
    then
      raise exception 'authenticated clients cannot mutate referenced original asset invariants'
        using errcode = '42501';
    end if;

    if not exists (
      select 1
      from public.floorplan_uploads as u
      where u.original_asset_id = old.id
        and new.kind = 'original'
        and new.session_id = u.session_id
        and new.owner_user_id = u.user_id
    ) then
      raise exception 'referenced original asset must remain same-session owner original'
        using errcode = '23514';
    end if;
  end if;

  return new;
end;
$$;

create trigger trg_floorplan_assets_referenced_original_client_guard
  before update of
    floorplan_id,
    floorplan_upload_id,
    session_id,
    owner_user_id,
    kind,
    storage_provider,
    bucket,
    object_key,
    content_type,
    byte_size,
    sha256_hex,
    width_px,
    height_px,
    page_count,
    scan_status
  on public.floorplan_assets
  for each row
  execute function public.prevent_referenced_original_asset_client_mutation();

create or replace function public.prevent_selected_asset_client_metadata_mutation()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if current_role = 'authenticated'
    and exists (
      select 1
      from public.sessions as s
      where s.selected_floorplan_asset_id = old.id
        and s.status in (
          'analyzing',
          'awaiting_overlay',
          'collecting_info',
          'ready_for_rule',
          'report_ready',
          'handoff'
        )
    )
  then
    raise exception 'authenticated clients cannot mutate selected asset metadata after analysis starts'
      using errcode = '42501';
  end if;

  return new;
end;
$$;

create trigger trg_floorplan_assets_selected_metadata_client_guard
  before update of
    floorplan_id,
    floorplan_upload_id,
    session_id,
    owner_user_id,
    kind,
    storage_provider,
    bucket,
    object_key,
    content_type,
    byte_size,
    sha256_hex,
    width_px,
    height_px,
    page_count,
    scan_status
  on public.floorplan_assets
  for each row
  execute function public.prevent_selected_asset_client_metadata_mutation();

create or replace function public.prevent_selected_asset_client_delete()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if current_role = 'authenticated'
    and exists (
      select 1
      from public.sessions as s
      where s.selected_floorplan_asset_id = old.id
        and s.status in (
          'analyzing',
          'awaiting_overlay',
          'collecting_info',
          'ready_for_rule',
          'report_ready',
          'handoff'
        )
    )
  then
    raise exception 'authenticated clients cannot delete selected assets after analysis starts'
      using errcode = '42501';
  end if;

  return old;
end;
$$;

create trigger trg_floorplan_assets_selected_delete_client_guard
  before delete
  on public.floorplan_assets
  for each row
  execute function public.prevent_selected_asset_client_delete();

create or replace function public.prevent_floorplan_asset_mixed_parent_scope()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if current_role = 'authenticated'
    and new.floorplan_id is not null
    and (
      new.floorplan_upload_id is not null
      or new.session_id is not null
    )
  then
    raise exception 'floorplan_assets cannot mix catalog floorplan scope with upload or session scope'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

create trigger trg_floorplan_assets_mixed_parent_scope_guard
  before insert or update of
    floorplan_id,
    floorplan_upload_id,
    session_id
  on public.floorplan_assets
  for each row
  execute function public.prevent_floorplan_asset_mixed_parent_scope();

create or replace function public.enforce_chat_tool_call_message_scope()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if new.message_id is not null and not exists (
    select 1
    from public.chat_messages as m
    where m.id = new.message_id
      and m.session_id = new.session_id
  ) then
    raise exception 'chat_tool_calls.message_id must reference a message in the same session'
      using errcode = '23514';
  end if;

  if new.parent_tool_call_id is not null and not exists (
    select 1
    from public.chat_tool_calls as parent
    where parent.id = new.parent_tool_call_id
      and parent.session_id = new.session_id
  ) then
    raise exception 'chat_tool_calls.parent_tool_call_id must reference a tool call in the same session'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

create trigger trg_chat_tool_calls_message_scope
  before insert or update of
    session_id,
    message_id,
    parent_tool_call_id
  on public.chat_tool_calls
  for each row
  execute function public.enforce_chat_tool_call_message_scope();

create or replace function public.force_chat_message_client_created_at()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if current_role = 'authenticated' then
    new.created_at := now();
    new.content_redacted := false;
    new.ui_components := '[]'::jsonb;
    new.judgment_snapshot := null;
    new.metadata := '{}'::jsonb;
  end if;

  return new;
end;
$$;

create trigger trg_chat_messages_client_created_at
  before insert
  on public.chat_messages
  for each row
  execute function public.force_chat_message_client_created_at();

alter table public.sessions enable row level security;
alter table public.session_addresses enable row level security;
alter table public.floorplans enable row level security;
alter table public.floorplan_uploads enable row level security;
alter table public.floorplan_assets enable row level security;
alter table public.floorplan_candidates enable row level security;
alter table public.chat_messages enable row level security;
alter table public.chat_tool_calls enable row level security;

create policy sessions_owner_all
  on public.sessions
  for all
  to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

create policy session_addresses_owner_all
  on public.session_addresses
  for all
  to authenticated
  using (user_id = (select auth.uid()))
  with check (
    user_id = (select auth.uid())
    and exists (
      select 1
      from public.sessions as s
      where s.id = session_id
        and s.user_id = (select auth.uid())
    )
  );

create policy floorplans_owner_or_public_read
  on public.floorplans
  for select
  to authenticated
  using (
    (
      visibility = 'public_catalog'
      and quality_status = 'verified'
    )
    or created_by = (select auth.uid())
  );

create policy floorplans_owner_insert
  on public.floorplans
  for insert
  to authenticated
  with check (
    created_by = (select auth.uid())
    and source in ('internal', 'external_candidate')
    and visibility = 'admin_only'
    and promoted_from_upload_id is null
    and quality_status in ('unverified', 'rejected', 'needs_review')
  );

create policy floorplans_owner_update
  on public.floorplans
  for update
  to authenticated
  using (
    created_by = (select auth.uid())
    and source in ('internal', 'external_candidate')
    and visibility = 'admin_only'
    and promoted_from_upload_id is null
    and quality_status in ('unverified', 'rejected', 'needs_review')
  )
  with check (
    created_by = (select auth.uid())
    and source in ('internal', 'external_candidate')
    and visibility = 'admin_only'
    and promoted_from_upload_id is null
    and quality_status in ('unverified', 'rejected', 'needs_review')
  );

create policy floorplans_owner_delete
  on public.floorplans
  for delete
  to authenticated
  using (
    created_by = (select auth.uid())
    and source in ('internal', 'external_candidate')
    and visibility = 'admin_only'
    and promoted_from_upload_id is null
    and quality_status in ('unverified', 'rejected', 'needs_review')
  );

create policy floorplan_uploads_owner_read
  on public.floorplan_uploads
  for select
  to authenticated
  using (user_id = (select auth.uid()));

create policy floorplan_uploads_owner_insert
  on public.floorplan_uploads
  for insert
  to authenticated
  with check (
    user_id = (select auth.uid())
    and status = 'uploaded'
    and exists (
      select 1
      from public.sessions as s
      where s.id = session_id
        and s.user_id = (select auth.uid())
    )
  );

create policy floorplan_uploads_owner_update
  on public.floorplan_uploads
  for update
  to authenticated
  using (
    user_id = (select auth.uid())
    and status = 'uploaded'
  )
  with check (
    user_id = (select auth.uid())
    and status = 'uploaded'
    and exists (
      select 1
      from public.sessions as s
      where s.id = session_id
        and s.user_id = (select auth.uid())
    )
  );

create policy floorplan_assets_owner_or_session_read
  on public.floorplan_assets
  for select
  to authenticated
  using (
    owner_user_id = (select auth.uid())
    or exists (
      select 1
      from public.sessions as s
      where s.id = session_id
        and s.user_id = (select auth.uid())
    )
    or exists (
      select 1
      from public.floorplan_uploads as u
      where u.id = floorplan_upload_id
        and u.user_id = (select auth.uid())
    )
    or exists (
      select 1
      from public.floorplans as f
      where f.id = floorplan_id
        and f.created_by = (select auth.uid())
    )
    or (
      kind in ('thumbnail', 'preview')
      and exists (
        select 1
        from public.floorplans as f
        where f.id = floorplan_id
          and f.visibility = 'public_catalog'
          and f.quality_status = 'verified'
        )
    )
  );

create policy floorplan_assets_owner_or_session_insert
  on public.floorplan_assets
  for insert
  to authenticated
  with check (
    owner_user_id = (select auth.uid())
    and kind = 'original'
    and scan_status = 'pending'
    and (
      floorplan_id is null
      or exists (
        select 1
        from public.floorplans as f
        where f.id = floorplan_id
          and f.created_by = (select auth.uid())
          and f.visibility = 'admin_only'
          and f.quality_status in ('unverified', 'rejected', 'needs_review')
      )
    )
    and (
      floorplan_upload_id is null
      or exists (
        select 1
        from public.floorplan_uploads as u
        where u.id = floorplan_upload_id
          and u.user_id = (select auth.uid())
          and u.status = 'uploaded'
          and (
            public.floorplan_assets.session_id is null
            or u.session_id = public.floorplan_assets.session_id
          )
      )
    )
    and (
      session_id is null
      or exists (
        select 1
        from public.sessions as s
        where s.id = session_id
          and s.user_id = (select auth.uid())
      )
    )
  );

create policy floorplan_assets_owner_or_session_update
  on public.floorplan_assets
  for update
  to authenticated
  using (
    owner_user_id = (select auth.uid())
    and kind = 'original'
    and scan_status = 'pending'
    and (
      floorplan_id is null
      or exists (
        select 1
        from public.floorplans as f
        where f.id = floorplan_id
          and f.created_by = (select auth.uid())
          and f.visibility = 'admin_only'
          and f.quality_status in ('unverified', 'rejected', 'needs_review')
        )
    )
    and (
      floorplan_upload_id is null
      or exists (
        select 1
        from public.floorplan_uploads as u
        where u.id = floorplan_upload_id
          and u.user_id = (select auth.uid())
          and u.status = 'uploaded'
          and (
            public.floorplan_assets.session_id is null
            or u.session_id = public.floorplan_assets.session_id
          )
      )
    )
    and (
      session_id is null
      or exists (
        select 1
        from public.sessions as s
        where s.id = session_id
          and s.user_id = (select auth.uid())
      )
    )
  )
  with check (
    owner_user_id = (select auth.uid())
    and kind = 'original'
    and scan_status = 'pending'
    and (
      floorplan_id is null
      or exists (
        select 1
        from public.floorplans as f
        where f.id = floorplan_id
          and f.created_by = (select auth.uid())
          and f.visibility = 'admin_only'
          and f.quality_status in ('unverified', 'rejected', 'needs_review')
      )
    )
    and (
      floorplan_upload_id is null
      or exists (
        select 1
        from public.floorplan_uploads as u
        where u.id = floorplan_upload_id
          and u.user_id = (select auth.uid())
          and u.status = 'uploaded'
          and (
            public.floorplan_assets.session_id is null
            or u.session_id = public.floorplan_assets.session_id
          )
        )
    )
    and (
      session_id is null
      or exists (
        select 1
        from public.sessions as s
        where s.id = session_id
          and s.user_id = (select auth.uid())
      )
    )
  );

create policy floorplan_assets_owner_or_session_delete
  on public.floorplan_assets
  for delete
  to authenticated
  using (
    owner_user_id = (select auth.uid())
    and kind = 'original'
    and scan_status = 'pending'
    and not exists (
      select 1
      from public.floorplan_uploads as u
      where u.original_asset_id = public.floorplan_assets.id
    )
    and (
      floorplan_id is null
      or exists (
        select 1
        from public.floorplans as f
        where f.id = floorplan_id
          and f.created_by = (select auth.uid())
          and f.visibility = 'admin_only'
          and f.quality_status in ('unverified', 'rejected', 'needs_review')
        )
    )
    and (
      floorplan_upload_id is null
      or exists (
        select 1
        from public.floorplan_uploads as u
        where u.id = floorplan_upload_id
          and u.user_id = (select auth.uid())
          and (
            public.floorplan_assets.session_id is null
            or u.session_id = public.floorplan_assets.session_id
          )
      )
    )
    and (
      session_id is null
      or exists (
        select 1
        from public.sessions as s
        where s.id = session_id
          and s.user_id = (select auth.uid())
      )
    )
  );

create policy floorplan_candidates_session_owner_read
  on public.floorplan_candidates
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.sessions as s
      where s.id = session_id
        and s.user_id = (select auth.uid())
    )
  );

create policy chat_messages_session_owner_read
  on public.chat_messages
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.sessions as s
      where s.id = session_id
        and s.user_id = (select auth.uid())
    )
  );

create policy chat_tool_calls_session_owner_read
  on public.chat_tool_calls
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.sessions as s
      where s.id = session_id
        and s.user_id = (select auth.uid())
    )
  );

grant usage on schema public to authenticated;

grant select, insert, update, delete
  on public.sessions,
     public.session_addresses,
     public.floorplans,
     public.floorplan_assets
  to authenticated;

grant select, insert, update
  on public.floorplan_uploads
  to authenticated;

grant select
  on public.chat_messages
  to authenticated;

grant select
  on public.floorplan_candidates,
     public.chat_tool_calls
  to authenticated;

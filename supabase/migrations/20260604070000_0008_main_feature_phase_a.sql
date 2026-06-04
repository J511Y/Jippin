-- CMP-606 Phase A main feature schema.
-- Supabase Auth remains the identity SSOT. User-owned rows reference
-- auth.users(id), including anonymous users created by Supabase Anonymous Sign-In.

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
    visibility in ('public_catalog', 'admin_only', 'private')
  ),
  constraint ck_floorplans_floorplans_quality_status_allowed check (
    quality_status in ('unverified', 'verified', 'rejected', 'needs_review')
  ),
  constraint fk_floorplans_created_by_auth_users
    foreign key (created_by)
    references auth.users (id)
    on delete set null
);

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
  constraint fk_sessions_user_id_auth_users
    foreign key (user_id)
    references auth.users (id)
    on delete cascade,
  constraint fk_sessions_selected_floorplan_id_floorplans
    foreign key (selected_floorplan_id)
    references public.floorplans (id)
    on delete set null
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
  constraint fk_session_addresses_user_id_auth_users
    foreign key (user_id)
    references auth.users (id)
    on delete cascade
);

alter table public.sessions
  add constraint fk_sessions_address_id_session_addresses
  foreign key (address_id)
  references public.session_addresses (id)
  on delete set null;

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
  constraint fk_floorplan_uploads_user_id_auth_users
    foreign key (user_id)
    references auth.users (id)
    on delete cascade
);

create table public.floorplan_assets (
  id uuid not null default gen_random_uuid(),
  session_id uuid,
  user_id uuid,
  floorplan_id uuid,
  upload_id uuid,
  kind text not null,
  storage_provider text not null default 'r2',
  bucket text not null,
  object_key text not null,
  content_type text,
  byte_size bigint,
  sha256 text,
  width_px integer,
  height_px integer,
  page_count integer,
  metadata jsonb not null default '{}'::jsonb,
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
      'report_pdf'
    )
  ),
  constraint ck_floorplan_assets_floorplan_assets_storage_provider_allowed check (
    storage_provider in ('r2', 's3')
  ),
  constraint fk_floorplan_assets_session_id_sessions
    foreign key (session_id)
    references public.sessions (id)
    on delete cascade,
  constraint fk_floorplan_assets_user_id_auth_users
    foreign key (user_id)
    references auth.users (id)
    on delete cascade,
  constraint fk_floorplan_assets_floorplan_id_floorplans
    foreign key (floorplan_id)
    references public.floorplans (id)
    on delete set null,
  constraint fk_floorplan_assets_upload_id_floorplan_uploads
    foreign key (upload_id)
    references public.floorplan_uploads (id)
    on delete cascade,
  constraint uq_floorplan_assets_storage_object unique (storage_provider, bucket, object_key)
);

alter table public.floorplan_uploads
  add constraint fk_floorplan_uploads_original_asset_id_floorplan_assets
  foreign key (original_asset_id)
  references public.floorplan_assets (id)
  on delete set null;

alter table public.floorplans
  add constraint fk_floorplans_promoted_from_upload_id_floorplan_uploads
  foreign key (promoted_from_upload_id)
  references public.floorplan_uploads (id)
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

create table public.floorplan_candidates (
  id uuid not null default gen_random_uuid(),
  session_id uuid not null,
  user_id uuid not null,
  floorplan_id uuid,
  lookup_revision integer not null default 1,
  rank integer not null,
  confidence numeric(5, 4),
  candidate_snapshot jsonb not null default '{}'::jsonb,
  presented_at timestamp with time zone not null default now(),
  selected_at timestamp with time zone,
  rejected_at timestamp with time zone,
  created_at timestamp with time zone not null default now(),
  constraint pk_floorplan_candidates primary key (id),
  constraint fk_floorplan_candidates_session_id_sessions
    foreign key (session_id)
    references public.sessions (id)
    on delete cascade,
  constraint fk_floorplan_candidates_user_id_auth_users
    foreign key (user_id)
    references auth.users (id)
    on delete cascade,
  constraint fk_floorplan_candidates_floorplan_id_floorplans
    foreign key (floorplan_id)
    references public.floorplans (id)
    on delete set null,
  constraint uq_floorplan_candidates_session_revision_rank
    unique (session_id, lookup_revision, rank)
);

create table public.chat_messages (
  id uuid not null default gen_random_uuid(),
  session_id uuid not null,
  user_id uuid not null,
  role text not null,
  content text,
  content_json jsonb not null default '{}'::jsonb,
  message_order integer not null,
  created_at timestamp with time zone not null default now(),
  constraint pk_chat_messages primary key (id),
  constraint ck_chat_messages_chat_messages_role_allowed check (
    role in ('user', 'assistant', 'system', 'tool')
  ),
  constraint fk_chat_messages_session_id_sessions
    foreign key (session_id)
    references public.sessions (id)
    on delete cascade,
  constraint fk_chat_messages_user_id_auth_users
    foreign key (user_id)
    references auth.users (id)
    on delete cascade,
  constraint uq_chat_messages_session_message_order unique (session_id, message_order)
);

create table public.chat_tool_calls (
  id uuid not null default gen_random_uuid(),
  session_id uuid not null,
  user_id uuid not null,
  message_id uuid,
  tool_name text not null,
  status text not null default 'started',
  input jsonb not null default '{}'::jsonb,
  output jsonb,
  error_code text,
  error_message text,
  duration_ms integer,
  started_at timestamp with time zone not null default now(),
  finished_at timestamp with time zone,
  created_at timestamp with time zone not null default now(),
  constraint pk_chat_tool_calls primary key (id),
  constraint ck_chat_tool_calls_chat_tool_calls_status_allowed check (
    status in ('started', 'succeeded', 'failed', 'cancelled', 'timeout')
  ),
  constraint fk_chat_tool_calls_session_id_sessions
    foreign key (session_id)
    references public.sessions (id)
    on delete cascade,
  constraint fk_chat_tool_calls_user_id_auth_users
    foreign key (user_id)
    references auth.users (id)
    on delete cascade,
  constraint fk_chat_tool_calls_message_id_chat_messages
    foreign key (message_id)
    references public.chat_messages (id)
    on delete set null
);

create table public.processing_jobs (
  id uuid not null default gen_random_uuid(),
  session_id uuid,
  user_id uuid,
  job_type text not null,
  status text not null default 'queued',
  priority integer not null default 100,
  attempts integer not null default 0,
  max_attempts integer not null default 3,
  payload jsonb not null default '{}'::jsonb,
  result jsonb,
  error_code text,
  error_message text,
  run_after timestamp with time zone not null default now(),
  locked_at timestamp with time zone,
  locked_by text,
  started_at timestamp with time zone,
  finished_at timestamp with time zone,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint pk_processing_jobs primary key (id),
  constraint ck_processing_jobs_processing_jobs_status_allowed check (
    status in ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'retrying')
  ),
  constraint ck_processing_jobs_processing_jobs_attempts_allowed check (
    attempts >= 0 and max_attempts > 0 and attempts <= max_attempts
  ),
  constraint fk_processing_jobs_session_id_sessions
    foreign key (session_id)
    references public.sessions (id)
    on delete cascade,
  constraint fk_processing_jobs_user_id_auth_users
    foreign key (user_id)
    references auth.users (id)
    on delete cascade
);

create table public.webhook_deliveries (
  id uuid not null default gen_random_uuid(),
  session_id uuid,
  user_id uuid,
  event_type text not null,
  endpoint_url text not null,
  status text not null default 'pending',
  attempt_count integer not null default 0,
  payload jsonb not null default '{}'::jsonb,
  response_status integer,
  response_body text,
  error_message text,
  next_retry_at timestamp with time zone,
  delivered_at timestamp with time zone,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint pk_webhook_deliveries primary key (id),
  constraint ck_webhook_deliveries_webhook_deliveries_status_allowed check (
    status in ('pending', 'delivering', 'delivered', 'failed', 'cancelled')
  ),
  constraint fk_webhook_deliveries_session_id_sessions
    foreign key (session_id)
    references public.sessions (id)
    on delete cascade,
  constraint fk_webhook_deliveries_user_id_auth_users
    foreign key (user_id)
    references auth.users (id)
    on delete cascade
);

create table public.scheduled_task_runs (
  id uuid not null default gen_random_uuid(),
  task_key text not null,
  status text not null default 'started',
  lock_key text,
  started_at timestamp with time zone not null default now(),
  finished_at timestamp with time zone,
  duration_ms integer,
  summary jsonb not null default '{}'::jsonb,
  error_message text,
  created_at timestamp with time zone not null default now(),
  constraint pk_scheduled_task_runs primary key (id),
  constraint ck_scheduled_task_runs_scheduled_task_runs_status_allowed check (
    status in ('started', 'succeeded', 'failed', 'skipped')
  )
);

create table public.external_sync_records (
  id uuid not null default gen_random_uuid(),
  session_id uuid,
  user_id uuid,
  provider text not null,
  resource_type text not null,
  resource_key text not null,
  status text not null default 'pending',
  external_updated_at timestamp with time zone,
  last_synced_at timestamp with time zone,
  cursor_value text,
  payload jsonb not null default '{}'::jsonb,
  error_message text,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint pk_external_sync_records primary key (id),
  constraint ck_external_sync_records_external_sync_records_status_allowed check (
    status in ('pending', 'synced', 'failed', 'stale', 'ignored')
  ),
  constraint fk_external_sync_records_session_id_sessions
    foreign key (session_id)
    references public.sessions (id)
    on delete cascade,
  constraint fk_external_sync_records_user_id_auth_users
    foreign key (user_id)
    references auth.users (id)
    on delete cascade,
  constraint uq_external_sync_records_provider_resource
    unique (provider, resource_type, resource_key)
);

create index ix_floorplans_apartment_name_building_dong_size_type
  on public.floorplans (apartment_name, building_dong, size_type);
create index ix_floorplans_source_quality_status
  on public.floorplans (source, quality_status);
create index ix_floorplans_created_by_created_at
  on public.floorplans (created_by, created_at desc);
create index ix_floorplans_address_fingerprint
  on public.floorplans (address_fingerprint)
  where address_fingerprint is not null;
create unique index uq_floorplans_promoted_from_upload_id_not_null
  on public.floorplans (promoted_from_upload_id)
  where promoted_from_upload_id is not null;

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

create index ix_floorplan_uploads_session_id_created_at
  on public.floorplan_uploads (session_id, created_at desc);
create index ix_floorplan_uploads_user_id_created_at
  on public.floorplan_uploads (user_id, created_at desc);
create index ix_floorplan_uploads_status_created_at
  on public.floorplan_uploads (status, created_at desc);
create index ix_floorplan_uploads_original_asset_id
  on public.floorplan_uploads (original_asset_id);

create index ix_floorplan_assets_session_id_created_at
  on public.floorplan_assets (session_id, created_at desc);
create index ix_floorplan_assets_user_id_created_at
  on public.floorplan_assets (user_id, created_at desc);
create index ix_floorplan_assets_floorplan_id
  on public.floorplan_assets (floorplan_id);
create index ix_floorplan_assets_upload_id
  on public.floorplan_assets (upload_id);
create index ix_floorplan_assets_kind_created_at
  on public.floorplan_assets (kind, created_at desc);
create index ix_floorplan_assets_sha256
  on public.floorplan_assets (sha256)
  where sha256 is not null;

create index ix_floorplan_candidates_session_id_lookup_revision_rank
  on public.floorplan_candidates (session_id, lookup_revision, rank);
create index ix_floorplan_candidates_user_id_created_at
  on public.floorplan_candidates (user_id, created_at desc);
create index ix_floorplan_candidates_floorplan_id
  on public.floorplan_candidates (floorplan_id);

create index ix_chat_messages_session_id_message_order
  on public.chat_messages (session_id, message_order);
create index ix_chat_messages_user_id_created_at
  on public.chat_messages (user_id, created_at desc);

create index ix_chat_tool_calls_session_id_created_at
  on public.chat_tool_calls (session_id, created_at desc);
create index ix_chat_tool_calls_user_id_created_at
  on public.chat_tool_calls (user_id, created_at desc);
create index ix_chat_tool_calls_message_id
  on public.chat_tool_calls (message_id);
create index ix_chat_tool_calls_tool_name_status
  on public.chat_tool_calls (tool_name, status);

create index ix_processing_jobs_session_id_created_at
  on public.processing_jobs (session_id, created_at desc);
create index ix_processing_jobs_user_id_created_at
  on public.processing_jobs (user_id, created_at desc);
create index ix_processing_jobs_ready_queue
  on public.processing_jobs (priority, run_after, created_at)
  where status in ('queued', 'retrying');
create index ix_processing_jobs_locked_running
  on public.processing_jobs (locked_at)
  where status = 'running';

create index ix_webhook_deliveries_session_id_created_at
  on public.webhook_deliveries (session_id, created_at desc);
create index ix_webhook_deliveries_user_id_created_at
  on public.webhook_deliveries (user_id, created_at desc);
create index ix_webhook_deliveries_retry
  on public.webhook_deliveries (next_retry_at)
  where status in ('pending', 'failed');

create index ix_scheduled_task_runs_task_key_started_at
  on public.scheduled_task_runs (task_key, started_at desc);
create index ix_scheduled_task_runs_status_started_at
  on public.scheduled_task_runs (status, started_at desc);

create index ix_external_sync_records_session_id_created_at
  on public.external_sync_records (session_id, created_at desc);
create index ix_external_sync_records_user_id_created_at
  on public.external_sync_records (user_id, created_at desc);
create index ix_external_sync_records_status_last_synced_at
  on public.external_sync_records (status, last_synced_at);

alter table public.sessions enable row level security;
alter table public.session_addresses enable row level security;
alter table public.floorplans enable row level security;
alter table public.floorplan_uploads enable row level security;
alter table public.floorplan_assets enable row level security;
alter table public.floorplan_candidates enable row level security;
alter table public.chat_messages enable row level security;
alter table public.chat_tool_calls enable row level security;
alter table public.processing_jobs enable row level security;
alter table public.webhook_deliveries enable row level security;
alter table public.external_sync_records enable row level security;

create policy sessions_owner_select on public.sessions
  for select to authenticated
  using (user_id = (select auth.uid()));
create policy sessions_owner_insert on public.sessions
  for insert to authenticated
  with check (user_id = (select auth.uid()));
create policy sessions_owner_update on public.sessions
  for update to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

create policy session_addresses_owner_all on public.session_addresses
  for all to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

create policy floorplans_catalog_or_owner_select on public.floorplans
  for select to authenticated
  using (
    (visibility = 'public_catalog' and quality_status = 'verified')
    or created_by = (select auth.uid())
  );
create policy floorplans_owner_insert on public.floorplans
  for insert to authenticated
  with check (created_by = (select auth.uid()));
create policy floorplans_owner_update on public.floorplans
  for update to authenticated
  using (created_by = (select auth.uid()))
  with check (created_by = (select auth.uid()));

create policy floorplan_uploads_owner_all on public.floorplan_uploads
  for all to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

create policy floorplan_assets_owner_or_catalog_select on public.floorplan_assets
  for select to authenticated
  using (
    user_id = (select auth.uid())
    or exists (
      select 1
      from public.floorplans as floorplan
      where floorplan.id = floorplan_assets.floorplan_id
        and floorplan.visibility = 'public_catalog'
        and floorplan.quality_status = 'verified'
    )
  );
create policy floorplan_assets_owner_insert on public.floorplan_assets
  for insert to authenticated
  with check (user_id = (select auth.uid()));
create policy floorplan_assets_owner_update on public.floorplan_assets
  for update to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

create policy floorplan_candidates_owner_all on public.floorplan_candidates
  for all to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

create policy chat_messages_owner_all on public.chat_messages
  for all to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

create policy chat_tool_calls_owner_all on public.chat_tool_calls
  for all to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

create policy processing_jobs_owner_select on public.processing_jobs
  for select to authenticated
  using (user_id = (select auth.uid()));

create policy webhook_deliveries_owner_select on public.webhook_deliveries
  for select to authenticated
  using (user_id = (select auth.uid()));

create policy external_sync_records_owner_select on public.external_sync_records
  for select to authenticated
  using (user_id = (select auth.uid()));

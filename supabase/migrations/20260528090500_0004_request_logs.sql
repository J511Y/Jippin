-- CMP-575 Supabase SQL candidate for Alembic revision 0004_request_logs.

create table public.request_logs (
  id bigserial not null,
  created_at timestamp with time zone not null default now(),
  request_id uuid not null,
  is_anonymous_user boolean not null,
  user_id text,
  device_id text,
  version text,
  device text,
  country text,
  region text,
  ip_addrs text[] not null default '{}'::text[],
  last_ip inet,
  url text not null,
  parameter jsonb not null default '{}'::jsonb,
  method text not null,
  body jsonb,
  response_code integer not null,
  response_message text,
  error_code text,
  duration_ms integer not null,
  user_agent text,
  referrer text,
  constraint pk_request_logs primary key (id)
);

create index ix_request_logs_created_at
  on public.request_logs (created_at);

create index ix_request_logs_request_id
  on public.request_logs (request_id);

create index ix_request_logs_response_code
  on public.request_logs (response_code);

create index ix_request_logs_user_id_created_at
  on public.request_logs (user_id, created_at desc);

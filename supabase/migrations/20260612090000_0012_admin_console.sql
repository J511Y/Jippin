-- CMP-DIRECT 관리자 콘솔(apps/admin) 지원 스키마.
--
-- 1) consultation_leads 담당자 배정 컬럼 (관리자 auth.users 참조).
-- 2) consultation_lead_comments — 상담 건별 운영 댓글. PII 인접 데이터이므로
--    0009 리드 테이블과 동일하게 anon/authenticated 에 어떤 policy/grant 도 주지
--    않는다. 접근은 관리자 앱(service_role) 경로뿐이다.
-- 3) 대시보드 집계 RPC — PostgREST 는 GROUP BY 를 표현할 수 없으므로 집계는
--    security definer 함수로 제공한다. 함수 실행 권한은 service_role 단독.
--    (관리자 판별은 앱 레이어 — app_metadata.role='admin' 게이트 — 가 담당하고,
--    DB 레이어는 service_role 외 모든 role 의 실행을 차단하는 이중 방어.)

-- ---------------------------------------------------------------------------
-- 1. 담당자 배정
-- ---------------------------------------------------------------------------

alter table public.consultation_leads
  add column assigned_admin_id uuid,
  add column assigned_at timestamp with time zone;

alter table public.consultation_leads
  add constraint fk_consultation_leads_assigned_admin_id_users
    foreign key (assigned_admin_id)
    references auth.users (id)
    on delete set null;

create index ix_consultation_leads_assigned_admin_id
  on public.consultation_leads (assigned_admin_id)
  where assigned_admin_id is not null;

comment on column public.consultation_leads.assigned_admin_id is
  'Admin (auth.users with app_metadata.role=admin) assigned to handle this lead. Managed by apps/admin via service_role.';

-- ---------------------------------------------------------------------------
-- 2. 상담 댓글
-- ---------------------------------------------------------------------------

create table public.consultation_lead_comments (
  id uuid not null default gen_random_uuid(),
  lead_id uuid not null,
  author_id uuid,
  author_email text not null,
  body text not null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint pk_consultation_lead_comments primary key (id),
  constraint ck_consultation_lead_comments_body_not_blank check (
    length(btrim(body)) > 0
  ),
  constraint ck_consultation_lead_comments_body_max_length check (
    length(body) <= 4000
  ),
  constraint fk_consultation_lead_comments_lead_id_consultation_leads
    foreign key (lead_id)
    references public.consultation_leads (id)
    on delete cascade,
  constraint fk_consultation_lead_comments_author_id_users
    foreign key (author_id)
    references auth.users (id)
    on delete set null
);

create index ix_consultation_lead_comments_lead_id_created_at
  on public.consultation_lead_comments (lead_id, created_at);

comment on table public.consultation_lead_comments is
  'Operator comments per consultation lead. author_email is denormalized so the thread stays readable after an admin account is deleted. Written only via apps/admin (service_role); no PostgREST grants for anon/authenticated.';

-- 0009 consultation_leads 와 동일한 봉인: policy/grant 없음 → service_role 전용.
alter table public.consultation_lead_comments enable row level security;

-- ---------------------------------------------------------------------------
-- 3. 대시보드 집계 RPC (service_role 전용)
-- ---------------------------------------------------------------------------

-- 회원/리드/세션 핵심 수치 묶음.
create or replace function public.admin_dashboard_stats()
returns jsonb
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select jsonb_build_object(
    'member_total', (select count(*) from public.users where status = 'active'),
    'auth_member_total', (
      select count(*) from auth.users
      where coalesce(is_anonymous, false) = false
    ),
    'auth_anonymous_total', (
      select count(*) from auth.users
      where coalesce(is_anonymous, false) = true
    ),
    'lead_total', (select count(*) from public.consultation_leads),
    'lead_new', (
      select count(*) from public.consultation_leads where status = 'new'
    ),
    'lead_in_progress', (
      select count(*) from public.consultation_leads
      where status in ('contacted', 'in_progress')
    ),
    'lead_last_7d', (
      select count(*) from public.consultation_leads
      where created_at >= now() - interval '7 days'
    ),
    'session_total', (select count(*) from public.sessions),
    'session_active', (
      select count(*) from public.sessions
      where status not in ('expired', 'deleted')
    )
  );
$$;

-- 일자별 상담 인입량 (최근 days_back 일, 빈 날짜 0 채움, KST 기준 일자).
create or replace function public.admin_lead_daily_counts(days_back integer default 30)
returns table (day date, lead_count bigint)
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select
    d.day::date as day,
    count(l.id) as lead_count
  from generate_series(
    (now() at time zone 'Asia/Seoul')::date - (greatest(days_back, 1) - 1),
    (now() at time zone 'Asia/Seoul')::date,
    interval '1 day'
  ) as d(day)
  left join public.consultation_leads as l
    on (l.created_at at time zone 'Asia/Seoul')::date = d.day::date
  group by d.day
  order by d.day;
$$;

-- 에이전트(사전검토) 세션 상태별 분포 — 퍼널 차트용.
create or replace function public.admin_session_funnel()
returns table (status text, session_count bigint)
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select s.status, count(*) as session_count
  from public.sessions as s
  group by s.status;
$$;

-- 담당자 배정 드롭다운용 관리자 목록 (app_metadata.role='admin').
create or replace function public.admin_list_admins()
returns table (id uuid, email text)
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select u.id, u.email::text
  from auth.users as u
  where u.raw_app_meta_data ->> 'role' = 'admin'
  order by u.email;
$$;

-- 함수는 기본적으로 PUBLIC 에 EXECUTE 가 열리므로 명시적으로 회수한다.
revoke execute on function public.admin_dashboard_stats() from public, anon, authenticated;
revoke execute on function public.admin_lead_daily_counts(integer) from public, anon, authenticated;
revoke execute on function public.admin_session_funnel() from public, anon, authenticated;
revoke execute on function public.admin_list_admins() from public, anon, authenticated;

grant execute on function public.admin_dashboard_stats() to service_role;
grant execute on function public.admin_lead_daily_counts(integer) to service_role;
grant execute on function public.admin_session_funnel() to service_role;
grant execute on function public.admin_list_admins() to service_role;

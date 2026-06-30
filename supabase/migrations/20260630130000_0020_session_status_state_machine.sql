-- 사전검토 세션 상태 머신 정합화 + 상태 전이 이력 + 누적 퍼널 (CMP-DIRECT).
--
-- 배경: sessions.status 는 enum 으로 9단계(draft~handoff)를 정의하지만, 백엔드는 실제로
-- draft/address_ready 까지만 전이시켰다. 이후 단계(floorplan_selected~handoff)로 올리는
-- 코드 경로가 없었고, 설령 올리려 해도 reference-scope 트리거가 도면 소스를
-- selected_floorplan_id/upload_id 로만 인정해(에이전트 플로우는 selected_floorplan_asset_id
-- 만 씀) report_ready 등을 거부했다. 이번 변경:
--   1) reference-scope 트리거가 selected_floorplan_asset_id 도 유효한 도면 소스로 인정.
--   2) 상태 전이 이력 테이블(session_status_events) — 도구 완료 시 백엔드가 forward-only
--      전이를 기록한다(백엔드 advance_session_status). status 컬럼은 현재값, 이 테이블은 이력.
--   3) admin_session_funnel() 을 이력 기반 **누적**("이 단계 이상 도달")으로 재정의 —
--      group-by(현재 분포)는 뒤 단계가 앞 단계보다 많아질 수 있어 퍼널의 단조 감소를
--      보장하지 못한다. 누적은 보장한다. deleted 세션은 모수에서 제외(expired 는 포함).
-- 백필 없음(운영자 결정) — 기존 세션은 이벤트가 없어 신규 세션부터 퍼널에 반영된다.

-- 1) 상태 전이 이력 (append-only).
create table public.session_status_events (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.sessions (id) on delete cascade,
  from_status text,
  to_status text not null,
  reason text,
  run_id uuid,
  occurred_at timestamptz not null default now()
);

create index ix_session_status_events_session_id
  on public.session_status_events (session_id);
create index ix_session_status_events_to_status
  on public.session_status_events (to_status);

comment on table public.session_status_events is
  'Append-only log of sessions.status transitions (forward-only), written by the backend on tool/flow milestones. Source for the cumulative admin funnel. No client grants (service_role only).';

-- PII 아님이지만 클라이언트 직접 접근 불필요 — service_role 전용으로 봉인(grant 없음 + RLS).
alter table public.session_status_events enable row level security;

-- 2) reference-scope 트리거 — 분석 단계 진입 시 도면 소스로 selected_floorplan_asset_id 도
--    인정한다(에이전트 플로우 정합). 본문은 0008 원본과 동일하고, "도면 소스 필수" 검사에
--    asset_id null 조건만 추가했다. asset 유효성 검증 블록은 그대로 유지된다.
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
    'report_ready'
  )
    and new.selected_floorplan_id is null
    and new.selected_floorplan_upload_id is null
    and new.selected_floorplan_asset_id is null
  then
    raise exception 'sessions entering analysis must select a floorplan source'
      using errcode = '23514';
  end if;

  if new.status in (
    'analyzing',
    'awaiting_overlay',
    'collecting_info',
    'ready_for_rule',
    'report_ready'
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
    'report_ready'
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

-- 2b) status↔verdict 일관성 — 입력 변경으로 rule_eval_result 가 무효화(NULL)됐는데 status
--     가 report_ready 로 남으면, 관리자/세션 배지는 report_ready 인데 GET /report 는
--     REPORT_NOT_READY 가 되어 어긋난다. 0016 트리거(주소/도면/벽 변경 시 verdict 무효화)와
--     merge_judgment_schema 등 모든 무효화 경로를 한곳에서 받아, 남은 신호에 맞는 하위
--     단계로 status 를 되돌린다. handoff(실제 상담 전환)는 건드리지 않는다.
create or replace function public.enforce_session_status_verdict_consistency()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  -- report_ready 인데 판정/입력이 더는 유효하지 않으면(verdict NULL 또는 도면·주소 포인터
  -- 소실) 남은 신호에 맞는 하위 단계로 status 를 낮춘다.
  if new.status = 'report_ready'
    and (
      new.rule_eval_result is null
      or new.selected_floorplan_asset_id is null
      or new.address_id is null
    )
  then
    new.status := case
      when new.selected_floorplan_asset_id is not null
           and new.address_id is not null
           and (new.judgment_schema ? 'selected_walls') then 'collecting_info'
      when new.selected_floorplan_asset_id is not null
           and new.address_id is not null
           and (new.judgment_schema ? 'wall_objects') then 'awaiting_overlay'
      when new.selected_floorplan_asset_id is not null then 'floorplan_selected'
      when new.address_id is not null then 'address_ready'
      else 'draft'
    end;
  end if;
  return new;
end;
$$;

-- reference-scope(trg_sessions_reference_scope) **앞**(이름순)에 두어야 한다 — 도면/주소
-- 포인터가 비워진 report_ready 행을 reference-scope 가 먼저 검증하면 "분석 단계엔 도면/주소
-- 필수" 로 raise 해 FK ON DELETE SET NULL / 명시적 입력 해제를 통째로 막는다(리뷰 지적).
-- 'trg_sessions_p_' 접두는 invalidate_verdict(i) 뒤·reference_scope(r) 앞에 발화하게 한다.
create trigger trg_sessions_p_status_verdict_consistency
  before update on public.sessions
  for each row
  when (
    new.status = 'report_ready'
    and (
      new.rule_eval_result is null
      or new.selected_floorplan_asset_id is null
      or new.address_id is null
    )
  )
  execute function public.enforce_session_status_verdict_consistency();

-- 3) 퍼널 — 각 단계를 그 단계의 **실제 이벤트**를 가진 세션 수로 센다(단계별 distinct).
--    rank 누적(max_rank >= S)은 건너뛴 단계까지 도달한 것으로 집계해(예: 주소 없이 도면을
--    먼저 올린 세션이 address_ready 에, 상담만 한 세션이 analyzing/report_ready 에) 전환을
--    부풀린다(리뷰 지적). "그 단계 이벤트가 실제로 있었는가"로 세면 정확하고, 순차 흐름에선
--    여전히 좁아진다(상위 단계 세션은 거쳐온 하위 단계 이벤트를 모두 갖는다). 현재 status 가
--    deleted 인 세션은 모수에서 제외(테스트/스팸 정리분).
create or replace function public.admin_session_funnel()
returns table (status text, session_count bigint)
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  with stages(name, rank) as (
    values
      ('draft', 0), ('address_ready', 1), ('floorplan_selected', 2),
      ('analyzing', 3), ('awaiting_overlay', 4), ('collecting_info', 5),
      ('ready_for_rule', 6), ('report_ready', 7), ('handoff', 8)
  ),
  reached as (
    select distinct e.to_status, e.session_id
    from public.session_status_events as e
    join public.sessions as s
      on s.id = e.session_id and s.status <> 'deleted'
  )
  select
    st.name as status,
    count(r.session_id) as session_count
  from stages as st
  left join reached as r on r.to_status = st.name
  group by st.name, st.rank
  order by st.rank;
$$;

revoke execute on function public.admin_session_funnel() from public, anon, authenticated;
grant execute on function public.admin_session_funnel() to service_role;

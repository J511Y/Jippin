-- 0016 Session report — 사전검토 세션의 룰 판정 결과 영속화 + 도면 버킷 (CMP-DIRECT).
--
-- 에이전트가 evaluate_rules 로 만든 rule-eval-result(verdict/required_facilities/
-- legal_basis/user_message 등)는 지금까지 chat_messages.judgment_snapshot 에만
-- 흩어져 있어 독립 리포트(GET /sessions/{id}/report)로 노출할 정본이 없었다.
-- 세션에 최종 판정을 단일 verdict 로 영속해 리포트의 source of truth 로 삼는다.
--
-- rule_eval_result: rule-eval-result 계약 그대로의 JSON(평가 시점 evaluated_at 포함).
-- rule_evaluated_at: 마지막으로 판정을 기록한 시각(리포트 신선도 표시용).
-- 이 컬럼이 NULL 이면 리포트 미준비(REPORT_NOT_READY).

alter table public.sessions
  add column if not exists rule_eval_result jsonb,
  add column if not exists rule_evaluated_at timestamp with time zone;

-- ---------------------------------------------------------------------------
-- 클라이언트 쓰기 가드 — rule_eval_result/rule_evaluated_at 도 service-controlled.
--
-- 0008 의 sessions_owner_all + authenticated UPDATE grant 때문에, 가드 트리거가
-- 막지 않으면 세션 소유자가 PostgREST 로 verdict JSON 을 위조할 수 있다(리포트가
-- 이 값을 정본으로 신뢰하므로 위험). 기존 트리거 함수를 확장해 두 컬럼을 추가로
-- 막는다(백엔드 service role 은 current_role<>'authenticated' 라 early-return).
-- ---------------------------------------------------------------------------
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
      or new.rule_eval_result is not null
      or new.rule_evaluated_at is not null
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
    or new.rule_eval_result is distinct from old.rule_eval_result
    or new.rule_evaluated_at is distinct from old.rule_evaluated_at
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

-- ---------------------------------------------------------------------------
-- 리포트-입력 일관성 — 입력(주소/도면 포인터)이 바뀌면 영속된 verdict 를 무효화.
--
-- GET /sessions/{id}/report 는 rule_eval_result 를 정본으로 신뢰한다. 그런데 0008 의
-- 완료-포인터 가드는 (1) authenticated 역할에만 적용되고 (2) 세션이 report 상태일 때만
-- 동작한다 — service-role API(create_floorplan_asset)나 report 상태 이전의 포인터 변경은
-- 막지 못해, 새 도면에 옛 판정이 붙는 사고가 난다. 역할/상태 무관 트리거로 입력 포인터가
-- 바뀌면 verdict 를 비워 리포트가 항상 현재 입력과 일치하게 한다(#verdict-input-consistency).
-- ---------------------------------------------------------------------------
create or replace function public.invalidate_session_verdict_on_input_change()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if new.address_id is distinct from old.address_id
    or new.selected_floorplan_id is distinct from old.selected_floorplan_id
    or new.selected_floorplan_upload_id is distinct from old.selected_floorplan_upload_id
    or new.selected_floorplan_asset_id is distinct from old.selected_floorplan_asset_id
  then
    new.rule_eval_result := null;
    new.rule_evaluated_at := null;
    -- 흐름 결정(PROCEED_RULE/HOLD_OR_HANDOFF 등)도 옛 입력 기준이므로 함께 비운다.
    -- 상세 UI 가 completion_decision 비-null 을 report-ready 로 보기 때문(#stale-decision).
    new.completion_decision := null;
  end if;
  return new;
end;
$$;

create trigger trg_sessions_invalidate_verdict
  before update of
    address_id,
    selected_floorplan_id,
    selected_floorplan_upload_id,
    selected_floorplan_asset_id
  on public.sessions
  for each row
  execute function public.invalidate_session_verdict_on_input_change();

-- 주소 행 in-place 수정(PUT /sessions/{id}/address 는 같은 session_addresses 행을
-- upsert 하므로 sessions.address_id 포인터는 그대로다)도 입력 변경이다. 부모 세션의
-- verdict/decision 을 무효화한다(#address-row-edit). SECURITY DEFINER 로 실행해 cascade
-- UPDATE 가 authenticated client 가드(prevent_session_client_service_field_mutation)에
-- 막히지 않게 한다(definer 컨텍스트에선 current_role 이 authenticated 가 아님).
create or replace function public.invalidate_session_verdict_on_address_change()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  update public.sessions
    set rule_eval_result = null,
        rule_evaluated_at = null,
        completion_decision = null
    where id = new.session_id
      and (
        rule_eval_result is not null
        or rule_evaluated_at is not null
        or completion_decision is not null
      );
  return new;
end;
$$;

create trigger trg_session_addresses_invalidate_verdict
  after insert or update on public.session_addresses
  for each row
  execute function public.invalidate_session_verdict_on_address_change();

-- ---------------------------------------------------------------------------
-- floorplan_assets 클라이언트 쓰기 차단 — asset 메타는 백엔드(service-role)만 작성.
--
-- 0008 의 owner/session insert·update RLS 정책은 authenticated 클라이언트가 PostgREST
-- 로 직접 asset row(bucket/object_key/scan_status)를 만들거나 바꾸게 허용한다. 그러면
-- /sessions/upload-url(presign)·POST /floorplan-assets(owner-folder+content-type 검증)를
-- 우회해 임의 pending asset 을 심을 수 있고, 기본 allow_unscanned=true 라 세그멘테이션이
-- 그 untrusted 객체를 서명·전달한다. 프론트는 백엔드 라우트(service-role, RLS 우회)로만
-- asset 을 만들므로, 클라이언트 insert/update 정책을 제거해 pending=백엔드검증 으로 신뢰
-- 가능하게 한다(#trusted-pending). 읽기/삭제 정책은 유지.
-- ---------------------------------------------------------------------------
drop policy if exists floorplan_assets_owner_or_session_insert on public.floorplan_assets;
drop policy if exists floorplan_assets_owner_or_session_update on public.floorplan_assets;

-- ---------------------------------------------------------------------------
-- Supabase Storage — session-floorplans 비공개 버킷 + owner-folder 정책.
--
-- 사전검토 도면 업로드 전용. 프론트는 presigned PUT(S3 자격증명)로 올리고, 세그멘테이션은
-- service_role 서명 URL 로만 읽는다. 직접 SDK 접근 대비 owner-folder 정책도 둔다
-- (leads 의 lead-floorplans 패턴). 각 branch 의 Storage 활성화는 콘솔에서 선행해야
-- storage.* 스키마가 존재한다(ADR-0007).
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public)
values ('session-floorplans', 'session-floorplans', false)
on conflict (id) do nothing;

create policy session_floorplans_owner_insert
  on storage.objects
  for insert
  to authenticated
  with check (
    bucket_id = 'session-floorplans'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

create policy session_floorplans_owner_read
  on storage.objects
  for select
  to authenticated
  using (
    bucket_id = 'session-floorplans'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

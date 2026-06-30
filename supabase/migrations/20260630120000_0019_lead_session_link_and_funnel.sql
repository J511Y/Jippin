-- 사전검토 세션 ↔ 상담 리드 연결 (CMP-DIRECT).
--
-- 사전검토(precheck_session) 인입 상담 리드가 어느 세션에서 왔는지 추적할 FK 가 없어
-- 관리자가 세션↔상담을 교차 참조할 수 없었고, 도로명 없는(아파트명만) 세션에서 만든
-- 리드의 주소가 공란이 되곤 했다. → consultation_leads.session_id 를 추가한다(nullable +
-- ON DELETE SET NULL — 리드는 영업 자산이라 세션이 정리돼도 보존, user_id 와 동일 정책).
-- 백엔드가 사전검토 상담 생성 시 본인 세션이면 이 컬럼을 채우고, 주소가 비면 세션 확정
-- 주소(아파트명 포함)로 폴백한다. 이 컬럼은 상태 퍼널(0020)의 handoff 신호로도 쓰인다.

alter table public.consultation_leads
  add column if not exists session_id uuid;

alter table public.consultation_leads
  add constraint fk_consultation_leads_session_id_sessions
  foreign key (session_id)
  references public.sessions (id)
  on delete set null;

create index if not exists ix_consultation_leads_session_id
  on public.consultation_leads (session_id);

comment on column public.consultation_leads.session_id is
  'Originating pre-check (agent) session, when the lead was created from a session handoff/CTA. Nullable + ON DELETE SET NULL so leads survive session cleanup.';

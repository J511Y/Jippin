-- 사전검토(채팅 세션) 인입 상담을 lead_page 와 명확히 구분하기 위해 consultation_leads.
-- source_form 에 'precheck_session' 추가 (CHECK drop→재생성, 0014 의 property_check 추가와
-- 동일 패턴). 사전검토 빠른 상담폼은 이름/연락처만 받으므로 full-form 필수 필드를 요구하지
-- 않는다 — ck_consultation_leads_full_form_required 는 source_form <> 'lead_page' 게이트라
-- precheck_session 에 영향이 없으므로 그대로 둔다.
alter table public.consultation_leads
  drop constraint ck_consultation_leads_source_form_allowed;
alter table public.consultation_leads
  add constraint ck_consultation_leads_source_form_allowed check (
    source_form in ('main_page', 'lead_page', 'property_check', 'precheck_session')
  );

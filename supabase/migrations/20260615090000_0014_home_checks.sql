-- 0014 우리집 체크(home-check) — 집합건축물대장 전유부 + 표제부 조회 잡/판정/요약.
-- 결정 정본: docs/adr/0008-home-check-building-register.md
--
-- 보관 원칙
--   * 발급 PDF(resOriGinalData)를 SoT 원본으로 Supabase Storage(home-check-docs)에 보관하고,
--     DB 에는 판정·표시에 필요한 최소 필드만 둔다(home_check_documents 가 포인터).
--   * 소유자/설계자 등 PII(resOwnerList, resLicenseClassList)는 구조화 저장하지 않는다 — 원본 PDF 로만 확인.
--   * 세움터 password / 주민번호 전체값은 어디에도(로그/Redis/DB) 저장하지 않는다.
--   * consultation_leads 와 동일하게 PII 테이블이므로 authenticated/anon grant 없이
--     백엔드 풀 role 로만 접근한다(PostgREST 차단). user_id nullable + ON DELETE SET NULL.
--
-- 위반(노란딱지) 판정: 전유부 resViolationStatus 또는 표제부 resViolationStatus 가 '위반건축물' → violation.
-- 표제부 병행 조회로 건물 단위 위반 누락(위음성)을 방지한다.

create table public.home_checks (
  id uuid not null default gen_random_uuid(),
  user_id uuid,
  is_anonymous boolean not null default false,

  -- 잡 상태 / 종합 판정
  status text not null default 'pending',
  signal text,

  -- 조회 주소 (도로명주소 팝업 입력 + 정규화)
  road_addr text,
  jibun_addr text,
  addr_dong text,
  addr_ho text,

  -- 건축물 식별자 (전유부 / 표제부)
  comm_unique_no text,
  heading_comm_unique_no text,
  res_doc_no text,
  heading_res_doc_no text,
  res_issue_date date,

  -- 위반 표시 (전유부 + 표제부 병행)
  exclusive_violation boolean,
  heading_violation boolean,
  violation boolean,

  -- 전유부 요약 (전유부분 resType="0")
  exclusive_area_m2 numeric,
  exclusive_use_type text,
  exclusive_structure text,
  exclusive_floor text,

  -- 표제부 요약 (건물 단위)
  building_main_use text,
  building_floors text,
  building_approval_date date,
  building_permit_date date,

  -- 가변 데이터 (전부 PII 미포함 — 주민번호/성명/면허 저장 금지)
  change_list jsonb not null default '[]'::jsonb,
  price_list jsonb not null default '[]'::jsonb,
  heading_detail jsonb not null default '{}'::jsonb,
  result_fields jsonb not null default '{}'::jsonb,

  -- 상담 인입 연결
  consultation_lead_id uuid,

  -- 운영
  error_code text,
  error_message text,
  queried_at timestamp with time zone,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),

  constraint pk_home_checks primary key (id),
  constraint ck_home_checks_status_allowed check (
    status in ('pending', 'querying', 'needs_input', 'completed', 'failed')
  ),
  constraint ck_home_checks_signal_allowed check (
    signal is null or signal in ('violation', 'caution', 'normal')
  ),
  constraint ck_home_checks_signal_requires_completed check (
    signal is null or status = 'completed'
  ),
  constraint fk_home_checks_user_id_users
    foreign key (user_id) references auth.users (id) on delete set null,
  constraint fk_home_checks_consultation_lead_id_consultation_leads
    foreign key (consultation_lead_id)
    references public.consultation_leads (id) on delete set null
);

-- 발급 PDF(전유부/표제부) Storage object 포인터. 바이너리는 home-check-docs 버킷.
create table public.home_check_documents (
  id uuid not null default gen_random_uuid(),
  home_check_id uuid not null,
  kind text not null,
  bucket text not null,
  object_path text not null,
  byte_size bigint,
  created_at timestamp with time zone not null default now(),

  constraint pk_home_check_documents primary key (id),
  constraint ck_home_check_documents_kind_allowed check (
    kind in ('exclusive_part', 'building_heading')
  ),
  constraint uq_home_check_documents_home_check_id_kind unique (home_check_id, kind),
  constraint uq_home_check_documents_bucket_object_path unique (bucket, object_path),
  constraint fk_home_check_documents_home_check_id_home_checks
    foreign key (home_check_id)
    references public.home_checks (id) on delete cascade
);

-- consultation_leads.source_form 에 property_check 추가 (CHECK drop→재생성).
-- ck_consultation_leads_full_form_required 는 source_form <> 'lead_page' 게이트라 영향 없음.
alter table public.consultation_leads
  drop constraint ck_consultation_leads_source_form_allowed;
alter table public.consultation_leads
  add constraint ck_consultation_leads_source_form_allowed check (
    source_form in ('main_page', 'lead_page', 'property_check')
  );

-- 인덱스
create index ix_home_checks_user_id_created_at
  on public.home_checks (user_id, created_at desc);
create index ix_home_checks_status_created_at
  on public.home_checks (status, created_at desc);
create index ix_home_checks_comm_unique_no
  on public.home_checks (comm_unique_no) where comm_unique_no is not null;
create index ix_home_checks_consultation_lead_id
  on public.home_checks (consultation_lead_id) where consultation_lead_id is not null;
create index ix_home_check_documents_home_check_id
  on public.home_check_documents (home_check_id);

comment on table public.home_checks is
  'Home-check (집합건축물대장 전유부+표제부) lookup jobs, judgment, and PII-free summary. '
  'Backend-only access (no PostgREST/anon grants), like consultation_leads. Never stores Seumter '
  'password, full resident registration numbers, owner/architect names, or raw CODEF data — the '
  'issued PDF in Storage is the source-of-truth original.';
comment on column public.home_checks.violation is
  'Overall violation flag = exclusive_violation OR heading_violation (CODEF resViolationStatus == 위반건축물).';
comment on column public.home_checks.result_fields is
  'Extracted, PII-free fields only. Never store passwords, resident numbers, names, or PDF base64.';
comment on table public.home_check_documents is
  'Pointers to issued building-register PDFs (exclusive_part / building_heading) in the home-check-docs Storage bucket.';

-- RLS: PII 테이블. authenticated/anon 에 policy/grant 미부여 → 백엔드 풀 role 로만 접근.
-- 마이페이지 이력도 백엔드 API 가 서빙한다(consultation_leads 와 동일 경로).
alter table public.home_checks enable row level security;
alter table public.home_check_documents enable row level security;

-- Supabase Storage — home-check-docs 비공개 버킷. 백엔드(service role) 가 PDF write/read,
-- 사용자에게는 백엔드 서명 URL 로 제공한다(클라이언트 직접 접근 없음 → owner-folder 정책 불필요).
insert into storage.buckets (id, name, public)
values ('home-check-docs', 'home-check-docs', false)
on conflict (id) do nothing;

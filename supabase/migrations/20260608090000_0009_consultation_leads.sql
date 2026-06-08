-- CMP-DIRECT 상담 리드(consultation leads) 저장 스키마.
--
-- 비회원(Supabase Anonymous Sign-In)도 상담 신청을 할 수 있다(요구사항). 따라서
-- 본 테이블은 ADR-0004 §5.3 #11 / AGENTS §4.7 의 conversion-only(is_anonymous=false)
-- 봉인을 사용자 결정으로 override 한다 — 익명 owner 도 리드를 생성할 수 있다.
--
-- 리드는 영업 자산이므로 익명 user 가 TTL cleanup 으로 삭제되어도 보존되어야 한다.
-- 그래서 user_id 는 nullable + ON DELETE SET NULL 이다(기존 도메인 테이블의
-- ON DELETE CASCADE 와 의도적으로 다르다).
--
-- 평면도 첨부 바이너리는 Supabase Storage(`lead-floorplans` 버킷)에 두고, 본 DB 에는
-- object metadata(버킷/경로)만 저장한다. Supabase Storage 도입은 ADR-0007 참조
-- (ADR-0004 의 R2 정본 + [storage].enabled=false 봉인을 사용자 결정으로 override).

create table public.consultation_leads (
  id uuid not null default gen_random_uuid(),
  user_id uuid,
  is_anonymous boolean not null default false,
  source_form text not null,
  applicant_kind text not null default 'individual',
  applicant_name text not null,
  applicant_phone text not null,
  road_addr_part1 text,
  road_addr_part2 text,
  road_addr_detail text,
  expansion_location text,
  ownership_status text,
  construction_start_date date,
  construction_end_date date,
  inflow_source text,
  message text,
  status text not null default 'new',
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint pk_consultation_leads primary key (id),
  constraint ck_consultation_leads_source_form_allowed check (
    source_form in ('main_page', 'lead_page')
  ),
  constraint ck_consultation_leads_applicant_kind_allowed check (
    applicant_kind in ('individual', 'company')
  ),
  constraint ck_consultation_leads_ownership_status_allowed check (
    ownership_status is null
    or ownership_status in ('in_transaction', 'owner')
  ),
  constraint ck_consultation_leads_inflow_source_allowed check (
    inflow_source is null
    or inflow_source in ('naver_search', 'blog', 'acquaintance', 'cafe', 'etc')
  ),
  constraint ck_consultation_leads_status_allowed check (
    status in ('new', 'contacted', 'in_progress', 'closed', 'spam')
  ),
  constraint ck_consultation_leads_construction_period_order check (
    construction_start_date is null
    or construction_end_date is null
    or construction_end_date >= construction_start_date
  ),
  -- 전체 상담 신청 폼(lead_page)은 도로명 주소(part1/detail), 확장 위치, 상태 구분이
  -- 필수다(defense-in-depth — API Pydantic 검증과 정합). main_page 간소화 폼은 면제.
  constraint ck_consultation_leads_full_form_required check (
    source_form <> 'lead_page'
    or (
      road_addr_part1 is not null
      and road_addr_detail is not null
      and expansion_location is not null
      and ownership_status is not null
    )
  ),
  constraint fk_consultation_leads_user_id_users
    foreign key (user_id)
    references auth.users (id)
    on delete set null
);

create table public.consultation_lead_attachments (
  id uuid not null default gen_random_uuid(),
  lead_id uuid not null,
  bucket text not null,
  object_path text not null,
  file_name text,
  content_type text,
  byte_size bigint,
  created_at timestamp with time zone not null default now(),
  constraint pk_consultation_lead_attachments primary key (id),
  constraint ck_consultation_lead_attachments_byte_size_nonnegative check (
    byte_size is null or byte_size >= 0
  ),
  constraint uq_consultation_lead_attachments_bucket_object_path
    unique (bucket, object_path),
  constraint fk_consultation_lead_attachments_lead_id_consultation_leads
    foreign key (lead_id)
    references public.consultation_leads (id)
    on delete cascade
);

create index ix_consultation_leads_status_created_at
  on public.consultation_leads (status, created_at desc);
create index ix_consultation_leads_user_id_created_at
  on public.consultation_leads (user_id, created_at desc);
create index ix_consultation_leads_applicant_phone
  on public.consultation_leads (applicant_phone);
create index ix_consultation_leads_created_at
  on public.consultation_leads (created_at desc);

create index ix_consultation_lead_attachments_lead_id
  on public.consultation_lead_attachments (lead_id);

comment on table public.consultation_leads is
  'Consultation/sales leads. PII — written only by the FastAPI backend; no PostgREST/client grants. user_id is nullable (ON DELETE SET NULL) so leads survive anonymous-user cleanup.';
comment on table public.consultation_lead_attachments is
  'Supabase Storage object metadata for lead attachments (e.g. unit floorplans). Bucket/path only; binaries live in the lead-floorplans bucket.';

-- RLS: 리드는 PII 다. authenticated/anon 에 어떤 policy/grant 도 부여하지 않아
-- PostgREST(현재 [api].enabled=false 로 이미 차단)나 anon key 로 직접 조회/쓰기를
-- 막는다. 백엔드는 DATABASE_POOL_URL 의 권한 role 로 연결해 RLS 를 우회 INSERT 한다
-- (기존 request_logs 와 동일 경로).
alter table public.consultation_leads enable row level security;
alter table public.consultation_lead_attachments enable row level security;

-- ---------------------------------------------------------------------------
-- Supabase Storage — lead-floorplans 비공개 버킷 + owner-folder 정책.
--
-- 프론트는 익명/영구 Supabase 세션(role=authenticated)으로 `<auth.uid()>/<file>`
-- 경로에만 업로드한다. 업로드 후 object 경로를 백엔드 POST /leads 로 전달한다.
-- (ADR-0007 — Supabase Storage 도입 결정. 각 branch 의 Storage 서비스 활성화는
-- 콘솔에서 수행해야 storage.* 스키마가 존재한다.)
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public)
values ('lead-floorplans', 'lead-floorplans', false)
on conflict (id) do nothing;

create policy lead_floorplans_owner_insert
  on storage.objects
  for insert
  to authenticated
  with check (
    bucket_id = 'lead-floorplans'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

create policy lead_floorplans_owner_read
  on storage.objects
  for select
  to authenticated
  using (
    bucket_id = 'lead-floorplans'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

-- DELETE 정책은 의도적으로 두지 않는다. POST /leads 로 리드에 연결된 첨부를 제출자가
-- 직접 삭제하면 DB row 는 남고 파일만 사라져(운영자 화면의 dangling 참조) 제출 증거가
-- 훼손될 수 있다. 정리/삭제는 백엔드(service role) 경로로만 처리한다.

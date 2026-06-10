-- CMP-DIRECT 자주묻는질문(FAQ) 저장 스키마 + 초기 시드.
--
-- FAQ 는 공개 콘텐츠다(PII 아님). 공개 읽기는 FastAPI ``GET /faqs`` 백엔드 경로를
-- 통하며, 백엔드는 DATABASE_POOL_URL 의 권한 role 로 접속해 RLS 를 우회 SELECT 한다
-- (기존 도메인 테이블과 동일 경로). 따라서 anon/authenticated 에 grant/policy 를
-- 부여하지 않는다([api].enabled=false 로 PostgREST 직접 접근도 이미 차단).
--
-- ``answer`` 는 마크다운 텍스트를 보관한다(링크·이미지·목록 등 마크업 포함 가능).
-- 렌더링은 프론트(`/faq`)가 담당한다.
--
-- ``category`` 는 안정적인 영문 슬러그로 보관하고, 한국어 라벨/카테고리 순서는
-- 프론트(`apps/web/lib/faq.ts`)가 소유한다. Phase 3 관리자 편집 UI 에서 드롭다운으로
-- 노출한다. 본 시드는 프론트 정적 폴백(`FAQ_FALLBACK`)과 동일 내용으로 유지한다.

create table public.faqs (
  id uuid not null default gen_random_uuid(),
  category text not null,
  question text not null,
  answer text not null,
  sort_order integer not null default 0,
  is_published boolean not null default true,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint pk_faqs primary key (id),
  constraint ck_faqs_category_allowed check (
    category in (
      'cost', 'prereview', 'glossary', 'act_permit',
      'resident_consent', 'fireproofing', 'use_inspection'
    )
  )
);

-- 공개 목록 조회용 부분 인덱스 — 노출 행만 카테고리/정렬 순으로 읽는 단일 경로.
create index ix_faqs_published_category_sort_order
  on public.faqs (category, sort_order)
  where is_published;

comment on table public.faqs is
  'Public FAQ content (not PII). Read via the FastAPI GET /faqs path; no PostgREST/client grants. answer holds markdown; category is an English slug mapped to a Korean label by the web app.';

-- RLS: 공개 콘텐츠지만 다른 도메인 테이블과 동일하게 백엔드 경유 읽기만 허용한다.
-- anon/authenticated 에 어떤 policy/grant 도 부여하지 않는다(백엔드 권한 role 로 우회).
alter table public.faqs enable row level security;

-- ---------------------------------------------------------------------------
-- 초기 시드 (20문항 / 7카테고리). 운영자가 추후 관리자 화면(Phase 3)에서 수정한다.
-- ---------------------------------------------------------------------------
insert into public.faqs (category, sort_order, question, answer) values
  ('cost', 1,
   '사전검토 비용은 얼마인가요?',
   '**AI 사전검토는 무료**입니다. 평면도 한 장과 주소만 입력하면 비용 없이 철거·확장 가능성과 행위허가 필요 여부를 확인할 수 있어요. [무료로 사전검토 시작하기](/sessions/new)'),
  ('cost', 2,
   '전문가 상담·대행·시공 비용은 어떻게 책정되나요?',
   '상담·동의서/행위허가 대행·시공 비용은 **현장 조건(면적·구조·세대 수 등)에 따라 달라져** 사전 진단 후 견적으로 안내합니다. 자세한 항목은 [가격 안내](/prices)를 참고해 주세요.'),
  ('cost', 3,
   '견적을 받으면 꼭 진행해야 하나요?',
   '아니요. 사전검토와 견적 확인까지는 **부담 없이 무료**이며, 진행 여부는 견적과 상담 내용을 확인한 뒤 결정하시면 됩니다.'),

  ('prereview', 1,
   '사전검토는 시간이 얼마나 걸리나요?',
   '평면도 한 장과 주소만 입력하면 **로그인 없이 약 1분**이면 됩니다. 철거·확장 가능성, 주의 구간, 행위허가 필요 여부를 신호등 리포트로 바로 확인할 수 있어요.'),
  ('prereview', 2,
   '사전검토에 무엇을 준비해야 하나요?',
   '**평면도 이미지 한 장과 주소**면 충분합니다. 평면도는 분양 카탈로그, 건축물현황도, 관리사무소 도면 등 어떤 형태든 좋고, 사진이나 캡처 이미지도 AI 가 벽체·개구부·치수를 인식합니다.'),
  ('prereview', 3,
   '사전검토 결과는 법적 효력이 있나요?',
   'AI 사전검토는 **가능성을 빠르게 진단하는 참고 자료**입니다. 최종 가부는 전문가 검토와 구조안전확인, 관할 지자체의 행위허가로 확정되며, 집핀이 그 절차까지 연결해 드립니다.'),

  ('glossary', 1,
   '내력벽과 비내력벽은 어떻게 다른가요?',
   E'- **내력벽**: 건물의 하중(무게)을 지지하는 벽으로, 원칙적으로 철거할 수 없습니다.\n- **비내력벽(가벽)**: 하중을 받지 않는 칸막이 벽으로, 일반적으로 철거·이동이 가능합니다.\n\n집핀 AI 는 평면도에서 두 벽을 자동으로 판별해 위험 구간을 진단합니다.'),
  ('glossary', 2,
   '행위허가가 무엇인가요?',
   '**행위허가**는 발코니 확장처럼 건축물의 구조·용도에 영향을 주는 공사를 하기 전에 관할 지자체(구청 등)로부터 받아야 하는 허가(또는 신고)입니다. 보통 입주민 동의서, 검인 도면, 구조안전확인서 등이 필요합니다.'),
  ('glossary', 3,
   '건축물대장 등재는 무엇인가요?',
   '공사 완료 후 **사용검사**를 거쳐 변경된 내용을 **건축물대장**에 정식으로 기록하는 절차입니다. 이 절차까지 마쳐야 법적으로 공사가 완료된 것으로 인정됩니다.'),

  ('act_permit', 1,
   '베란다(발코니) 확장에 행위허가가 꼭 필요한가요?',
   '발코니 확장 자체는 건축법상 허용되지만, **대부분 관할 지자체의 행위허가(또는 신고)와 입주민 동의가 필요**합니다. 집핀이 필요 여부를 사전검토하고, 서류 준비부터 접수까지 대행합니다.'),
  ('act_permit', 2,
   '행위허가는 얼마나 걸리나요?',
   '동의서·검인 도면·구조안전확인서·철거 사유서 준비부터 지자체 접수까지 **약 7일** 정도 소요됩니다. (현장·지자체 상황에 따라 달라질 수 있습니다.)'),
  ('act_permit', 3,
   '행위허가 없이 공사하면 어떻게 되나요?',
   '허가 없이 구조를 변경하면 **위반건축물로 분류**되어 이행강제금 부과, 원상복구 명령 등의 불이익을 받을 수 있습니다. 반드시 사전검토와 허가 절차를 거치는 것을 권장합니다.'),

  ('resident_consent', 1,
   '입주민 동의서는 꼭 받아야 하나요?',
   '네. 발코니 확장 등 행위허가가 필요한 공사는 단지·지자체 기준에 따라 **인접 세대의 동의서가 필수**인 경우가 많습니다. 집핀이 방문부터 서명 수령까지 대행합니다.'),
  ('resident_consent', 2,
   '몇 세대의 동의가 필요한가요?',
   '동의 대상은 단지와 지자체 기준에 따라 다르며, 보통 **직상·직하·좌우 인접 세대** 등이 포함됩니다. 정확한 대상은 사전검토와 상담에서 안내해 드립니다.'),
  ('resident_consent', 3,
   '동의를 안 해주는 세대가 있으면 어떻게 되나요?',
   '담당자가 평일 저녁·주말에 직접 방문하고 부재 세대도 끝까지 재방문해 동의를 받습니다. 다만 끝내 동의가 어려운 경우의 한계도 상담 단계에서 미리 안내해 드립니다.'),

  ('fireproofing', 1,
   '발코니 확장 시 방화판·방화유리가 꼭 필요한가요?',
   '네. 발코니를 확장하면 인접 세대로의 화재 확산을 막기 위해 **90cm 이상의 방화판 또는 방화유리 설치가 의무**입니다. 집핀은 건축법 및 **KS F 2845** 기준에 맞춰 시공합니다.'),
  ('fireproofing', 2,
   '확장하면 결로나 단열 문제가 생기지 않나요?',
   '확장부는 단열·새시 시공 기준에 맞춰 진행해 결로 위험을 관리합니다. 세대별 상황에 따라 필요한 보강 범위를 상담에서 안내해 드립니다.'),
  ('fireproofing', 3,
   '사전검토나 허가만 따로 받을 수도 있나요?',
   '네. 사전검토 / 전문가 상담 / 행위허가 대행 / 시공을 **필요한 단계만 골라** 진행할 수 있습니다.'),

  ('use_inspection', 1,
   '사용검사는 왜 받아야 하나요?',
   '사용검사는 공사가 법 기준에 맞게 완료됐는지 확인받는 절차입니다. 이 검사를 통과하고 **건축물대장에 등재**해야 비로소 법적으로 공사가 완료됩니다.'),
  ('use_inspection', 2,
   '사용검사·건축물대장 등재까지 집핀이 해주나요?',
   '네. 집핀은 사전검토부터 행위허가, 방화판·방화유리 시공, **사용검사 신청과 건축물대장 등재까지 전 과정**을 대행합니다. 2007년부터 행위허가만 누적 2만5천여 건을 처리했습니다.');

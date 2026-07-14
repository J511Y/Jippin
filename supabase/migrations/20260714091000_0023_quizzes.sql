-- 0023 대기 화면 퀴즈 — DB 편집형 콘텐츠 (faqs v2 컨벤션 미러).
--
-- 우리집 체크 대기 화면(건축물대장 조회 약 1.5~3분)에서 이탈을 막는 O/X·객관식 퀴즈.
-- 운영자가 관리자 콘솔(service_role, Supabase Data API)로 문항을 수정하므로 하드코딩하지
-- 않고 faqs(0011)와 동일한 컨벤션으로 테이블에 둔다:
--   * 공개 콘텐츠(PII 아님). 읽기는 FastAPI ``GET /quizzes`` 경로만 — anon/authenticated
--     에 grant/policy 미부여(백엔드 풀 role 이 RLS 우회 SELECT).
--   * **객관식 일반형**: ``choices``(선택지 2~5개) + ``answer_index``(0-base 정답 위치).
--     O/X 문항은 ``choices = array['O','X']`` 인 특수 케이스다 — 별도 type 컬럼 없이
--     선택지 배열만으로 운영자가 두 형식을 자유 편집한다(프론트가 배열을 보고 렌더 분기).
--   * ``explanation`` 은 마크다운(정답 공개 후 해설). 렌더링은 프론트 책임.
--   * ``categories`` 는 faqs 와 동일한 영문 슬러그 배열. 한국어 라벨은 프론트 소유.
-- 시드 문항의 사실관계는 faqs 시드(0011, 운영자 검수 QnA 시트)에서만 도출했다.
-- 프론트 폴백(`apps/web/lib/quiz-fallback.ts`)의 id 1..20 은 identity 시드 순서와 일치한다.

create table public.quizzes (
  id bigint generated always as identity,
  categories text[] not null,
  question text not null,
  choices text[] not null,
  answer_index smallint not null,
  explanation text not null,
  sort_order integer not null default 0,
  is_published boolean not null default true,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint pk_quizzes primary key (id),
  -- 허용 슬러그 외 값과 빈 배열을 차단한다(faqs 의 ck 와 동일 논거 — cardinality 사용).
  constraint ck_quizzes_categories_allowed check (
    categories <@ array[
      'cost', 'prereview', 'glossary', 'act_permit',
      'resident_consent', 'fireproofing', 'use_inspection'
    ]::text[]
    and cardinality(categories) >= 1
  ),
  -- 선택지 2~5개(2개=O/X, 3~5개=객관식). 정답 인덱스는 선택지 범위 안(0-base).
  constraint ck_quizzes_choices_range check (
    cardinality(choices) between 2 and 5
  ),
  constraint ck_quizzes_answer_index_valid check (
    answer_index >= 0 and answer_index < cardinality(choices)
  )
);

-- 공개 목록 조회용 부분 인덱스 — 노출 행을 전역 정렬(sort_order) 순으로 읽는 단일 경로.
-- 셔플·카테고리 필터는 프론트가 전체 목록(현재 20건)을 받아 클라이언트에서 처리한다.
create index ix_quizzes_published_sort_order
  on public.quizzes (sort_order)
  where is_published;

comment on table public.quizzes is
  'Public quiz content for the home-check waiting screen (not PII). Read via the '
  'FastAPI GET /quizzes path; no PostgREST/client grants. Generalized multiple-choice: '
  'choices(2..5) + answer_index(0-base); an O/X item is choices=[O,X]. explanation '
  'holds markdown; categories reuse the FAQ English slugs.';

-- RLS: 공개 콘텐츠지만 다른 도메인 테이블과 동일하게 백엔드 경유 읽기만 허용한다.
alter table public.quizzes enable row level security;

-- ---------------------------------------------------------------------------
-- 초기 시드 (20문항 = O/X 15 + 객관식 5) — 사실관계는 faqs 시드(0011) 정본.
-- 위반건축물 '딱지' 색상은 표기하지 않는다(FAQ '빨간딱지' vs ADR-0008 '노란딱지' 상충).
-- ---------------------------------------------------------------------------
insert into public.quizzes (categories, sort_order, question, choices, answer_index, explanation) values
  (array['glossary']::text[], 1,
   $quiz$내력벽은 건물의 하중을 지지하는 벽이라 함부로 철거하면 안 된다.$quiz$,
   array['O', 'X'], 0,
   $quiz$내력벽은 위층·지붕·바닥의 무게를 기초로 전달하는 구조 벽이라 함부로 철거하면 안전에 영향을 줄 수 있습니다. 철거·변경 검토 대상이 되는 쪽은 공간을 나누는 **비내력벽**입니다.$quiz$),
  (array['glossary', 'prereview']::text[], 2,
   $quiz$도면에서 비내력벽으로 보이면 실제로도 항상 안전하게 철거할 수 있다.$quiz$,
   array['O', 'X'], 1,
   $quiz$도면상 비내력벽으로 보여도 실제 시공·현장 조건에 따라 다를 수 있어요. 철거 여부는 도면 확인과 **전문가 검토**를 함께 거치는 것이 안전합니다.$quiz$),
  (array['act_permit']::text[], 3,
   $quiz$공동주택 발코니를 구조적으로 변경하려면 공사 착공 전에 관할 행정청의 허가나 신고가 필요하다.$quiz$,
   array['O', 'X'], 0,
   $quiz$이것이 **행위허가**입니다(2005년 건축법 시행령 개정 이후). 공사를 시작하기 전에 "이 변경이 법령 기준에 맞는지"를 행정청이 확인하는 단계예요.$quiz$),
  (array['act_permit']::text[], 4,
   $quiz$허가 없이 구조를 변경해 위반건축물로 등록되면, 시정할 때까지 이행강제금이 매년 부과될 수 있다.$quiz$,
   array['O', 'X'], 0,
   $quiz$위반건축물로 등록되면 시정 때까지 매년 **이행강제금**이 부과될 수 있고 **원상복구 명령** 대상이 됩니다. 사용검사·건축물대장 등재도 막혀 매매에 걸림돌이 돼요.$quiz$),
  (array['act_permit']::text[], 5,
   $quiz$이전 소유자가 무단 확장한 집을 샀다면, 원상복구·이행강제금 책임이 현재 소유자에게 넘어올 수 있다.$quiz$,
   array['O', 'X'], 0,
   $quiz$무단 확장 책임은 **현재 소유자에게 승계**될 수 있습니다. 다만 구조가 기준에 맞으면 사후 행위허가·사용검사로 **양성화**할 수 있는 경우가 많아요.$quiz$),
  (array['resident_consent']::text[], 6,
   $quiz$발코니 확장 행위허가에는 보통 해당 동 전체 세대의 절반 이상 입주민 동의가 필요하다.$quiz$,
   array['O', 'X'], 0,
   $quiz$공동주택 공사는 이웃 세대의 구조 안전·공용부에 영향을 줄 수 있어, 보통 **해당 동(棟) 전체 세대의 50% 이상** 동의가 필요합니다(정확한 대상·비율은 단지·지자체 기준에 따라 다름).$quiz$),
  (array['resident_consent']::text[], 7,
   $quiz$입주민 동의서는 전화나 문자 메시지로 받아도 된다.$quiz$,
   array['O', 'X'], 1,
   $quiz$동의서는 **법적으로 직접 대면 수령이 원칙**입니다. 그래서 방문해서 서명을 받는 과정이 필요해요.$quiz$),
  (array['fireproofing']::text[], 8,
   $quiz$확장한 발코니에는 바닥판 두께를 포함해 높이 90cm 이상의 방화판 또는 방화유리를 설치해야 한다.$quiz$,
   array['O', 'X'], 0,
   $quiz$확장 발코니는 위층으로 불이 번지기 쉬워 **바닥판 두께 포함 90cm 이상**의 방화판·방화유리 설치가 의무입니다(난간과 샤시 사이 설치).$quiz$),
  (array['fireproofing']::text[], 9,
   $quiz$발코니가 스프링클러 살수 범위 안에 들어가면 방화판·방화유리 설치 의무가 면제될 수 있다.$quiz$,
   array['O', 'X'], 0,
   $quiz$살수 범위 **안**이면 면제될 수 있습니다. 다만 살수 범위 밖을 거실로 사용하면 방화시설은 물론 **자동화재탐지기 설치**도 필요해요(단독주택 제외).$quiz$),
  (array['fireproofing']::text[], 10,
   $quiz$방화판과 방화유리 중 채광과 시야 확보에 유리한 쪽은 방화유리다.$quiz$,
   array['O', 'X'], 0,
   $quiz$**방화유리**는 화재 시 열과 불길을 견디면서 채광·시야를 함께 확보할 수 있고, **방화판**은 불에 타지 않는 막음 판으로 세대 경계에 설치합니다. 채광·비용·시공 조건에 따라 선택이 달라져요.$quiz$),
  (array['use_inspection']::text[], 11,
   $quiz$행위허가를 받아 공사했다면, 사용검사까지 마쳐야 변경 내용이 정식으로 인정된다.$quiz$,
   array['O', 'X'], 0,
   $quiz$사용검사는 시공이 허가 내용대로 적법하게 이뤄졌는지 행정청이 확인하는 절차입니다. 이 확인을 마쳐야 변경된 상태가 정식으로 인정되고 **건축물대장에 등재**돼요.$quiz$),
  (array['use_inspection']::text[], 12,
   $quiz$사용검사를 받지 않아도 나중에 집을 팔거나 담보대출을 받는 데는 영향이 없다.$quiz$,
   array['O', 'X'], 1,
   $quiz$사용검사를 안 받으면 공사 내용이 건축물대장·건축물현황도에 **등재되지 않습니다**. 법적으로 공사가 완료되지 않은 상태라 **매매·담보대출·추가 공사** 때 문제가 될 수 있어요.$quiz$),
  (array['act_permit']::text[], 13,
   $quiz$구조 변경이 없는 단순 새시(샤시) 교체는 일반적으로 행위허가 대상이 아니다.$quiz$,
   array['O', 'X'], 0,
   $quiz$단순 새시 교체처럼 **구조 변경이 없는 공사**는 일반적으로 행위허가 대상이 아닙니다. 다만 확장과 함께 외벽·난간을 변경하면 허가·신고가 필요할 수 있어요.$quiz$),
  (array['glossary']::text[], 14,
   $quiz$아파트에서 흔히 '베란다 확장'이라 부르지만, 실제로 확장하는 공간은 대부분 발코니다.$quiz$,
   array['O', 'X'], 0,
   $quiz$**발코니**는 건물 외벽에서 돌출된 공간, **베란다**는 위·아래층 면적 차이로 생긴 공간, **테라스**는 지면과 맞닿은 외부 공간입니다. 아파트 확장 대상은 대부분 발코니예요.$quiz$),
  (array['use_inspection', 'act_permit']::text[], 15,
   $quiz$예전에 확장하면서 사용검사를 받지 않았다면, 지금은 건축물대장에 등재할 방법이 없다.$quiz$,
   array['O', 'X'], 1,
   $quiz$지금이라도 **사용검사를 받아 건축물대장에 등재(양성화)할 수 있는** 경우가 많습니다. 현재 상태가 방화·구조 기준에 맞는지 점검이 선행돼요.$quiz$),
  (array['fireproofing']::text[], 16,
   $quiz$확장 발코니에 설치하는 방화판·방화유리의 최소 높이는? (바닥판 두께 포함)$quiz$,
   array['60cm 이상', '90cm 이상', '120cm 이상'], 1,
   $quiz$기준은 **바닥판 두께 포함 90cm 이상**이고, 난간과 샤시 사이에 설치합니다. 2층 이상 세대 중 스프링클러 살수 범위에 포함되지 않는 확장 발코니가 대상이에요.$quiz$),
  (array['resident_consent']::text[], 17,
   $quiz$발코니 확장 행위허가에 보통 필요한 입주민 동의 기준은?$quiz$,
   array['해당 동 전체 세대의 1/3 이상', '해당 동 전체 세대의 1/2 이상', '해당 동 전체 세대의 2/3 이상'], 1,
   $quiz$보통 **해당 동 전체 세대의 절반(50%) 이상** 동의가 필요합니다. 정확한 대상·비율은 단지·지자체 기준에 따라 다르며, 직상·직하·좌우 인접 세대가 포함되는 경우가 많아요.$quiz$),
  (array['glossary']::text[], 18,
   $quiz$아파트에서 확장 공사를 하는 공간의 정확한 명칭은?$quiz$,
   array['발코니', '베란다', '테라스'], 0,
   $quiz$흔히 '베란다 확장'이라 부르지만, 아파트에서 확장하는 곳은 대부분 **발코니**(건물 외벽에서 돌출된 공간)입니다. 베란다는 위·아래층 면적 차이로 생긴 공간, 테라스는 지면과 맞닿은 외부 공간이에요.$quiz$),
  (array['act_permit']::text[], 19,
   $quiz$허가 없이 구조를 변경해 위반건축물로 등록되면, 시정할 때까지 매년 부과될 수 있는 것은?$quiz$,
   array['과태료', '이행강제금', '취득세'], 1,
   $quiz$위반건축물은 시정 때까지 매년 **이행강제금**이 부과될 수 있고 **원상복구 명령** 대상이 됩니다.$quiz$),
  (array['use_inspection']::text[], 20,
   $quiz$공사 완료 후 변경 내용을 건축물대장에 등재하기 위해 거치는 절차는?$quiz$,
   array['사용검사', '준공식', '소유권 이전 등기'], 0,
   $quiz$**사용검사**는 시공이 허가 내용대로 이뤄졌는지 행정청이 확인하는 절차로, 이를 통과해야 변경 내용이 건축물대장에 등재됩니다.$quiz$);

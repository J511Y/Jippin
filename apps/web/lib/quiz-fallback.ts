/**
 * 대기 화면 퀴즈 정적 폴백 — SQL 시드(``..._0023_quizzes.sql``, identity 1..20)와
 * 내용·id 를 동일하게 유지한다(faq-fallback 관례). API 장애/빌드 시에도 대기 화면
 * 콘텐츠가 비지 않게 하는 최후 방어선이다. 사실관계는 faqs 시드(0011) 정본에서만
 * 도출했다 — 문항 수정은 마이그레이션 시드(운영 DB)와 함께 맞춘다.
 */

import type { QuizItem } from '@/lib/quiz';

export const QUIZ_FALLBACK: QuizItem[] = [
  {
    id: 1,
    categories: ['glossary'],
    sort_order: 1,
    question: '내력벽은 건물의 하중을 지지하는 벽이라 함부로 철거하면 안 된다.',
    choices: ['O', 'X'],
    answer_index: 0,
    explanation:
      '내력벽은 위층·지붕·바닥의 무게를 기초로 전달하는 구조 벽이라 함부로 철거하면 안전에 영향을 줄 수 있습니다. 철거·변경 검토 대상이 되는 쪽은 공간을 나누는 **비내력벽**입니다.'
  },
  {
    id: 2,
    categories: ['glossary', 'prereview'],
    sort_order: 2,
    question: '도면에서 비내력벽으로 보이면 실제로도 항상 안전하게 철거할 수 있다.',
    choices: ['O', 'X'],
    answer_index: 1,
    explanation:
      '도면상 비내력벽으로 보여도 실제 시공·현장 조건에 따라 다를 수 있어요. 철거 여부는 도면 확인과 **전문가 검토**를 함께 거치는 것이 안전합니다.'
  },
  {
    id: 3,
    categories: ['act_permit'],
    sort_order: 3,
    question:
      '공동주택 발코니를 구조적으로 변경하려면 공사 착공 전에 관할 행정청의 허가나 신고가 필요하다.',
    choices: ['O', 'X'],
    answer_index: 0,
    explanation:
      '이것이 **행위허가**입니다(2005년 건축법 시행령 개정 이후). 공사를 시작하기 전에 "이 변경이 법령 기준에 맞는지"를 행정청이 확인하는 단계예요.'
  },
  {
    id: 4,
    categories: ['act_permit'],
    sort_order: 4,
    question:
      '허가 없이 구조를 변경해 위반건축물로 등록되면, 시정할 때까지 이행강제금이 매년 부과될 수 있다.',
    choices: ['O', 'X'],
    answer_index: 0,
    explanation:
      '위반건축물로 등록되면 시정 때까지 매년 **이행강제금**이 부과될 수 있고 **원상복구 명령** 대상이 됩니다. 사용검사·건축물대장 등재도 막혀 매매에 걸림돌이 돼요.'
  },
  {
    id: 5,
    categories: ['act_permit'],
    sort_order: 5,
    question:
      '이전 소유자가 무단 확장한 집을 샀다면, 원상복구·이행강제금 책임이 현재 소유자에게 넘어올 수 있다.',
    choices: ['O', 'X'],
    answer_index: 0,
    explanation:
      '무단 확장 책임은 **현재 소유자에게 승계**될 수 있습니다. 다만 구조가 기준에 맞으면 사후 행위허가·사용검사로 **양성화**할 수 있는 경우가 많아요.'
  },
  {
    id: 6,
    categories: ['resident_consent'],
    sort_order: 6,
    question:
      '발코니 확장 행위허가에는 보통 해당 동 전체 세대의 절반 이상 입주민 동의가 필요하다.',
    choices: ['O', 'X'],
    answer_index: 0,
    explanation:
      '공동주택 공사는 이웃 세대의 구조 안전·공용부에 영향을 줄 수 있어, 보통 **해당 동(棟) 전체 세대의 50% 이상** 동의가 필요합니다(정확한 대상·비율은 단지·지자체 기준에 따라 다름).'
  },
  {
    id: 7,
    categories: ['resident_consent'],
    sort_order: 7,
    question: '입주민 동의서는 전화나 문자 메시지로 받아도 된다.',
    choices: ['O', 'X'],
    answer_index: 1,
    explanation:
      '동의서는 **법적으로 직접 대면 수령이 원칙**입니다. 그래서 방문해서 서명을 받는 과정이 필요해요.'
  },
  {
    id: 8,
    categories: ['fireproofing'],
    sort_order: 8,
    question:
      '확장한 발코니에는 바닥판 두께를 포함해 높이 90cm 이상의 방화판 또는 방화유리를 설치해야 한다.',
    choices: ['O', 'X'],
    answer_index: 0,
    explanation:
      '확장 발코니는 위층으로 불이 번지기 쉬워 **바닥판 두께 포함 90cm 이상**의 방화판·방화유리 설치가 의무입니다(난간과 샤시 사이 설치).'
  },
  {
    id: 9,
    categories: ['fireproofing'],
    sort_order: 9,
    question:
      '발코니가 스프링클러 살수 범위 안에 들어가면 방화판·방화유리 설치 의무가 면제될 수 있다.',
    choices: ['O', 'X'],
    answer_index: 0,
    explanation:
      '살수 범위 **안**이면 면제될 수 있습니다. 다만 살수 범위 밖을 거실로 사용하면 방화시설은 물론 **자동화재탐지기 설치**도 필요해요(단독주택 제외).'
  },
  {
    id: 10,
    categories: ['fireproofing'],
    sort_order: 10,
    question: '방화판과 방화유리 중 채광과 시야 확보에 유리한 쪽은 방화유리다.',
    choices: ['O', 'X'],
    answer_index: 0,
    explanation:
      '**방화유리**는 화재 시 열과 불길을 견디면서 채광·시야를 함께 확보할 수 있고, **방화판**은 불에 타지 않는 막음 판으로 세대 경계에 설치합니다. 채광·비용·시공 조건에 따라 선택이 달라져요.'
  },
  {
    id: 11,
    categories: ['use_inspection'],
    sort_order: 11,
    question:
      '행위허가를 받아 공사했다면, 사용검사까지 마쳐야 변경 내용이 정식으로 인정된다.',
    choices: ['O', 'X'],
    answer_index: 0,
    explanation:
      '사용검사는 시공이 허가 내용대로 적법하게 이뤄졌는지 행정청이 확인하는 절차입니다. 이 확인을 마쳐야 변경된 상태가 정식으로 인정되고 **건축물대장에 등재**돼요.'
  },
  {
    id: 12,
    categories: ['use_inspection'],
    sort_order: 12,
    question:
      '사용검사를 받지 않아도 나중에 집을 팔거나 담보대출을 받는 데는 영향이 없다.',
    choices: ['O', 'X'],
    answer_index: 1,
    explanation:
      '사용검사를 안 받으면 공사 내용이 건축물대장·건축물현황도에 **등재되지 않습니다**. 법적으로 공사가 완료되지 않은 상태라 **매매·담보대출·추가 공사** 때 문제가 될 수 있어요.'
  },
  {
    id: 13,
    categories: ['act_permit'],
    sort_order: 13,
    question: '구조 변경이 없는 단순 새시(샤시) 교체는 일반적으로 행위허가 대상이 아니다.',
    choices: ['O', 'X'],
    answer_index: 0,
    explanation:
      '단순 새시 교체처럼 **구조 변경이 없는 공사**는 일반적으로 행위허가 대상이 아닙니다. 다만 확장과 함께 외벽·난간을 변경하면 허가·신고가 필요할 수 있어요.'
  },
  {
    id: 14,
    categories: ['glossary'],
    sort_order: 14,
    question:
      "아파트에서 흔히 '베란다 확장'이라 부르지만, 실제로 확장하는 공간은 대부분 발코니다.",
    choices: ['O', 'X'],
    answer_index: 0,
    explanation:
      '**발코니**는 건물 외벽에서 돌출된 공간, **베란다**는 위·아래층 면적 차이로 생긴 공간, **테라스**는 지면과 맞닿은 외부 공간입니다. 아파트 확장 대상은 대부분 발코니예요.'
  },
  {
    id: 15,
    categories: ['use_inspection', 'act_permit'],
    sort_order: 15,
    question:
      '예전에 확장하면서 사용검사를 받지 않았다면, 지금은 건축물대장에 등재할 방법이 없다.',
    choices: ['O', 'X'],
    answer_index: 1,
    explanation:
      '지금이라도 **사용검사를 받아 건축물대장에 등재(양성화)할 수 있는** 경우가 많습니다. 현재 상태가 방화·구조 기준에 맞는지 점검이 선행돼요.'
  },
  {
    id: 16,
    categories: ['fireproofing'],
    sort_order: 16,
    question: '확장 발코니에 설치하는 방화판·방화유리의 최소 높이는? (바닥판 두께 포함)',
    choices: ['60cm 이상', '90cm 이상', '120cm 이상'],
    answer_index: 1,
    explanation:
      '기준은 **바닥판 두께 포함 90cm 이상**이고, 난간과 샤시 사이에 설치합니다. 2층 이상 세대 중 스프링클러 살수 범위에 포함되지 않는 확장 발코니가 대상이에요.'
  },
  {
    id: 17,
    categories: ['resident_consent'],
    sort_order: 17,
    question: '발코니 확장 행위허가에 보통 필요한 입주민 동의 기준은?',
    choices: [
      '해당 동 전체 세대의 1/3 이상',
      '해당 동 전체 세대의 1/2 이상',
      '해당 동 전체 세대의 2/3 이상'
    ],
    answer_index: 1,
    explanation:
      '보통 **해당 동 전체 세대의 절반(50%) 이상** 동의가 필요합니다. 정확한 대상·비율은 단지·지자체 기준에 따라 다르며, 직상·직하·좌우 인접 세대가 포함되는 경우가 많아요.'
  },
  {
    id: 18,
    categories: ['glossary'],
    sort_order: 18,
    question: '아파트에서 확장 공사를 하는 공간의 정확한 명칭은?',
    choices: ['발코니', '베란다', '테라스'],
    answer_index: 0,
    explanation:
      "흔히 '베란다 확장'이라 부르지만, 아파트에서 확장하는 곳은 대부분 **발코니**(건물 외벽에서 돌출된 공간)입니다. 베란다는 위·아래층 면적 차이로 생긴 공간, 테라스는 지면과 맞닿은 외부 공간이에요."
  },
  {
    id: 19,
    categories: ['act_permit'],
    sort_order: 19,
    question:
      '허가 없이 구조를 변경해 위반건축물로 등록되면, 시정할 때까지 매년 부과될 수 있는 것은?',
    choices: ['과태료', '이행강제금', '취득세'],
    answer_index: 1,
    explanation:
      '위반건축물은 시정 때까지 매년 **이행강제금**이 부과될 수 있고 **원상복구 명령** 대상이 됩니다.'
  },
  {
    id: 20,
    categories: ['use_inspection'],
    sort_order: 20,
    question: '공사 완료 후 변경 내용을 건축물대장에 등재하기 위해 거치는 절차는?',
    choices: ['사용검사', '준공식', '소유권 이전 등기'],
    answer_index: 0,
    explanation:
      '**사용검사**는 시공이 허가 내용대로 이뤄졌는지 행정청이 확인하는 절차로, 이를 통과해야 변경 내용이 건축물대장에 등재됩니다.'
  }
];

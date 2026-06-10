/**
 * 자주묻는질문(FAQ) — 프론트 계약 + 카테고리 메타 + 정적 폴백 (CMP-DIRECT).
 *
 * DB 정본은 ``faqs`` 테이블이고, 읽기는 백엔드 ``GET /faqs`` 를 통한다(Phase 2).
 * 본 모듈은:
 *   1. 카테고리 슬러그 ↔ 한국어 라벨/노출 순서를 소유한다(콘텐츠를 코드에 묶지 않기 위해
 *      API 는 영문 슬러그만 반환하고, 라벨/정렬은 여기서 매핑한다).
 *   2. API 가 닿지 않을 때(빌드/장애/마이그레이션 미적용) 쓰는 정적 폴백을 보유한다.
 *      폴백 내용은 SQL 시드(``..._0010_faqs.sql``)와 동일하게 유지한다.
 *
 * ``answer`` 는 마크다운 텍스트다(링크·이미지·목록 등). 렌더링은 ``/faq`` 페이지가
 * react-markdown 으로 처리한다.
 */

import { serverApiBaseUrl } from '@/lib/api-base-url';

export type FaqCategory =
  | 'cost'
  | 'prereview'
  | 'glossary'
  | 'act_permit'
  | 'resident_consent'
  | 'fireproofing'
  | 'use_inspection';

export type FaqItem = {
  id: string;
  category: FaqCategory;
  question: string;
  /** 마크다운 텍스트. */
  answer: string;
  sort_order: number;
};

export type FaqGroup = {
  category: FaqCategory;
  label: string;
  items: FaqItem[];
};

/** 노출 순서 — 운영자 요청 카테고리 순. */
export const FAQ_CATEGORY_ORDER: FaqCategory[] = [
  'cost',
  'prereview',
  'glossary',
  'act_permit',
  'resident_consent',
  'fireproofing',
  'use_inspection'
];

/** 카테고리 슬러그 → 한국어 라벨. */
export const FAQ_CATEGORY_LABELS: Record<FaqCategory, string> = {
  cost: '비용',
  prereview: '사전검토',
  glossary: '용어',
  act_permit: '행위허가',
  resident_consent: '입주민 동의',
  fireproofing: '방화 · 시공',
  use_inspection: '사용검사'
};

/**
 * 정적 폴백 — SQL 시드와 동일 내용. API 가 닿지 않을 때만 사용한다.
 * id 는 폴백 전용 합성값(`${category}-${sort_order}`)이며 DB row id 와 무관하다.
 */
const FAQ_FALLBACK_SOURCE: Omit<FaqItem, 'id'>[] = [
  {
    category: 'cost',
    sort_order: 1,
    question: '사전검토 비용은 얼마인가요?',
    answer:
      '**AI 사전검토는 무료**입니다. 평면도 한 장과 주소만 입력하면 비용 없이 철거·확장 가능성과 행위허가 필요 여부를 확인할 수 있어요. [무료로 사전검토 시작하기](/sessions/new)'
  },
  {
    category: 'cost',
    sort_order: 2,
    question: '전문가 상담·대행·시공 비용은 어떻게 책정되나요?',
    answer:
      '상담·동의서/행위허가 대행·시공 비용은 **현장 조건(면적·구조·세대 수 등)에 따라 달라져** 사전 진단 후 견적으로 안내합니다. 자세한 항목은 [가격 안내](/prices)를 참고해 주세요.'
  },
  {
    category: 'cost',
    sort_order: 3,
    question: '견적을 받으면 꼭 진행해야 하나요?',
    answer:
      '아니요. 사전검토와 견적 확인까지는 **부담 없이 무료**이며, 진행 여부는 견적과 상담 내용을 확인한 뒤 결정하시면 됩니다.'
  },
  {
    category: 'prereview',
    sort_order: 1,
    question: '사전검토는 시간이 얼마나 걸리나요?',
    answer:
      '평면도 한 장과 주소만 입력하면 **로그인 없이 약 1분**이면 됩니다. 철거·확장 가능성, 주의 구간, 행위허가 필요 여부를 신호등 리포트로 바로 확인할 수 있어요.'
  },
  {
    category: 'prereview',
    sort_order: 2,
    question: '사전검토에 무엇을 준비해야 하나요?',
    answer:
      '**평면도 이미지 한 장과 주소**면 충분합니다. 평면도는 분양 카탈로그, 건축물현황도, 관리사무소 도면 등 어떤 형태든 좋고, 사진이나 캡처 이미지도 AI 가 벽체·개구부·치수를 인식합니다.'
  },
  {
    category: 'prereview',
    sort_order: 3,
    question: '사전검토 결과는 법적 효력이 있나요?',
    answer:
      'AI 사전검토는 **가능성을 빠르게 진단하는 참고 자료**입니다. 최종 가부는 전문가 검토와 구조안전확인, 관할 지자체의 행위허가로 확정되며, 집핀이 그 절차까지 연결해 드립니다.'
  },
  {
    category: 'glossary',
    sort_order: 1,
    question: '내력벽과 비내력벽은 어떻게 다른가요?',
    answer:
      '- **내력벽**: 건물의 하중(무게)을 지지하는 벽으로, 원칙적으로 철거할 수 없습니다.\n- **비내력벽(가벽)**: 하중을 받지 않는 칸막이 벽으로, 일반적으로 철거·이동이 가능합니다.\n\n집핀 AI 는 평면도에서 두 벽을 자동으로 판별해 위험 구간을 진단합니다.'
  },
  {
    category: 'glossary',
    sort_order: 2,
    question: '행위허가가 무엇인가요?',
    answer:
      '**행위허가**는 발코니 확장처럼 건축물의 구조·용도에 영향을 주는 공사를 하기 전에 관할 지자체(구청 등)로부터 받아야 하는 허가(또는 신고)입니다. 보통 입주민 동의서, 검인 도면, 구조안전확인서 등이 필요합니다.'
  },
  {
    category: 'glossary',
    sort_order: 3,
    question: '건축물대장 등재는 무엇인가요?',
    answer:
      '공사 완료 후 **사용검사**를 거쳐 변경된 내용을 **건축물대장**에 정식으로 기록하는 절차입니다. 이 절차까지 마쳐야 법적으로 공사가 완료된 것으로 인정됩니다.'
  },
  {
    category: 'act_permit',
    sort_order: 1,
    question: '베란다(발코니) 확장에 행위허가가 꼭 필요한가요?',
    answer:
      '발코니 확장 자체는 건축법상 허용되지만, **대부분 관할 지자체의 행위허가(또는 신고)와 입주민 동의가 필요**합니다. 집핀이 필요 여부를 사전검토하고, 서류 준비부터 접수까지 대행합니다.'
  },
  {
    category: 'act_permit',
    sort_order: 2,
    question: '행위허가는 얼마나 걸리나요?',
    answer:
      '동의서·검인 도면·구조안전확인서·철거 사유서 준비부터 지자체 접수까지 **약 7일** 정도 소요됩니다. (현장·지자체 상황에 따라 달라질 수 있습니다.)'
  },
  {
    category: 'act_permit',
    sort_order: 3,
    question: '행위허가 없이 공사하면 어떻게 되나요?',
    answer:
      '허가 없이 구조를 변경하면 **위반건축물로 분류**되어 이행강제금 부과, 원상복구 명령 등의 불이익을 받을 수 있습니다. 반드시 사전검토와 허가 절차를 거치는 것을 권장합니다.'
  },
  {
    category: 'resident_consent',
    sort_order: 1,
    question: '입주민 동의서는 꼭 받아야 하나요?',
    answer:
      '네. 발코니 확장 등 행위허가가 필요한 공사는 단지·지자체 기준에 따라 **인접 세대의 동의서가 필수**인 경우가 많습니다. 집핀이 방문부터 서명 수령까지 대행합니다.'
  },
  {
    category: 'resident_consent',
    sort_order: 2,
    question: '몇 세대의 동의가 필요한가요?',
    answer:
      '동의 대상은 단지와 지자체 기준에 따라 다르며, 보통 **직상·직하·좌우 인접 세대** 등이 포함됩니다. 정확한 대상은 사전검토와 상담에서 안내해 드립니다.'
  },
  {
    category: 'resident_consent',
    sort_order: 3,
    question: '동의를 안 해주는 세대가 있으면 어떻게 되나요?',
    answer:
      '담당자가 평일 저녁·주말에 직접 방문하고 부재 세대도 끝까지 재방문해 동의를 받습니다. 다만 끝내 동의가 어려운 경우의 한계도 상담 단계에서 미리 안내해 드립니다.'
  },
  {
    category: 'fireproofing',
    sort_order: 1,
    question: '발코니 확장 시 방화판·방화유리가 꼭 필요한가요?',
    answer:
      '네. 발코니를 확장하면 인접 세대로의 화재 확산을 막기 위해 **90cm 이상의 방화판 또는 방화유리 설치가 의무**입니다. 집핀은 건축법 및 **KS F 2845** 기준에 맞춰 시공합니다.'
  },
  {
    category: 'fireproofing',
    sort_order: 2,
    question: '확장하면 결로나 단열 문제가 생기지 않나요?',
    answer:
      '확장부는 단열·새시 시공 기준에 맞춰 진행해 결로 위험을 관리합니다. 세대별 상황에 따라 필요한 보강 범위를 상담에서 안내해 드립니다.'
  },
  {
    category: 'fireproofing',
    sort_order: 3,
    question: '사전검토나 허가만 따로 받을 수도 있나요?',
    answer:
      '네. 사전검토 / 전문가 상담 / 행위허가 대행 / 시공을 **필요한 단계만 골라** 진행할 수 있습니다.'
  },
  {
    category: 'use_inspection',
    sort_order: 1,
    question: '사용검사는 왜 받아야 하나요?',
    answer:
      '사용검사는 공사가 법 기준에 맞게 완료됐는지 확인받는 절차입니다. 이 검사를 통과하고 **건축물대장에 등재**해야 비로소 법적으로 공사가 완료됩니다.'
  },
  {
    category: 'use_inspection',
    sort_order: 2,
    question: '사용검사·건축물대장 등재까지 집핀이 해주나요?',
    answer:
      '네. 집핀은 사전검토부터 행위허가, 방화판·방화유리 시공, **사용검사 신청과 건축물대장 등재까지 전 과정**을 대행합니다. 2007년부터 행위허가만 누적 2만5천여 건을 처리했습니다.'
  }
];

export const FAQ_FALLBACK: FaqItem[] = FAQ_FALLBACK_SOURCE.map((row) => ({
  id: `${row.category}-${row.sort_order}`,
  ...row
}));

/** API 응답을 알려진 카테고리 슬러그로만 좁힌다(미지의 슬러그는 버린다). */
function isKnownCategory(value: string): value is FaqCategory {
  return value in FAQ_CATEGORY_LABELS;
}

/**
 * 백엔드 ``GET /faqs`` 에서 공개 FAQ 를 가져온다(서버 컴포넌트 전용).
 * 실패·미적용 시 정적 폴백을 반환해 페이지가 비지 않도록 한다.
 */
export async function fetchFaqs(): Promise<FaqItem[]> {
  try {
    const response = await fetch(`${serverApiBaseUrl()}/faqs`, {
      headers: { Accept: 'application/json' },
      // FAQ 는 자주 바뀌지 않으므로 ISR 로 캐시한다(운영자 수정 반영까지 최대 5분).
      next: { revalidate: 300 }
    });
    if (!response.ok) return FAQ_FALLBACK;
    const body = (await response.json()) as { items?: unknown };
    const items = Array.isArray(body.items) ? body.items : [];
    const parsed = items
      .filter(
        (it): it is FaqItem =>
          typeof it === 'object' &&
          it !== null &&
          typeof (it as FaqItem).category === 'string' &&
          isKnownCategory((it as FaqItem).category)
      )
      .map((it) => it);
    return parsed.length > 0 ? parsed : FAQ_FALLBACK;
  } catch {
    return FAQ_FALLBACK;
  }
}

/** 카테고리 순서대로 그룹핑한다(빈 카테고리는 생략). 각 그룹은 sort_order 오름차순. */
export function groupFaqs(items: FaqItem[]): FaqGroup[] {
  return FAQ_CATEGORY_ORDER.map((category) => ({
    category,
    label: FAQ_CATEGORY_LABELS[category],
    items: items
      .filter((it) => it.category === category)
      .sort((a, b) => a.sort_order - b.sort_order)
  })).filter((group) => group.items.length > 0);
}

/** schema.org FAQPage 의 plain-text answer 를 위해 가벼운 마크다운 제거. */
export function stripMarkdown(markdown: string): string {
  return markdown
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '') // 이미지
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1') // 링크 → 텍스트
    .replace(/[*_`>#-]/g, '') // 강조/헤더/인용/리스트 마커
    .replace(/\s+/g, ' ')
    .trim();
}

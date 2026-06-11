/**
 * 자주묻는질문(FAQ) — 프론트 계약 + 카테고리 메타 + 조회 (CMP-DIRECT).
 *
 * DB 정본은 ``faqs`` 테이블이고, 읽기는 백엔드 ``GET /faqs``(목록)·
 * ``GET /faqs/{faqId}``(상세)를 통한다. 본 모듈은:
 *   1. 카테고리 슬러그 ↔ 한국어 라벨/노출 순서를 소유한다(콘텐츠를 코드에 묶지
 *      않기 위해 API 는 영문 슬러그만 반환하고, 라벨/정렬은 여기서 매핑한다).
 *      한 질문이 여러 카테고리에 속할 수 있다(`categories` 배열).
 *   2. API 가 닿지 않을 때(빌드/장애/마이그레이션 미적용) 쓰는 정적 폴백을
 *      ``./faq-fallback`` 에서 가져와 노출한다. 폴백 내용·id 는 SQL 시드
 *      (``..._0011_faqs_v2.sql``, identity 1..44)와 동일하게 유지한다.
 *
 * ``answer`` 는 마크다운 텍스트다(표·링크·인라인 HTML 일부). 렌더링은 ``/faq``·
 * ``/faq/[faqId]`` 페이지가 react-markdown 으로 처리한다.
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
  /** identity 정수 — 상세 URL(`/faq/{faqId}`)에 쓴다. */
  id: number;
  /** 한 질문이 여러 카테고리에 속할 수 있다(최소 1개). */
  categories: FaqCategory[];
  question: string;
  /** 마크다운 텍스트. */
  answer: string;
  sort_order: number;
};

/** 노출 순서 — 운영자 요청 카테고리 순(필터 칩 순서로도 쓴다). */
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

/** 알려진 카테고리 슬러그로만 좁힌다(미지의 슬러그는 버린다). */
function isKnownCategory(value: unknown): value is FaqCategory {
  return typeof value === 'string' && value in FAQ_CATEGORY_LABELS;
}

/** API 응답 한 건을 검증·정규화한다. 형태가 어긋나면 ``null``. */
function parseFaqItem(it: unknown): FaqItem | null {
  if (typeof it !== 'object' || it === null) return null;
  const row = it as Record<string, unknown>;
  if (
    typeof row.id !== 'number' ||
    typeof row.question !== 'string' ||
    typeof row.answer !== 'string' ||
    !Array.isArray(row.categories)
  ) {
    return null;
  }
  const categories = row.categories.filter(isKnownCategory);
  if (categories.length === 0) return null;
  return {
    id: row.id,
    categories,
    question: row.question,
    answer: row.answer,
    sort_order: typeof row.sort_order === 'number' ? row.sort_order : 0
  };
}

/**
 * 백엔드 ``GET /faqs`` 에서 공개 FAQ 목록을 가져온다(서버 컴포넌트 전용).
 * 실패·미적용 시 정적 폴백을 반환해 페이지가 비지 않도록 한다.
 */
export async function fetchFaqs(): Promise<FaqItem[]> {
  // 순환 import 방지를 위해 정적 폴백은 지연 로드한다(타입은 본 모듈이 소유).
  const { FAQ_FALLBACK } = await import('@/lib/faq-fallback');
  try {
    const response = await fetch(`${serverApiBaseUrl()}/faqs`, {
      headers: { Accept: 'application/json' },
      // FAQ 는 자주 바뀌지 않으므로 ISR 로 캐시한다(운영자 수정 반영까지 최대 5분).
      next: { revalidate: 300 }
    });
    if (!response.ok) return FAQ_FALLBACK;
    const body = (await response.json()) as { items?: unknown };
    if (!Array.isArray(body.items)) return FAQ_FALLBACK;
    // 정상 응답의 빈 목록은 의도된 상태(전체 비공개 등)로 존중한다 — 폴백은
    // 네트워크 장애·계약 불일치(구버전 페이로드 등)에만 쓴다.
    if (body.items.length === 0) return [];
    const parsed = body.items
      .map(parseFaqItem)
      .filter((it): it is FaqItem => it !== null);
    return parsed.length > 0 ? parsed : FAQ_FALLBACK;
  } catch {
    return FAQ_FALLBACK;
  }
}

/**
 * 백엔드 ``GET /faqs/{faqId}`` 에서 FAQ 한 건을 가져온다(상세 페이지 전용).
 *
 * - 부재·비공개 404(백엔드가 ``detail: "FAQ not found"`` 로 응답)는 ``null`` 을
 *   반환해 페이지가 ``notFound()`` 처리한다.
 * - 상세 라우트가 아직 없는 구버전 API(스태거드 배포)의 404 나 네트워크 장애 등
 *   그 밖의 실패는 폴백 목록에서 같은 id 를 찾아 반환한다(시드와 id 가 일치하므로
 *   목록 폴백에서 이어지는 상세 링크가 깨지지 않는다).
 */
export async function fetchFaqById(faqId: number): Promise<FaqItem | null> {
  const { FAQ_FALLBACK } = await import('@/lib/faq-fallback');
  const fallback = FAQ_FALLBACK.find((it) => it.id === faqId) ?? null;
  try {
    const response = await fetch(`${serverApiBaseUrl()}/faqs/${faqId}`, {
      headers: { Accept: 'application/json' },
      next: { revalidate: 300 }
    });
    if (response.status === 404) {
      // 백엔드 라우터(`apps/api/src/routers/faq.py`)의 부재 404 만 신뢰한다.
      // 전역 핸들러(`apps/api/src/errors.py`)가 HTTPException 을
      // `{ error: { message } }` 봉투로 감싸므로 그 메시지로 판별하고,
      // 라우트 자체가 없는 구버전 API 의 404(message "Not Found")는 폴백으로 둔다.
      const body = (await response.json().catch(() => null)) as {
        error?: { message?: unknown };
        detail?: unknown;
      } | null;
      const message = body?.error?.message ?? body?.detail;
      return message === 'FAQ not found' ? null : fallback;
    }
    if (!response.ok) return fallback;
    return parseFaqItem(await response.json()) ?? fallback;
  } catch {
    return fallback;
  }
}

/** schema.org FAQPage 의 plain-text answer 를 위해 가벼운 마크다운 제거. */
export function stripMarkdown(markdown: string): string {
  return markdown
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '') // 이미지
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1') // 링크 → 텍스트
    .replace(/<[^>]+>/g, ' ') // 인라인 HTML 태그
    .replace(/[*_`>#|-]/g, '') // 강조/헤더/인용/리스트/표 마커
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * 대기 화면 퀴즈 — 프론트 계약 + 조회 (우리집 체크).
 *
 * DB 정본은 ``quizzes`` 테이블이고, 읽기는 백엔드 ``GET /quizzes`` 를 통한다.
 * **객관식 일반형**: ``choices``(선택지 2~5개) + ``answer_index``(0-base 정답).
 * O/X 문항은 ``choices=['O','X']`` 인 특수 케이스다 — 렌더 분기는 컴포넌트가
 * 배열을 보고 결정한다(``isOxQuiz``).
 *
 * API 가 닿지 않을 때(빌드/장애/마이그레이션 미적용) 쓰는 정적 폴백은
 * ``./quiz-fallback`` 에 있다. 폴백 내용·id 는 SQL 시드(``..._0023_quizzes.sql``,
 * identity 1..20)와 동일하게 유지한다(faq 관례).
 *
 * ``explanation`` 은 마크다운 텍스트다. 렌더링은 대기 화면 컴포넌트가 처리한다.
 */

import { serverApiBaseUrl } from '@/lib/api-base-url';
import type { FaqCategory } from '@/lib/faq';
import { FAQ_CATEGORY_LABELS } from '@/lib/faq';

/** 퀴즈 카테고리 = FAQ 슬러그 재사용(콘텐츠 도메인 동일 — 리모델링/건축 규정). */
export type QuizCategory = FaqCategory;

export type QuizItem = {
  /** identity 정수 — 시드/폴백 id 일치 규약. */
  id: number;
  categories: QuizCategory[];
  question: string;
  /** 선택지 2~5개. ['O','X'] 는 O/X 문항. */
  choices: string[];
  /** 0-base 정답 인덱스 (choices 범위 안 — DB CHECK + parseQuizItem 이 보장). */
  answer_index: number;
  /** 마크다운 해설(정답 공개 후 표시). */
  explanation: string;
  sort_order: number;
};

/** O/X 문항 판별 — 선택지 배열이 정확히 ['O','X'] 일 때만. */
export function isOxQuiz(item: Pick<QuizItem, 'choices'>): boolean {
  return item.choices.length === 2 && item.choices[0] === 'O' && item.choices[1] === 'X';
}

/** 알려진 카테고리 슬러그로만 좁힌다(미지의 슬러그는 버린다). */
function isKnownCategory(value: unknown): value is QuizCategory {
  return typeof value === 'string' && value in FAQ_CATEGORY_LABELS;
}

/** API 응답 한 건을 검증·정규화한다. 형태가 어긋나면 ``null``. */
export function parseQuizItem(it: unknown): QuizItem | null {
  if (typeof it !== 'object' || it === null) return null;
  const row = it as Record<string, unknown>;
  if (
    typeof row.id !== 'number' ||
    typeof row.question !== 'string' ||
    typeof row.explanation !== 'string' ||
    typeof row.answer_index !== 'number' ||
    !Array.isArray(row.choices) ||
    !Array.isArray(row.categories)
  ) {
    return null;
  }
  const choices = row.choices.filter((c): c is string => typeof c === 'string');
  // 선택지 2~5개 + 정답 인덱스 범위 검증 — 어긋난 문항은 조용히 버린다
  // (깨진 한 문항이 대기 화면 전체를 폴백으로 밀어내지 않게 항목 단위로 거른다).
  if (choices.length < 2 || choices.length > 5) return null;
  if (!Number.isInteger(row.answer_index) || row.answer_index < 0 || row.answer_index >= choices.length) {
    return null;
  }
  const categories = row.categories.filter(isKnownCategory);
  if (categories.length === 0) return null;
  return {
    id: row.id,
    categories,
    question: row.question,
    choices,
    answer_index: row.answer_index,
    explanation: row.explanation,
    sort_order: typeof row.sort_order === 'number' ? row.sort_order : 0
  };
}

/**
 * 백엔드 ``GET /quizzes`` 에서 공개 퀴즈 목록을 가져온다(서버 컴포넌트 전용).
 * 실패·미적용 시 정적 폴백을 반환해 대기 화면 콘텐츠가 비지 않도록 한다.
 */
export async function fetchQuizzes(): Promise<QuizItem[]> {
  // 순환 import 방지를 위해 정적 폴백은 지연 로드한다(타입은 본 모듈이 소유).
  const { QUIZ_FALLBACK } = await import('@/lib/quiz-fallback');
  try {
    const response = await fetch(`${serverApiBaseUrl()}/quizzes`, {
      headers: { Accept: 'application/json' },
      // 퀴즈는 자주 바뀌지 않으므로 ISR 로 캐시한다(운영자 수정 반영까지 최대 5분).
      next: { revalidate: 300 }
    });
    if (!response.ok) return QUIZ_FALLBACK;
    const body = (await response.json()) as { items?: unknown };
    if (!Array.isArray(body.items)) return QUIZ_FALLBACK;
    // 정상 응답의 빈 목록은 의도된 상태(전체 비공개 등)로 존중한다 — 폴백은
    // 네트워크 장애·계약 불일치(구버전 페이로드 등)에만 쓴다.
    if (body.items.length === 0) return [];
    const parsed = body.items
      .map(parseQuizItem)
      .filter((it): it is QuizItem => it !== null);
    return parsed.length > 0 ? parsed : QUIZ_FALLBACK;
  } catch {
    return QUIZ_FALLBACK;
  }
}

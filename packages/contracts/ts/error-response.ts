/* eslint-disable */
/**
 * THIS FILE IS AUTO-GENERATED — DO NOT EDIT BY HAND.
 * Source: packages/contracts/schemas/*.schema.json
 * Regenerate: pnpm -C packages/contracts run generate
 */

/**
 * 표준 에러 응답 포맷. 모든 백엔드 모듈은 AGENTS.md §4.5 에 따라 본 포맷으로 응답한다. ZippinException 계열이 공통 핸들러를 거쳐 본 형태로 직렬화된다.
 */
export interface ErrorResponse {
  error: ErrorBody;
}
export interface ErrorBody {
  /**
   * 도메인 에러 코드. SDD §8.2 가 AI 단계 코드를 정의 (SEGMENTATION_FAILED / VLM_TIMEOUT / ANALYSIS_LOW_CONFIDENCE 등). 추가 코드는 모듈별 README 에 등재한다.
   */
  code: string;
  /**
   * 사용자/디버그용 메시지. PII 미포함.
   */
  message: string;
  /**
   * structlog request_id 컨텍스트와 일치 (AGENTS.md §4.5).
   */
  request_id: string;
  /**
   * 에러 발생 시각 (ISO-8601, UTC).
   */
  timestamp: string;
  /**
   * 도메인별 추가 컨텍스트 (예: missing_fields, retry_after). 스키마 미고정.
   */
  details?: {
    [k: string]: unknown | undefined;
  } | null;
}

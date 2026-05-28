/* eslint-disable */
/**
 * THIS FILE IS AUTO-GENERATED — DO NOT EDIT BY HAND.
 * Source: packages/contracts/schemas/*.schema.json
 * Regenerate: pnpm -C packages/contracts run generate
 */

/**
 * 견적 산출 결과. REPORT.estimate 가 RuleEvalResult + 정책 단가표(pricing_policy_ref) 로부터 산출한다. SDD §4.9·§6.3 정본. 특정 단가는 정책에 따라 변경 가능, policy_version 으로 산정 시점 추적.
 */
export interface EstimateResult {
  /**
   * 스키마 버전 (semver).
   */
  schema_version: "1.0.0";
  permit_agency_fee_estimate?: MoneyRange;
  fire_panel_estimate?: MoneyRange1;
  fire_glass_estimate?: MoneyRange2;
  total_range: MoneyRange3;
  /**
   * 산정 전제 (예: '대피공간 가로 길이 = 2.4m 가정').
   */
  assumptions: string[];
  /**
   * 정책 단가표 버전 (예: 'pricing-2026-Q2-v1'). 항상 산정 결과와 함께 기록한다 (SDD §6.3).
   */
  policy_version: string;
  /**
   * 변동 사유 (예: '단가표 누락 항목 1건 → 상담 권고').
   */
  variance_notes?: string[];
  /**
   * 상담 권장 여부. PRICING_POLICY_MISSING 또는 ESTIMATE_OUT_OF_RANGE 발생 시 true (SDD §4.9 오류·예외).
   */
  consultation_required: boolean;
}
/**
 * 행위허가 대행 비용 범위. 운영 정책 v1 예시 단가 = 33만원.
 */
export interface MoneyRange {
  /**
   * 통화. MVP 는 KRW 만 지원.
   */
  currency: "KRW";
  /**
   * 최저 예상 금액 (원, 정수).
   */
  min: number;
  /**
   * 최고 예상 금액 (원, 정수). min <= max 는 RULE/REPORT 의 산정 책임.
   */
  max: number;
  /**
   * 산정 기준 한 줄 요약 (예: '가로 길이 2.4m × 20,000원/m').
   */
  basis?: string | null;
}
/**
 * 방화판 설치 비용 범위. 운영 정책 v1 예시 = 가로 길이 × 2만원/m.
 */
export interface MoneyRange1 {
  /**
   * 통화. MVP 는 KRW 만 지원.
   */
  currency: "KRW";
  /**
   * 최저 예상 금액 (원, 정수).
   */
  min: number;
  /**
   * 최고 예상 금액 (원, 정수). min <= max 는 RULE/REPORT 의 산정 책임.
   */
  max: number;
  /**
   * 산정 기준 한 줄 요약 (예: '가로 길이 2.4m × 20,000원/m').
   */
  basis?: string | null;
}
/**
 * 방화유리 설치 비용 범위. 운영 정책 v1 예시 = 유리 자재비 + 시공비 5만원.
 */
export interface MoneyRange2 {
  /**
   * 통화. MVP 는 KRW 만 지원.
   */
  currency: "KRW";
  /**
   * 최저 예상 금액 (원, 정수).
   */
  min: number;
  /**
   * 최고 예상 금액 (원, 정수). min <= max 는 RULE/REPORT 의 산정 책임.
   */
  max: number;
  /**
   * 산정 기준 한 줄 요약 (예: '가로 길이 2.4m × 20,000원/m').
   */
  basis?: string | null;
}
/**
 * 전체 견적 합산 범위. 항목 미산정 시 최저/최고 폭이 넓어질 수 있다.
 */
export interface MoneyRange3 {
  /**
   * 통화. MVP 는 KRW 만 지원.
   */
  currency: "KRW";
  /**
   * 최저 예상 금액 (원, 정수).
   */
  min: number;
  /**
   * 최고 예상 금액 (원, 정수). min <= max 는 RULE/REPORT 의 산정 책임.
   */
  max: number;
  /**
   * 산정 기준 한 줄 요약 (예: '가로 길이 2.4m × 20,000원/m').
   */
  basis?: string | null;
}

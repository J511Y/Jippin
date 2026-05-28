/* eslint-disable */
/**
 * THIS FILE IS AUTO-GENERATED — DO NOT EDIT BY HAND.
 * Source: packages/contracts/schemas/*.schema.json
 * Regenerate: pnpm -C packages/contracts run generate
 */

/**
 * RULE 모듈의 평가 결과. CommonJudgmentSchema 를 입력으로 산출되며, REPORT 와 REPORT.estimate 의 입력이다. SDD §4.8·§5.1 (I-REPORT-EST-01) 정본.
 */
export interface RuleEvalResult {
  /**
   * 스키마 버전 (semver). 본 ADR-0001 / CMP-527 시점 고정값.
   */
  schema_version: "1.0.0";
  /**
   * 최종 판정. 집계 우선순위 DENY > WARN > ALLOW > HOLD 는 RULE 모듈 내부에서 강제 (SDD §4.8 데이터 계약).
   */
  verdict: "ALLOW" | "WARN" | "DENY" | "HOLD";
  /**
   * 필요 방화시설 목록. REPORT.estimate 의 산정 입력.
   */
  required_facilities: RequiredFacility[];
  /**
   * 행위허가 필요 여부.
   */
  permit_required: boolean;
  /**
   * 법령 근거 목록. 모든 화면에 노출되어야 한다 (FR-REPORT-009).
   *
   * @minItems 0
   */
  legal_basis: LegalBasis[];
  /**
   * 룰셋 카탈로그 버전 (예: '2026-05-01'). 결정성 100%(NFR-QUAL-002) 의 추적 키.
   */
  ruleset_version: string;
  /**
   * RULE 평가 시점 (ISO-8601).
   */
  evaluated_at: string;
  /**
   * 사용자에게 표시할 한 줄 요약. RULE 의 메시지 빌더 결과.
   */
  user_message?: string | null;
}
export interface RequiredFacility {
  /**
   * 방화시설/안전시설 코드.
   */
  code: "FIRE_PANEL" | "FIRE_GLASS" | "EVACUATION_SPACE" | "SPRINKLER" | "AUTOMATIC_DOOR_CLOSER";
  /**
   * 사용자 노출 라벨.
   */
  label: string;
  /**
   * 산정 기준 (예: '대피공간 인접 벽 가로 길이').
   */
  measurement_basis?: string | null;
}
export interface LegalBasis {
  /**
   * 법령명 (예: '건축법 시행령').
   */
  statute: string;
  /**
   * 조·항·호 (예: '제46조 제5항').
   */
  article: string;
  /**
   * 한 줄 요약.
   */
  summary: string;
  /**
   * 원문 링크 (있는 경우).
   */
  url?: string | null;
}

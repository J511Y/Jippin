/* eslint-disable */
/**
 * THIS FILE IS AUTO-GENERATED — DO NOT EDIT BY HAND.
 * Source: packages/contracts/schemas/*.schema.json
 * Regenerate: pnpm -C packages/contracts run generate
 */

/**
 * FLOW_GUARD 의 충분성·충돌·고위험 판정 결과. CHAT/OVERLAY/RULE 분기를 결정한다. SDD §4.7·§5.1 (I-FLOW-02) 정본.
 */
export interface CompletionDecision {
  /**
   * 스키마 버전 (semver). 본 ADR-0001 / CMP-527 시점 고정값.
   */
  schema_version: "1.0.0";
  /**
   * 결정 분기. SDD §4.7 의 4가지: ASK_MORE(추가 질의), REQUEST_OVERLAY_REVIEW(도면 재확인), PROCEED_RULE(룰 평가 진행), HOLD_OR_HANDOFF(보류·상담 전환).
   */
  decision: "ASK_MORE" | "REQUEST_OVERLAY_REVIEW" | "PROCEED_RULE" | "HOLD_OR_HANDOFF";
  /**
   * 결정 사유. 사용자 노출 텍스트가 아닌 디버그/감사용. 결정성 보장을 위해 한 줄.
   */
  reason: string;
  /**
   * 보완이 필요한 CommonJudgmentSchema 필드 경로 목록 (예: 'judgment_values.has_sprinkler').
   */
  missing_fields: string[];
  /**
   * 후속 행동 시퀀스. 클라이언트/CHAT 가 그대로 dispatch 한다.
   */
  next_actions: NextAction[];
  /**
   * 신뢰도 요약. flow_guard_decisions 영속화에 사용 (SDD §6.3).
   */
  confidence_summary?: {
    /**
     * AI 분석 종합 신뢰도.
     */
    ai_overall?: number;
    /**
     * OVERLAY 선택값 종합 신뢰도.
     */
    overlay_overall?: number;
  };
  /**
   * 감지된 충돌 종류. 동시에 다수 발생하면 HOLD_OR_HANDOFF 로 보수 분기 (DECISION_AMBIGUOUS, SDD §4.7).
   */
  conflict_flags?: (
    | "WALL_TYPE_CONFLICT"
    | "OVERLAY_SELECTION_OUT_OF_SCOPE"
    | "LOAD_BEARING_SELECTED"
    | "EVACUATION_SPACE_REMOVAL"
    | "AI_LOW_CONFIDENCE"
    | "USER_CONTRADICTION"
  )[];
}
export interface NextAction {
  /**
   * 행동 종류.
   */
  kind: "ASK_USER_QUESTION" | "RE_OPEN_OVERLAY" | "INVOKE_RULE" | "OFFER_HANDOFF";
  /**
   * ASK_USER_QUESTION 인 경우 보완 대상 필드 경로.
   */
  target_field?: string | null;
  /**
   * 사용자에게 노출되는 보완 질의 문구 (생활어, NFR-QUAL 의 비전문 사용자 친화 원칙).
   */
  prompt?: string | null;
  /**
   * 행동을 노출할 채널.
   */
  channel?: "INLINE_CHAT" | "OVERLAY_PANEL" | "HANDOFF_CTA" | null;
}

/* eslint-disable */
/**
 * THIS FILE IS AUTO-GENERATED — DO NOT EDIT BY HAND.
 * Source: packages/contracts/schemas/*.schema.json
 * Regenerate: pnpm -C packages/contracts run generate
 */

/**
 * 에이전트 런 SSE 스트림의 단일 이벤트 envelope. SSE `event:` 필드가 type, `data:` 필드가 본 JSON 이다. type 별 discriminated union — 클라이언트는 type 으로 분기한다.
 */
export type AgentSseEvent =
  | TokenEvent
  | ToolStepEvent
  | StateChangeEvent
  | MessageEvent
  | ErrorEvent
  | DoneEvent;

/**
 * LLM 토큰 스트리밍 조각. 영속화되지 않으며 최종 message 이벤트만 저장된다.
 */
export interface TokenEvent {
  schema_version: "1.0.0";
  type: "token";
  /**
   * 런 내 단조 증가 시퀀스.
   */
  seq: number;
  /**
   * assistant 응답의 토큰 조각. 누적은 클라이언트가 한다.
   */
  delta: string;
}
/**
 * 도구 호출 진행 상황. 원장(chat_tool_calls) 의 사용자 친화 투영.
 */
export interface ToolStepEvent {
  schema_version: "1.0.0";
  type: "tool_step";
  seq: number;
  /**
   * 실행 중/완료된 도구 이름.
   */
  tool_name: string;
  /**
   * 도구 분류 (chat_tool_calls.tool_kind 와 정합).
   */
  tool_kind:
    | "retrieval"
    | "db_query"
    | "external_api"
    | "ai_model"
    | "rule_engine"
    | "render"
    | "notification"
    | "other";
  /**
   * 도구 라이프사이클 상태.
   */
  status: "started" | "succeeded" | "failed";
  /**
   * 사용자 노출용 짧은 진행 요약.
   */
  summary?: string | null;
  /**
   * status=failed 시 안정적 에러 코드.
   */
  error_code?: string | null;
}
/**
 * 세션 status / completion_decision 전이 알림.
 */
export interface StateChangeEvent {
  schema_version: "1.0.0";
  type: "state_change";
  seq: number;
  /**
   * 세션 상태 머신의 새 상태.
   */
  session_status:
    | "draft"
    | "address_ready"
    | "floorplan_selected"
    | "analyzing"
    | "awaiting_overlay"
    | "collecting_info"
    | "ready_for_rule"
    | "report_ready"
    | "handoff"
    | "expired"
    | "deleted";
  /**
   * FLOW_GUARD 결정 (completion-decision 계약의 decision enum 재사용).
   */
  completion_decision?:
    | "ASK_MORE"
    | "REQUEST_OVERLAY_REVIEW"
    | "PROCEED_RULE"
    | "HOLD_OR_HANDOFF"
    | null;
}
/**
 * 완료된 메시지 (영속화 후 전송).
 */
export interface MessageEvent {
  schema_version: "1.0.0";
  type: "message";
  seq: number;
  /**
   * 런타임이 만든 메시지 role.
   */
  role: "assistant" | "system" | "tool";
  /**
   * 완료된 메시지 본문.
   */
  content: string;
  /**
   * 영속화된 chat_messages.id.
   */
  message_id?: string | null;
  /**
   * A2UI 렌더링 payload (chat_messages.ui_components 와 정합).
   */
  ui_components?: {
    [k: string]: unknown | undefined;
  }[];
}
/**
 * 런 중 발생한 오류.
 */
export interface ErrorEvent {
  schema_version: "1.0.0";
  type: "error";
  seq: number;
  /**
   * 안정적 에러 코드.
   */
  error_code: string;
  /**
   * 사람이 읽을 수 있는 짧은 메시지.
   */
  message: string;
  /**
   * true 면 스트림이 계속될 수 있고, false 면 done 이 뒤따른다.
   */
  recoverable: boolean;
}
/**
 * 스트림 종료 신호. 항상 마지막 이벤트.
 */
export interface DoneEvent {
  schema_version: "1.0.0";
  type: "done";
  seq: number;
  /**
   * 런 종료 상태. awaiting_input/interrupted 는 resume 가능.
   */
  run_status: "succeeded" | "failed" | "awaiting_input" | "interrupted" | "cancelled";
}

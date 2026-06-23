/* eslint-disable */
/**
 * THIS FILE IS AUTO-GENERATED — DO NOT EDIT BY HAND.
 * Source: packages/contracts/schemas/*.schema.json
 * Regenerate: pnpm -C packages/contracts run generate
 */

/**
 * 에이전트 세션 런 시작 요청 body. `POST /sessions/{session_id}/agent/runs` 정본. 클라이언트는 role='user' message 만 보낼 수 있고, assistant/tool message 는 런타임만 생성한다.
 */
export interface AgentRunRequest {
  /**
   * 스키마 버전 (semver). 본 시점 고정값.
   */
  schema_version: "1.0.0";
  message: UserMessage;
  /**
   * 런타임/관측용 부가 정보. 신뢰할 수 없는 입력이므로 service-controlled 필드로 승격하지 않는다.
   */
  metadata?: {
    [k: string]: unknown | undefined;
  };
}
/**
 * 이번 턴의 사용자 입력 메시지.
 */
export interface UserMessage {
  /**
   * 공개 endpoint 에서 클라이언트가 만들 수 있는 유일한 role.
   */
  role: "user";
  /**
   * 사용자 발화 본문. 요청 메모리/DB row/LLM 호출 비대화를 막기 위해 최대 8000자.
   */
  content: string;
}

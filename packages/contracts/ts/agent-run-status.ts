/* eslint-disable */
/**
 * THIS FILE IS AUTO-GENERATED — DO NOT EDIT BY HAND.
 * Source: packages/contracts/schemas/*.schema.json
 * Regenerate: pnpm -C packages/contracts run generate
 */

/**
 * agent_runs row 의 클라이언트 노출 투영. `GET /sessions/{session_id}/agent/runs/{run_id}` 정본. 재연결 시 재스트림 없이 상태를 확인하는 데 쓴다.
 */
export interface AgentRunStatus {
  /**
   * 스키마 버전 (semver).
   */
  schema_version: "1.0.0";
  /**
   * agent_runs.id.
   */
  id: string;
  /**
   * 소유 세션 id.
   */
  session_id: string;
  /**
   * LangGraph 체크포인터 thread_id (= session_id).
   */
  thread_id: string;
  /**
   * 런 상태 머신.
   */
  status:
    | "pending"
    | "running"
    | "awaiting_input"
    | "interrupted"
    | "succeeded"
    | "failed"
    | "cancelled";
  /**
   * 이 런에 사용된 LLM 모델 식별자 (예: openai:gpt-5.4-mini).
   */
  model: string;
  /**
   * 마지막으로 진입한 플로우 단계 라벨.
   */
  current_step?: string | null;
  /**
   * LangSmith 트레이스 URL (있으면).
   */
  langsmith_run_url?: string | null;
  /**
   * 실패 시 안정적 에러 코드.
   */
  error_code?: string | null;
  /**
   * 실패 시 사람이 읽을 수 있는 짧은 메시지 (원본 payload·PII 비포함).
   */
  error_message?: string | null;
  /**
   * 런 시작 시각.
   */
  started_at?: string | null;
  /**
   * 런 종료 시각.
   */
  finished_at?: string | null;
  /**
   * row 생성 시각.
   */
  created_at: string;
}

/**
 * 에이전트 SSE 스트림 파서 (CMP-DIRECT).
 *
 * 백엔드(api.jippin.ai)의 `POST /sessions/{id}/agent/runs` 가 보내는 text/event-stream
 * 을 파싱한다. 이벤트 타입은 `packages/contracts/schemas/agent-sse-event.schema.json`
 * 의 discriminated union(token/tool_step/state_change/message/error/done)과 정합한다.
 *
 * 본 모듈은 순수 함수만 둔다(React/네트워크 비의존) — 단위 테스트가 쉽도록.
 */

export type AgentSseEvent =
  | { type: 'token'; seq: number; delta: string }
  | {
      type: 'tool_step';
      seq: number;
      tool_name: string;
      tool_kind: string;
      status: 'started' | 'succeeded' | 'failed';
      summary: string | null;
      error_code: string | null;
      /**
       * write_todos 도구일 때만 채워지는 최신 전체 계획(누적 아님, 최신이 전체 상태).
       * PlanPanel 이 이 값으로 plan 을 교체한다. 옵셔널 — 하위호환(파서 변경 불필요).
       */
      todos?: Array<{ content: string; status: string }>;
    }
  | {
      type: 'state_change';
      seq: number;
      session_status: string;
      completion_decision: string | null;
    }
  | {
      type: 'message';
      seq: number;
      role: 'assistant' | 'system' | 'tool';
      content: string;
      message_id: string | null;
      ui_components?: Array<Record<string, unknown>>;
    }
  | {
      type: 'error';
      seq: number;
      error_code: string;
      message: string;
      recoverable: boolean;
      active_run_id?: string | null;
      active_run_status?: string | null;
    }
  | { type: 'done'; seq: number; run_status: string };

export type RawSseFrame = { event: string; data: unknown };

/**
 * 누적 버퍼에서 완성된 프레임(빈 줄 `\n\n` 구분)만 떼어 내고 나머지를 돌려준다.
 * 마지막 조각은 아직 끝나지 않았을 수 있으므로 rest 로 남긴다.
 */
export function splitSseBuffer(buffer: string): { frames: string[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, '\n');
  const parts = normalized.split('\n\n');
  const rest = parts.pop() ?? '';
  return { frames: parts.filter((frame) => frame.trim().length > 0), rest };
}

/** 단일 SSE 프레임을 {event, data} 로 파싱. 주석(`:`)/빈 data/깨진 JSON 은 null. */
export function parseSseFrame(frame: string): RawSseFrame | null {
  let event = 'message';
  const dataLines: string[] = [];
  for (const line of frame.split('\n')) {
    if (line.startsWith(':')) continue; // 하트비트/주석
    if (line.startsWith('event:')) {
      event = line.slice('event:'.length).trim();
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).replace(/^ /, ''));
    }
  }
  const data = dataLines.join('\n');
  if (!data) return null;
  try {
    return { event, data: JSON.parse(data) };
  } catch {
    return null;
  }
}

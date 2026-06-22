'use client';

/**
 * 에이전트 SSE 스트림 훅 (CMP-DIRECT).
 *
 * 브라우저가 백엔드(api.jippin.ai)로 **직접** `fetch`+ReadableStream POST 한다
 * (Vercel 우회). EventSource 는 Authorization 헤더를 실을 수 없어 쓰지 않는다.
 * token/tool_step/state_change/message/error/done 이벤트를 받아 채팅 상태로 환원한다.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import type { ChatMessage, DynamicComponentSpec } from '@/components/a2ui';
import { apiBaseUrl } from '@/lib/api-base-url';
import { getAccessToken } from '@/lib/auth-token';
import { ensureAnonymousSession } from '@/lib/leads/ensure-anonymous-session';

import { parseSseFrame, splitSseBuffer, type AgentSseEvent } from './sse';

export type AgentStreamStatus = 'idle' | 'streaming' | 'done' | 'error';

function uid(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

async function resolveToken(): Promise<string> {
  const existing = getAccessToken();
  if (existing) return existing;
  const session = await ensureAnonymousSession();
  return session.token;
}

// resumable run id 를 세션별 sessionStorage 에 보존한다 — 컴포넌트 remount/새로고침
// 후에도 다음 send 가 /resume 로 이어갈 수 있게(없으면 새 런이 AGENT_RUN_ALREADY_ACTIVE).
const resumeKey = (sessionId: string) => `jippin:agent-resume:${sessionId}`;

function loadResumeId(sessionId: string): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.sessionStorage.getItem(resumeKey(sessionId));
  } catch {
    return null;
  }
}

function saveResumeId(sessionId: string, id: string | null): void {
  if (typeof window === 'undefined') return;
  try {
    if (id) window.sessionStorage.setItem(resumeKey(sessionId), id);
    else window.sessionStorage.removeItem(resumeKey(sessionId));
  } catch {
    /* sessionStorage 비가용(SSR/프라이빗) — 무시 */
  }
}

function toDynamic(component: Record<string, unknown>): DynamicComponentSpec | undefined {
  const kind = typeof component.kind === 'string' ? component.kind : undefined;
  if (!kind) return undefined;
  const payload =
    component.payload && typeof component.payload === 'object'
      ? (component.payload as Record<string, unknown>)
      : {};
  return { kind, payload };
}

export interface UseAgentStream {
  messages: ChatMessage[];
  streamingText: string;
  toolActivity: string | null;
  status: AgentStreamStatus;
  error: string | null;
  send: (content: string) => Promise<void>;
  stop: () => void;
}

export function useAgentStream(sessionId: string): UseAgentStream {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingText, setStreamingText] = useState('');
  const [toolActivity, setToolActivity] = useState<string | null>(null);
  const [status, setStatus] = useState<AgentStreamStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const streamingRef = useRef(false);
  // 직전 런이 resumable(interrupted/awaiting_input)로 끝났으면 그 run_id 를 들고
  // 있다가 다음 send 에서 /resume 로 보낸다. 그렇지 않으면 null(=새 런 시작).
  const resumableRunIdRef = useRef<string | null>(null);

  // remount/새로고침 시 sessionStorage 에서 resumable run id 를 복원한다.
  useEffect(() => {
    resumableRunIdRef.current = loadResumeId(sessionId);
  }, [sessionId]);

  const setResumeId = useCallback(
    (id: string | null) => {
      resumableRunIdRef.current = id;
      saveResumeId(sessionId, id);
    },
    [sessionId],
  );

  const send = useCallback(
    async (content: string) => {
      const text = content.trim();
      if (!text || streamingRef.current) return;

      streamingRef.current = true;
      setError(null);
      setStatus('streaming');
      setToolActivity(null);
      setStreamingText('');
      setMessages((prev) => [
        ...prev,
        { id: uid(), role: 'user', content: text, createdAt: new Date().toISOString() },
      ]);

      const controller = new AbortController();
      abortRef.current = controller;
      let assembled = '';
      let runStatus: string | null = null;

      try {
        const token = await resolveToken();
        const base = apiBaseUrl();
        // 직전 런이 resumable 이면 같은 런을 /resume 로 이어 간다 — 아니면 새 런 시작.
        // (활성 런 부분 유니크 때문에 새로 시작하면 AGENT_RUN_ALREADY_ACTIVE 가 난다.)
        const resumeRunId = resumableRunIdRef.current;
        const url = resumeRunId
          ? `${base}/sessions/${sessionId}/agent/runs/${resumeRunId}/resume`
          : `${base}/sessions/${sessionId}/agent/runs`;
        const res = await fetch(url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'text/event-stream',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            schema_version: '1.0.0',
            message: { role: 'user', content: text },
          }),
          signal: controller.signal,
        });
        if (!res.ok || !res.body) {
          // resume 시도가 실패(예: 런이 이미 종료돼 409)하면 저장된 id 를 비워
          // 다음 send 가 새 런을 시작하게 한다(stale resume 복구).
          if (resumeRunId) setResumeId(null);
          throw new Error(`에이전트 요청에 실패했습니다 (HTTP ${res.status}).`);
        }
        setResumeId(res.headers.get('X-Agent-Run-Id') ?? resumeRunId);

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const { frames, rest } = splitSseBuffer(buffer);
          buffer = rest;
          for (const frame of frames) {
            const parsed = parseSseFrame(frame);
            if (!parsed) continue;
            const ev = parsed.data as AgentSseEvent;
            if (ev.type === 'token') {
              assembled += ev.delta;
              setStreamingText(assembled);
            } else if (ev.type === 'tool_step') {
              setToolActivity(`${ev.tool_name} · ${ev.status}`);
            } else if (ev.type === 'message') {
              // emit_ui_component 가 복수 컴포넌트를 보내면 전부 보존해 렌더한다.
              const dynamics = (ev.ui_components ?? [])
                .map(toDynamic)
                .filter((d): d is DynamicComponentSpec => d !== undefined);
              setMessages((prev) => [
                ...prev,
                {
                  id: ev.message_id ?? uid(),
                  role: 'assistant',
                  content: ev.content,
                  createdAt: new Date().toISOString(),
                  dynamics,
                },
              ]);
              assembled = '';
              setStreamingText('');
            } else if (ev.type === 'error') {
              setError(ev.message);
            } else if (ev.type === 'done') {
              runStatus = ev.run_status;
            }
          }
        }
        setToolActivity(null);
        setStreamingText('');
        if (runStatus === 'interrupted' || runStatus === 'awaiting_input') {
          // resumable — run id 를 유지(이미 X-Agent-Run-Id 로 채워짐)해 다음 send 가
          // /resume 한다. 입력 가능 상태로 둔다.
          setStatus('done');
        } else if (runStatus === 'succeeded' || runStatus === 'cancelled') {
          setResumeId(null);
          setStatus('done');
        } else if (runStatus === 'failed') {
          setResumeId(null);
          setStatus('error');
        } else {
          // runStatus === null: done 프레임 없이 스트림이 끊김(네트워크/프록시). run id 를
          // 유지해 다음 send 가 /resume 하도록 하고 오류를 노출한다(#done-required).
          setError((prev) => prev ?? '연결이 끊겼습니다. 다시 보내면 이어서 진행합니다.');
          setStatus('error');
        }
      } catch (err) {
        if ((err as Error)?.name === 'AbortError') {
          setStatus('idle');
          return;
        }
        setError((err as Error)?.message ?? '알 수 없는 오류가 발생했습니다.');
        setStatus('error');
      } finally {
        streamingRef.current = false;
        abortRef.current = null;
      }
    },
    [sessionId, setResumeId],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    streamingRef.current = false;
    setToolActivity(null);
    setStatus('idle');
  }, []);

  return { messages, streamingText, toolActivity, status, error, send, stop };
}

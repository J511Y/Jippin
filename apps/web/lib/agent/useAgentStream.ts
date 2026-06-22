'use client';

/**
 * 에이전트 SSE 스트림 훅 (CMP-DIRECT).
 *
 * 브라우저가 백엔드(api.jippin.ai)로 **직접** `fetch`+ReadableStream POST 한다
 * (Vercel 우회). EventSource 는 Authorization 헤더를 실을 수 없어 쓰지 않는다.
 * token/tool_step/state_change/message/error/done 이벤트를 받아 채팅 상태로 환원한다.
 */

import { useCallback, useRef, useState } from 'react';

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
      let finalStatus: AgentStreamStatus = 'done';

      try {
        const token = await resolveToken();
        const res = await fetch(`${apiBaseUrl()}/sessions/${sessionId}/agent/runs`, {
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
          throw new Error(`에이전트 요청에 실패했습니다 (HTTP ${res.status}).`);
        }

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
              const firstComponent = ev.ui_components?.[0];
              const dynamic = firstComponent ? toDynamic(firstComponent) : undefined;
              setMessages((prev) => [
                ...prev,
                {
                  id: ev.message_id ?? uid(),
                  role: 'assistant',
                  content: ev.content,
                  createdAt: new Date().toISOString(),
                  dynamic,
                },
              ]);
              assembled = '';
              setStreamingText('');
            } else if (ev.type === 'error') {
              setError(ev.message);
            } else if (ev.type === 'done') {
              finalStatus = ev.run_status === 'failed' ? 'error' : 'done';
            }
          }
        }
        setToolActivity(null);
        setStreamingText('');
        setStatus(finalStatus);
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
    [sessionId],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    streamingRef.current = false;
    setToolActivity(null);
    setStatus('idle');
  }, []);

  return { messages, streamingText, toolActivity, status, error, send, stop };
}

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
import { getAccessToken, setAccessToken } from '@/lib/auth-token';
import { ensureAnonymousSession } from '@/lib/leads/ensure-anonymous-session';
import { createClient } from '@/lib/supabase/client';

import { parseSseFrame, splitSseBuffer, type AgentSseEvent } from './sse';

export type AgentStreamStatus = 'idle' | 'streaming' | 'done' | 'error';

function uid(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

async function resolveToken(): Promise<string> {
  // Supabase 세션이 토큰 정본 — SDK 가 만료 임박 시 갱신하므로 getSession 으로 현재
  // 토큰을 받아 메모리에 동기화한다(만료된 메모리 토큰으로 401 나는 것 방지). 세션이
  // 없으면 익명 세션을 만든다.
  try {
    const supabase = createClient();
    const {
      data: { session }
    } = await supabase.auth.getSession();
    if (session?.access_token) {
      setAccessToken(session.access_token);
      return session.access_token;
    }
  } catch {
    /* getSession 실패 — 메모리/익명 폴백 */
  }
  const existing = getAccessToken();
  if (existing) return existing;
  const session = await ensureAnonymousSession();
  return session.token;
}

// 401 시 한 번 강제 갱신한다. 직접 fetch 라 apiClient 의 401 refresh 경로를 못 타므로
// Supabase refreshSession 으로 새 토큰을 받아 메모리에 반영한다.
async function refreshToken(): Promise<string | null> {
  try {
    const supabase = createClient();
    const {
      data: { session }
    } = await supabase.auth.refreshSession();
    if (session?.access_token) {
      setAccessToken(session.access_token);
      return session.access_token;
    }
  } catch {
    /* refresh 실패 */
  }
  return null;
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

// 런이 terminal(succeeded/failed/cancelled) 이거나 없는지 서버에 확인한다. resume
// 실패 시 id 를 비워도 되는지 판단용 — 아직 running(미마감)이면 false(=id 유지).
async function isRunTerminalOrMissing(
  base: string,
  sessionId: string,
  runId: string,
  token: string,
): Promise<boolean> {
  try {
    const res = await fetch(`${base}/sessions/${sessionId}/agent/runs/${runId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.status === 404) return true;
    if (!res.ok) return false;
    const data = (await res.json()) as { status?: string };
    return ['succeeded', 'failed', 'cancelled'].includes(data?.status ?? '');
  } catch {
    return false; // 확인 실패 시 보수적으로 id 유지
  }
}

// 409 AGENT_RUN_ALREADY_ACTIVE 응답의 detail.active_run_id 를 읽는다(복구용).
async function readActiveRunId(res: Response): Promise<string | null> {
  try {
    const data = (await res.clone().json()) as {
      detail?: { active_run_id?: string };
    };
    const id = data?.detail?.active_run_id;
    return typeof id === 'string' && id ? id : null;
  } catch {
    return null;
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

  // resumable run id 를 복원하고, 언마운트/세션변경 시 진행 중 스트림을 중단한다 —
  // 옛 스트림이 프레임을 계속 흘리는 누수를 막는다(#stale-stream-leak). 메시지 등
  // useState 리셋은 부모가 AgentChat 을 sessionId 로 key 해 remount 시키는 것으로
  // 처리한다(effect 안 setState 회피).
  useEffect(() => {
    resumableRunIdRef.current = loadResumeId(sessionId);
    return () => {
      abortRef.current?.abort();
      abortRef.current = null;
      streamingRef.current = false;
    };
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
        let token = await resolveToken();
        const base = apiBaseUrl();
        const startUrl = `${base}/sessions/${sessionId}/agent/runs`;
        const body = JSON.stringify({
          schema_version: '1.0.0',
          message: { role: 'user', content: text },
        });
        const makeInit = (tok: string): RequestInit => ({
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'text/event-stream',
            Authorization: `Bearer ${tok}`,
          },
          body,
          signal: controller.signal,
        });
        // 만료 토큰이면 1회 갱신 후 재시도(직접 fetch 라 apiClient 401 경로를 못 탐).
        const fetchAuthed = async (url: string): Promise<Response> => {
          const res = await fetch(url, makeInit(token));
          if (res.status !== 401) return res;
          const refreshed = await refreshToken();
          if (!refreshed) return res;
          token = refreshed;
          return fetch(url, makeInit(token));
        };

        // 직전 런이 resumable 이면 같은 런을 /resume 로 이어 간다 — 아니면 새 런 시작.
        // (활성 런 부분 유니크 때문에 새로 시작하면 AGENT_RUN_ALREADY_ACTIVE 가 난다.)
        const resumeRunId = resumableRunIdRef.current;
        let res = await fetchAuthed(
          resumeRunId
            ? `${base}/sessions/${sessionId}/agent/runs/${resumeRunId}/resume`
            : startUrl,
        );

        // resume 실패 시: 서버가 런이 terminal/missing 임을 확인하면 id 를 비우고
        // 같은 메시지로 새 런을 1회 재시도한다(메시지 유실 방지). 아직 running(미마감)
        // 이면 id 를 유지해 사용자가 나중에 다시 resume 할 수 있게 한다.
        if (
          (!res.ok || !res.body) &&
          resumeRunId &&
          (await isRunTerminalOrMissing(base, sessionId, resumeRunId, token))
        ) {
          setResumeId(null);
          res = await fetchAuthed(startUrl);
        }

        // 새 런 시작이 409(이미 활성 런)면, 서버가 준 active_run_id 를 저장해 다음
        // send 가 그 런을 resume/이어가게 한다 — 헤더를 못 받은 새 탭/유실 복구.
        if (res.status === 409) {
          const activeId = await readActiveRunId(res);
          if (activeId) setResumeId(activeId);
        }

        if (!res.ok || !res.body) {
          throw new Error(`에이전트 요청에 실패했습니다 (HTTP ${res.status}).`);
        }
        setResumeId(res.headers.get('X-Agent-Run-Id') ?? resumableRunIdRef.current);

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

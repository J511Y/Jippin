'use client';

/**
 * 에이전트 SSE 스트림 훅 (CMP-DIRECT).
 *
 * 브라우저가 백엔드(api.jippin.ai)로 **직접** `fetch`+ReadableStream POST 한다
 * (Vercel 우회). EventSource 는 Authorization 헤더를 실을 수 없어 쓰지 않는다.
 * token/tool_step/state_change/message/error/done 이벤트를 받아 채팅 상태로 환원한다.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import type { A2uiComponent, ChatMessage } from '@/components/a2ui';
import { apiBaseUrl } from '@/lib/api-base-url';
import { getAccessToken, setAccessToken } from '@/lib/auth-token';
import { ensureAnonymousSession } from '@/lib/leads/ensure-anonymous-session';
import { createClient } from '@/lib/supabase/client';

import { parseSseFrame, splitSseBuffer, type AgentSseEvent } from './sse';
import { toolDisplay, toolStepText } from './tool-labels';

export type AgentStreamStatus = 'idle' | 'streaming' | 'done' | 'error';

// 에이전트 SSE 전용 base URL. `/api` 프록시(Next dev / Vercel rewrite)를 거치면 응답이
// 버퍼링되어 토큰 스트리밍이 한꺼번에 도착할 수 있다 — `NEXT_PUBLIC_AGENT_BASE_URL` 이
// 설정되면 백엔드로 **직접** 연결해 프록시 버퍼링을 우회한다(직접 연결은 백엔드 CORS 가
// 해당 웹 오리진을 허용해야 함). 미설정 시 apiBaseUrl(`/api`)로 폴백(현행 동작 유지).
function agentBaseUrl(): string {
  const direct = process.env.NEXT_PUBLIC_AGENT_BASE_URL;
  return direct && direct.length > 0 ? direct : apiBaseUrl();
}

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

// 409 AGENT_RUN_ALREADY_ACTIVE 응답의 detail(active_run_id/status)을 읽는다(복구용).
async function readActiveRun(res: Response): Promise<{ id: string; status: string } | null> {
  try {
    const data = (await res.clone().json()) as {
      detail?: { active_run_id?: string; status?: string };
    };
    const id = data?.detail?.active_run_id;
    if (typeof id !== 'string' || !id) return null;
    return { id, status: typeof data?.detail?.status === 'string' ? data.detail.status : '' };
  } catch {
    return null;
  }
}

// run_status → resume mode. interrupted/드롭은 reconnect(다음 입력 전 no-message drain),
// awaiting_input 은 reply(메시지 전송), 그 외(terminal)는 null.
function modeForStatus(status: string): 'reply' | 'reconnect' | null {
  if (status === 'awaiting_input') return 'reply';
  if (status === 'interrupted') return 'reconnect';
  return null;
}

/** 도구 진행 단계 한 줄 — UI(MessageThread)가 스피너/체크로 렌더한다. */
export interface ToolActivityStep {
  /** 안정 키(같은 toolName 의 마지막 started 를 갱신할 때 재사용). */
  id: string;
  toolName: string;
  status: ToolStepStatusValue;
  /** 화이트라벨 문구(toolStepText 결과). raw 도구명은 절대 담지 않는다. */
  text: string;
}

type ToolStepStatusValue = 'started' | 'succeeded' | 'failed';

/**
 * deepagents 의 write_todos 계획 한 단계. status 는 들어오는 문자열을 그대로 둔다 —
 * 알 수 없는 값은 UI(PlanPanel)에서 'pending' 으로 취급한다.
 */
export interface PlanTodo {
  content: string;
  status: 'pending' | 'in_progress' | 'completed';
}

export interface UseAgentStream {
  messages: ChatMessage[];
  streamingText: string;
  /** 하위호환 — 마지막 활동 한 줄. 신규 UI 는 activity 배열을 쓴다. */
  toolActivity: string | null;
  /** 이번 턴의 도구 활동 타임라인(숨김 도구는 제외). */
  activity: ToolActivityStep[];
  /** write_todos 가 세운 최신 전체 계획(턴을 넘어 유지·갱신). 비면 빈 배열. */
  plan: PlanTodo[];
  status: AgentStreamStatus;
  error: string | null;
  send: (content: string) => Promise<void>;
  stop: () => void;
}

export function useAgentStream(sessionId: string): UseAgentStream {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingText, setStreamingText] = useState('');
  const [toolActivity, setToolActivity] = useState<string | null>(null);
  const [activity, setActivity] = useState<ToolActivityStep[]>([]);
  // 계획은 턴을 넘어 유지·갱신한다(send 시작 시 초기화하지 않음). sessionId 가 바뀌면
  // 부모가 Conversation 을 key 로 remount 시키므로 자연히 초기화된다.
  const [plan, setPlan] = useState<PlanTodo[]>([]);
  const [status, setStatus] = useState<AgentStreamStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const streamingRef = useRef(false);
  // 직전 런이 resumable(interrupted/awaiting_input)로 끝났으면 그 run_id 를 들고
  // 있다가 다음 send 에서 /resume 로 보낸다. 그렇지 않으면 null(=새 런 시작).
  const resumableRunIdRef = useRef<string | null>(null);
  // resume 의 의미를 구분한다: 'reply'=awaiting_input 후속 입력(메시지 전송),
  // 'reconnect'=drop 으로 끊긴 in-flight 런 이어 받기(메시지 없이 drain). 서버
  // reconnect 경로가 message 를 무시하므로, 새 입력을 reconnect 로 보내면 유실된다
  // → reconnect 는 no-message 로 먼저 drain 하고 새 입력은 그 뒤 새 턴으로 보낸다(#reconnect).
  const resumeModeRef = useRef<'reply' | 'reconnect' | null>(null);

  // resumable run id 를 복원하고, 언마운트/세션변경 시 진행 중 스트림을 중단한다 —
  // 옛 스트림이 프레임을 계속 흘리는 누수를 막는다(#stale-stream-leak). 메시지 등
  // useState 리셋은 부모가 AgentChat 을 sessionId 로 key 해 remount 시키는 것으로
  // 처리한다(effect 안 setState 회피).
  useEffect(() => {
    // 빈 sessionId(=compose 단계) 가드: 히스토리 로드/resume 복원을 no-op 으로 둔다.
    if (!sessionId) return;
    resumableRunIdRef.current = loadResumeId(sessionId);
    // 마운트/새로고침 시 영속된 transcript 를 복원한다 — 완료된 런은 resume 스트림이
    // 없어 SSE 로 다시 못 받으므로(#load-history-on-mount). 라이브 메시지가 이미 있으면
    // 덮어쓰지 않는다.
    let ignore = false;
    void (async () => {
      try {
        const token = await resolveToken();
        const res = await fetch(
          `${agentBaseUrl()}/sessions/${sessionId}/agent/messages`,
          { headers: { Authorization: `Bearer ${token}` } },
        );
        if (ignore || !res.ok) return;
        const data = (await res.json()) as {
          messages?: Array<{
            id: string;
            role: string;
            content: string;
            ui_components?: Record<string, unknown>[];
            created_at?: string;
          }>;
        };
        const items = data?.messages ?? [];
        if (ignore || items.length === 0) return;
        const history: ChatMessage[] = items.map((m) => ({
          id: String(m.id),
          role: m.role === 'assistant' ? 'assistant' : 'user',
          content: typeof m.content === 'string' ? m.content : '',
          createdAt: m.created_at ?? new Date().toISOString(),
          // A2UI 컴포넌트는 raw 그대로 보존한다 — A2uiSurface 가 json-render spec /
          // 레거시 {kind,payload} 양쪽을 해석한다.
          dynamics:
            m.role === 'assistant' ? ((m.ui_components ?? []) as A2uiComponent[]) : undefined,
        }));
        setMessages((prev) => (prev.length > 0 ? prev : history));
      } catch {
        /* 히스토리 로드 실패 — 빈 채로 시작 */
      }
    })();
    return () => {
      ignore = true;
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
      // 빈 sessionId(compose 단계)면 send 를 no-op 으로 둔다(SessionChat 이 세션 생성 후 재마운트).
      if (!text || !sessionId || streamingRef.current) return;

      streamingRef.current = true;
      setError(null);
      setStatus('streaming');
      setToolActivity(null);
      setActivity([]);
      setStreamingText('');

      const controller = new AbortController();
      abortRef.current = controller;
      const base = agentBaseUrl();
      const startUrl = `${base}/sessions/${sessionId}/agent/runs`;
      const resumeUrl = (id: string) =>
        `${base}/sessions/${sessionId}/agent/runs/${id}/resume`;
      let token = await resolveToken();

      // body: message 가 null 이면 no-message reconnect(끊긴 런 drain).
      const bodyFor = (msg: string | null): string =>
        JSON.stringify({
          schema_version: '1.0.0',
          ...(msg !== null ? { message: { role: 'user', content: msg } } : {}),
        });
      const makeInit = (tok: string, payload: string): RequestInit => ({
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
          Authorization: `Bearer ${tok}`,
        },
        body: payload,
        signal: controller.signal,
      });
      // 만료 토큰이면 1회 갱신 후 재시도(직접 fetch 라 apiClient 401 경로를 못 탐).
      const fetchAuthed = async (url: string, payload: string): Promise<Response> => {
        const res = await fetch(url, makeInit(token, payload));
        if (res.status !== 401) return res;
        const refreshed = await refreshToken();
        if (!refreshed) return res;
        token = refreshed;
        return fetch(url, makeInit(token, payload));
      };

      // 한 SSE 응답 본문을 소비하며 채팅 상태를 갱신하고 종료 run_status 를 돌려준다.
      const pump = async (
        res: Response,
      ): Promise<{ runStatus: string | null; recoveredId: string | null }> => {
        let assembled = '';
        let runStatus: string | null = null;
        let recoveredId: string | null = null;
        const reader = res.body!.getReader();
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
              // write_todos 가 보낸 최신 전체 계획이면 plan 을 그대로 교체한다(누적 아님).
              // write_todos 는 tool-labels 에서 hidden 이라 활동 타임라인엔 안 뜨고,
              // 대신 PlanPanel 로 보여 준다. 빈 배열은 의미 없는 갱신이라 무시한다.
              if (Array.isArray(ev.todos) && ev.todos.length > 0) {
                setPlan(ev.todos as PlanTodo[]);
              }
              // 숨김 도구(set_completion_decision, write_todos 등)는 활동 UI 에 노출하지 않는다.
              if (!toolDisplay(ev.tool_name).hidden) {
                const text = toolStepText(ev.tool_name, ev.status, ev.summary);
                setToolActivity(text);
                setActivity((prev) => {
                  if (ev.status === 'started') {
                    // 같은 도구의 진행 중 단계가 이미 있으면 갱신, 없으면 push.
                    const existing = prev.find(
                      (s) => s.toolName === ev.tool_name && s.status === 'started',
                    );
                    const step: ToolActivityStep = {
                      id: existing ? existing.id : uid(),
                      toolName: ev.tool_name,
                      status: 'started',
                      text,
                    };
                    if (existing) {
                      return prev.map((s) => (s === existing ? step : s));
                    }
                    return [...prev, step];
                  }
                  // succeeded/failed: 같은 도구의 마지막 started 를 종료 상태로 갱신.
                  let target: ToolActivityStep | undefined;
                  for (let i = prev.length - 1; i >= 0; i -= 1) {
                    const s = prev[i];
                    if (s && s.toolName === ev.tool_name && s.status === 'started') {
                      target = s;
                      break;
                    }
                  }
                  if (target) {
                    const updated = target;
                    return prev.map((s) =>
                      s === updated ? { ...updated, status: ev.status, text } : s,
                    );
                  }
                  // 대응하는 started 가 없으면 종료 단계를 그대로 추가.
                  return [
                    ...prev,
                    { id: uid(), toolName: ev.tool_name, status: ev.status, text },
                  ];
                });
              }
            } else if (ev.type === 'message') {
              // 방어적 차단: assistant 메시지만 채팅 버블로 만든다. tool/system role 은
              // 내부 메시지라 raw 누출을 막기 위해 버블화하지 않는다(#raw-leak-guard).
              if (ev.role !== 'assistant') continue;
              const dynamics = (ev.ui_components ?? []) as A2uiComponent[];
              const msgId = ev.message_id ?? uid();
              // resume 재연결 시 서버가 이미 영속된 메시지를 다시 보낼 수 있다 —
              // message_id 로 dedupe 한다(#replay-on-resume).
              setMessages((prev) =>
                prev.some((m) => m.id === msgId)
                  ? prev
                  : [
                      ...prev,
                      {
                        id: msgId,
                        role: 'assistant',
                        content: ev.content,
                        createdAt: new Date().toISOString(),
                        dynamics,
                      },
                    ],
              );
              assembled = '';
              setStreamingText('');
            } else if (ev.type === 'error') {
              setError(ev.message);
              if (ev.error_code === 'AGENT_RUN_ALREADY_ACTIVE' && ev.active_run_id) {
                recoveredId = ev.active_run_id;
                setResumeId(ev.active_run_id);
                resumeModeRef.current = modeForStatus(ev.active_run_status ?? '');
              }
            } else if (ev.type === 'done') {
              runStatus = ev.run_status;
            }
          }
        }
        return { runStatus, recoveredId };
      };

      try {
        // --- 0단계: 직전이 drop(reconnect)이면, 새 입력 전에 no-message reconnect 로
        // 끊긴 런을 먼저 drain 한다 — 서버 reconnect 경로가 message 를 무시해 새 입력이
        // 유실되는 것을 막는다(#reconnect). drain 후 새 입력은 1단계에서 새 턴/응답으로.
        const dropRunId = resumableRunIdRef.current;
        if (dropRunId && resumeModeRef.current === 'reconnect') {
          const rc = await fetchAuthed(resumeUrl(dropRunId), bodyFor(null));
          if (rc.ok && rc.body) {
            const { runStatus } = await pump(rc);
            if (runStatus === 'awaiting_input' || runStatus === 'interrupted') {
              resumeModeRef.current = modeForStatus(runStatus);
            } else {
              setResumeId(null);
              resumeModeRef.current = null;
            }
          }
        }

        // --- 1단계: 사용자가 입력한 text 를 전송한다(awaiting_input 응답이면 /resume,
        // 아니면 새 런 시작). 낙관적 user 버블을 여기서 추가한다.
        setMessages((prev) => [
          ...prev,
          {
            id: uid(),
            role: 'user',
            content: text,
            createdAt: new Date().toISOString(),
          },
        ]);

        const replyId =
          resumeModeRef.current === 'reply' ? resumableRunIdRef.current : null;
        let res = await fetchAuthed(
          replyId ? resumeUrl(replyId) : startUrl,
          bodyFor(text),
        );

        // resume(reply) 실패 시 런이 terminal/missing 이면 id 를 비우고 새 런으로 1회 재시도.
        if (
          (!res.ok || !res.body) &&
          replyId &&
          (await isRunTerminalOrMissing(base, sessionId, replyId, token))
        ) {
          setResumeId(null);
          resumeModeRef.current = null;
          res = await fetchAuthed(startUrl, bodyFor(text));
        }

        // 새 런 시작이 409(이미 활성 런)면 active_run_id 로 복구한다. resumable 이면
        // 같은 메시지로 /resume 즉시 재시도(방금 추가한 사용자 메시지 유실 방지).
        if (res.status === 409) {
          const active = await readActiveRun(res);
          if (active) {
            setResumeId(active.id);
            resumeModeRef.current = modeForStatus(active.status);
            if (active.status === 'awaiting_input' || active.status === 'interrupted') {
              res = await fetchAuthed(resumeUrl(active.id), bodyFor(text));
            }
          }
        }

        if (!res.ok || !res.body) {
          throw new Error(`에이전트 요청에 실패했습니다 (HTTP ${res.status}).`);
        }
        setResumeId(res.headers.get('X-Agent-Run-Id') ?? resumableRunIdRef.current);

        const { runStatus, recoveredId } = await pump(res);
        setToolActivity(null);
        setStreamingText('');
        if (runStatus === 'awaiting_input') {
          resumeModeRef.current = 'reply';
          setStatus('done');
        } else if (runStatus === 'interrupted') {
          resumeModeRef.current = 'reconnect';
          setStatus('done');
        } else if (runStatus === 'succeeded' || runStatus === 'cancelled') {
          setResumeId(null);
          resumeModeRef.current = null;
          setStatus('done');
        } else if (runStatus === 'failed') {
          // conflict 로 활성 런 id 를 복구한 경우엔 비우지 않는다(다음 send 가 resume).
          if (!recoveredId) {
            setResumeId(null);
            resumeModeRef.current = null;
          }
          setStatus('error');
        } else {
          // done 프레임 없이 스트림이 끊김(네트워크/프록시) — reconnect 로 표시해 다음
          // send 가 no-message drain 후 이어가도록 한다(#done-required).
          resumeModeRef.current = 'reconnect';
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
        // 스트림이 끝나면 남은 'started' 단계의 스피너를 멈춘다 — 종료(succeeded)로
        // 마무리해 완료 후에도 스피너가 계속 도는 것처럼 보이는 문제를 막는다.
        setActivity((prev) =>
          prev.some((s) => s.status === 'started')
            ? prev.map((s) =>
                s.status === 'started'
                  ? { ...s, status: 'succeeded', text: toolStepText(s.toolName, 'succeeded') }
                  : s,
              )
            : prev,
        );
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

  return { messages, streamingText, toolActivity, activity, plan, status, error, send, stop };
}

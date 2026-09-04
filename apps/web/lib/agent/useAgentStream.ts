'use client';

/**
 * 에이전트 SSE 스트림 훅 (CMP-DIRECT).
 *
 * 브라우저가 백엔드(api.jippin.ai)로 **직접** `fetch`+ReadableStream POST 한다
 * (Vercel 우회). EventSource 는 Authorization 헤더를 실을 수 없어 쓰지 않는다.
 * token/tool_step/state_change/message/error/done 이벤트를 받아 채팅 상태로 환원한다.
 *
 * 세션당 활성 런은 1개다(서버 409 AGENT_RUN_ALREADY_ACTIVE). 새로고침·다른 탭 등으로 이
 * 훅이 모르는 런이 살아 있을 수 있으므로, 마운트 시 활성 런을 확인해 재부착하고
 * (#reattach-active-run) 전송이 409 를 받으면 그 런이 끝나길 기다렸다가 이어 보낸다
 * (#wait-active-run) — 도면 업로드 카드가 분석 중에 "분석해 주세요" 를 보내다 HTTP 409 로
 * 실패하던 경로(2026-09-03 운영 재현)의 수정이다.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import type { A2uiComponent, ChatActivityStep, ChatMessage } from '@/components/a2ui';
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

// 런 한 건의 현재 상태를 조회한다. 'missing'=404(없음/타세션), null=일시 오류(호출자가
// 보수적으로 다룬다). resume 실패 뒤 id 를 비워도 되는지, 활성 런이 끝났는지 판정에 쓴다.
async function fetchRunStatus(
  base: string,
  sessionId: string,
  runId: string,
  token: string,
): Promise<string | 'missing' | null> {
  try {
    const res = await fetch(`${base}/sessions/${sessionId}/agent/runs/${runId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.status === 404) return 'missing';
    if (!res.ok) return null;
    const data = (await res.json()) as { status?: string };
    return typeof data?.status === 'string' ? data.status : null;
  } catch {
    return null;
  }
}

const TERMINAL_RUN_STATUSES = ['succeeded', 'failed', 'cancelled'];
// 재개(/resume)도 재스트림도 안 되는 상태 — 끝나길 기다리는 수밖에 없다(#wait-active-run).
const ACTIVE_RUN_STATUSES = ['pending', 'running'];
// 기다리는 동안 활동 타임라인에 올리는 클라이언트 전용 의사 단계(문구는 tool-labels).
const WAIT_ACTIVE_RUN_STEP = 'wait_active_run';
const DEFAULT_ACTIVE_RUN_POLL_MS = 2000;
// 서버 wallclock(agent_run_wallclock_timeout_seconds=1200s)보다 짧게 — 그 뒤엔 포기하고
// 안내한다(정상 도면 분석은 1~2분).
const DEFAULT_ACTIVE_RUN_MAX_WAIT_MS = 10 * 60 * 1000;

// 세션의 활성 런(pending/running/awaiting_input/interrupted)을 조회한다. 없으면(404) null.
async function fetchActiveRun(
  base: string,
  sessionId: string,
  token: string,
): Promise<{ id: string; status: string } | null> {
  try {
    const res = await fetch(`${base}/sessions/${sessionId}/agent/runs/active`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { id?: string; status?: string };
    if (typeof data?.id !== 'string' || typeof data?.status !== 'string') return null;
    return { id: data.id, status: data.status };
  } catch {
    return null;
  }
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) {
      resolve();
      return;
    }
    const onAbort = () => {
      clearTimeout(timer);
      resolve();
    };
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    signal.addEventListener('abort', onAbort, { once: true });
  });
}

function abortError(): Error {
  const err = new Error('aborted');
  err.name = 'AbortError';
  return err;
}

// 활성 런(pending/running)이 끝나기를 폴링으로 기다린다(#wait-active-run). 서버는 세션당
// 활성 런 1개만 허용하고(409 AGENT_RUN_ALREADY_ACTIVE) 진행 중 런의 스트림을 다시 붙일
// 경로가 없다 — 상태만 폴링하다가 활성 상태를 벗어나면(awaiting_input/interrupted/
// terminal/missing) 그 상태를 돌려준다. 상한 초과면 null, 중단(signal)되면 AbortError.
async function waitForRunToSettle(
  base: string,
  sessionId: string,
  runId: string,
  getToken: () => Promise<string>,
  signal: AbortSignal,
  pollMs: number,
  maxWaitMs: number,
): Promise<string | 'missing' | null> {
  const deadline = Date.now() + maxWaitMs;
  while (Date.now() < deadline) {
    await sleep(pollMs, signal);
    if (signal.aborted) throw abortError();
    const status = await fetchRunStatus(base, sessionId, runId, await getToken());
    if (status === null) continue; // 일시 오류 — 다음 폴링에서 다시
    if (!ACTIVE_RUN_STATUSES.includes(status)) return status;
  }
  return null;
}

type HistoryItem = {
  id: string;
  role: string;
  content: string;
  ui_components?: Record<string, unknown>[];
  created_at?: string;
};

// 영속된 transcript(`GET /agent/messages`)를 ChatMessage 로 변환한다. 실패는 빈 배열.
async function fetchHistory(
  base: string,
  sessionId: string,
  token: string,
): Promise<ChatMessage[]> {
  try {
    const res = await fetch(`${base}/sessions/${sessionId}/agent/messages`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return [];
    const data = (await res.json()) as { messages?: HistoryItem[] };
    return (data?.messages ?? []).map((m) => ({
      id: String(m.id),
      role: m.role === 'assistant' ? 'assistant' : 'user',
      content: typeof m.content === 'string' ? m.content : '',
      createdAt: m.created_at ?? new Date().toISOString(),
      // A2UI 컴포넌트는 raw 그대로 보존한다 — A2uiSurface 가 json-render spec /
      // 레거시 {kind,payload} 양쪽을 해석한다.
      dynamics:
        m.role === 'assistant' ? ((m.ui_components ?? []) as A2uiComponent[]) : undefined,
    }));
  } catch {
    return [];
  }
}

// 이미 있는 메시지는 두고 히스토리의 새 메시지만 끼워 넣는다. beforeId(방금 붙인 낙관적
// 사용자 말풍선)가 있으면 그 앞에 — 기다린 런의 답은 시간상 내 메시지보다 먼저다.
function mergeHistory(
  prev: ChatMessage[],
  history: ChatMessage[],
  beforeId?: string,
): ChatMessage[] {
  const known = new Set(prev.map((m) => m.id));
  const missing = history.filter((m) => !known.has(m.id));
  if (missing.length === 0) return prev;
  const at = beforeId ? prev.findIndex((m) => m.id === beforeId) : -1;
  if (at < 0) return [...prev, ...missing];
  return [...prev.slice(0, at), ...missing, ...prev.slice(at)];
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

export interface UseAgentStreamOptions {
  /** 활성 런 상태 폴링 간격(ms). 테스트에서 줄인다. */
  activeRunPollMs?: number;
  /** 활성 런을 기다리는 상한(ms). 서버 wallclock 보다 짧게. */
  activeRunMaxWaitMs?: number;
}

export function useAgentStream(
  sessionId: string,
  options: UseAgentStreamOptions = {},
): UseAgentStream {
  const pollMs = options.activeRunPollMs ?? DEFAULT_ACTIVE_RUN_POLL_MS;
  const maxWaitMs = options.activeRunMaxWaitMs ?? DEFAULT_ACTIVE_RUN_MAX_WAIT_MS;
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingText, setStreamingText] = useState('');
  const [toolActivity, setToolActivity] = useState<string | null>(null);
  const [activity, setActivity] = useState<ToolActivityStep[]>([]);
  // activity state 의 최신 스냅샷 미러. message 커밋 시 그 턴의 활동을 메시지에 귀속
  // 시키려면(아바타 중복·순서 문제 해소) 함수형 updater 밖에서 현재값을 읽어야 한다.
  const activityRef = useRef<ToolActivityStep[]>([]);
  const setActivitySynced = useCallback((next: ToolActivityStep[]) => {
    activityRef.current = next;
    setActivity(next);
  }, []);
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

  const setResumeId = useCallback(
    (id: string | null) => {
      resumableRunIdRef.current = id;
      saveResumeId(sessionId, id);
    },
    [sessionId],
  );

  // 활성 런을 기다리는 동안 보여 줄 활동 한 줄(스피너) — 사용자가 "왜 멈춰 있는지" 알게
  // 한다. 기다림이 끝나면 지운다(성공 체크로 남기지 않음).
  const showWaiting = useCallback((): string => {
    const step: ToolActivityStep = {
      id: uid(),
      toolName: WAIT_ACTIVE_RUN_STEP,
      status: 'started',
      text: toolStepText(WAIT_ACTIVE_RUN_STEP, 'started'),
    };
    setToolActivity(step.text);
    setActivitySynced([...activityRef.current, step]);
    return step.id;
  }, [setActivitySynced]);
  const clearWaiting = useCallback(
    (stepId: string) => {
      setActivitySynced(activityRef.current.filter((s) => s.id !== stepId));
      setToolActivity(null);
    },
    [setActivitySynced],
  );

  // resumable run id 를 복원하고, 언마운트/세션변경 시 진행 중 스트림을 중단한다 —
  // 옛 스트림이 프레임을 계속 흘리는 누수를 막는다(#stale-stream-leak). 메시지 등
  // useState 리셋은 부모가 AgentChat 을 sessionId 로 key 해 remount 시키는 것으로
  // 처리한다(effect 안 setState 회피 — 아래 setState 는 모두 await 이후).
  useEffect(() => {
    // 빈 sessionId(=compose 단계) 가드: 히스토리 로드/resume 복원을 no-op 으로 둔다.
    if (!sessionId) return;
    resumableRunIdRef.current = loadResumeId(sessionId);
    const controller = new AbortController();
    abortRef.current = controller;
    let ignore = false;
    void (async () => {
      try {
        const base = agentBaseUrl();
        const token = await resolveToken();
        // 마운트/새로고침 시 영속된 transcript 를 복원한다 — 완료된 런은 resume 스트림이
        // 없어 SSE 로 다시 못 받으므로(#load-history-on-mount). 라이브 메시지가 이미 있으면
        // 덮어쓰지 않는다.
        const history = await fetchHistory(base, sessionId, token);
        if (ignore) return;
        if (history.length > 0) setMessages((prev) => (prev.length > 0 ? prev : history));

        // 활성 런 재부착(#reattach-active-run). 새로고침/다른 탭으로 연 화면은 서버에 아직
        // 살아 있는 런을 모른다 — 그대로 두면 다음 전송(도면 카드의 "분석해 주세요" 포함)이
        // 새 런을 시작하다 409 AGENT_RUN_ALREADY_ACTIVE 로 실패했다. resumable 이면 다음
        // 전송이 바로 /resume 로 가게 refs 만 맞추고, pending/running 이면 끝날 때까지
        // busy(streaming)로 두어 입력·카드 액션을 잠갔다가 그 런이 남긴 메시지를 합친다.
        const active = await fetchActiveRun(base, sessionId, token);
        if (ignore || !active) return;
        if (!ACTIVE_RUN_STATUSES.includes(active.status)) {
          setResumeId(active.id);
          resumeModeRef.current = modeForStatus(active.status);
          return;
        }
        streamingRef.current = true;
        setStatus('streaming');
        const waitId = showWaiting();
        let settled: string | 'missing' | null = null;
        try {
          settled = await waitForRunToSettle(
            base,
            sessionId,
            active.id,
            resolveToken,
            controller.signal,
            pollMs,
            maxWaitMs,
          );
        } catch {
          settled = null; // AbortError(언마운트/stop) — ignore 가드로 빠지거나 idle 로 복귀
        }
        if (ignore) return;
        streamingRef.current = false;
        clearWaiting(waitId);
        const later = await fetchHistory(base, sessionId, await resolveToken());
        if (ignore) return;
        if (later.length > 0) setMessages((prev) => mergeHistory(prev, later));
        if (
          settled === null ||
          settled === 'missing' ||
          TERMINAL_RUN_STATUSES.includes(settled)
        ) {
          // 끝났거나(terminal/없음) 상한 초과·중단 — id 를 비운다. 아직 살아 있었다면 다음
          // 전송의 409 복구(#wait-active-run)가 다시 기다린다.
          setResumeId(null);
          resumeModeRef.current = null;
        } else {
          setResumeId(active.id);
          resumeModeRef.current = modeForStatus(settled);
        }
        setStatus('idle');
      } catch {
        /* 히스토리 로드/재부착 실패 — 빈 채로 시작 */
      }
    })();
    return () => {
      ignore = true;
      controller.abort();
      abortRef.current?.abort();
      abortRef.current = null;
      streamingRef.current = false;
    };
  }, [sessionId, setResumeId, showWaiting, clearWaiting, pollMs, maxWaitMs]);

  const send = useCallback(
    async (content: string) => {
      const text = content.trim();
      // 빈 sessionId(compose 단계)면 send 를 no-op 으로 둔다(SessionChat 이 세션 생성 후 재마운트).
      if (!text || !sessionId || streamingRef.current) return;

      streamingRef.current = true;
      setError(null);
      setStatus('streaming');
      setToolActivity(null);
      setActivitySynced([]);
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
                const prev = activityRef.current;
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
                  setActivitySynced(
                    existing
                      ? prev.map((s) => (s === existing ? step : s))
                      : [...prev, step],
                  );
                } else {
                  // succeeded/failed: 같은 도구의 마지막 started 를 종료 상태로 갱신.
                  let target: ToolActivityStep | undefined;
                  for (let i = prev.length - 1; i >= 0; i -= 1) {
                    const s = prev[i];
                    if (s && s.toolName === ev.tool_name && s.status === 'started') {
                      target = s;
                      break;
                    }
                  }
                  setActivitySynced(
                    target
                      ? prev.map((s) =>
                          s === target ? { ...target, status: ev.status, text } : s,
                        )
                      : [
                          ...prev,
                          { id: uid(), toolName: ev.tool_name, status: ev.status, text },
                        ],
                  );
                }
              }
            } else if (ev.type === 'message') {
              // 방어적 차단: assistant 메시지만 채팅 버블로 만든다. tool/system role 은
              // 내부 메시지라 raw 누출을 막기 위해 버블화하지 않는다(#raw-leak-guard).
              if (ev.role !== 'assistant') continue;
              const dynamics = (ev.ui_components ?? []) as A2uiComponent[];
              const msgId = ev.message_id ?? uid();
              // 이 턴의 도구 활동을 메시지에 귀속시킨다 — 한 아바타 아래 [활동 → 본문]
              // 순서로 렌더되도록(도구가 본문보다 먼저 실행되므로). 귀속 후 임시 활동은
              // 비워, 다음 턴 도구가 새로 쌓이고 진행 중 블록이 중복 표시되지 않게 한다.
              const turnActivity: ChatActivityStep[] = activityRef.current.map((s) => ({
                id: s.id,
                status: s.status,
                text: s.text,
              }));
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
                        activity: turnActivity.length > 0 ? turnActivity : undefined,
                      },
                    ],
              );
              setActivitySynced([]);
              setToolActivity(null);
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

      // 런이 에러/중단으로 끝났는지 — finally 에서 남은 'started' 단계를 succeeded 로 둘지
      // failed 로 둘지 가른다. 성공/대기/정상중단은 false 유지(#orphan-tool-step).
      let errored = false;
      try {
        // 사용자 입력 1건을 서버에 전달한다 — 직전 런 상태(refs)에 따라 (0) drop 된 런은
        // no-message reconnect 로 먼저 drain 하고, (1) awaiting_input 이면 /resume 로 답을,
        // 아니면 새 런을 시작한다. 409 복구 뒤 refs 를 맞춰 다시 부를 수 있게 함수로 둔다.
        const deliver = async (): Promise<Response> => {
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

          // --- 1단계: text 를 전송한다(awaiting_input 응답이면 /resume, 아니면 새 런 시작).
          const replyId =
            resumeModeRef.current === 'reply' ? resumableRunIdRef.current : null;
          let res = await fetchAuthed(
            replyId ? resumeUrl(replyId) : startUrl,
            bodyFor(text),
          );

          // resume(reply) 실패 시 런이 terminal/missing 이면 id 를 비우고 새 런으로 1회 재시도.
          if ((!res.ok || !res.body) && replyId) {
            const probe = await fetchRunStatus(base, sessionId, replyId, token);
            if (
              probe === 'missing' ||
              (probe !== null && TERMINAL_RUN_STATUSES.includes(probe))
            ) {
              setResumeId(null);
              resumeModeRef.current = null;
              res = await fetchAuthed(startUrl, bodyFor(text));
            }
          }
          return res;
        };

        // 낙관적 user 버블을 먼저 추가한다(전송 실패해도 입력이 사라지지 않게).
        const userMessageId = uid();
        setMessages((prev) => [
          ...prev,
          {
            id: userMessageId,
            role: 'user',
            content: text,
            createdAt: new Date().toISOString(),
          },
        ]);

        let res = await deliver();

        // 409 = 이 세션에 이미 활성 런이 있다(새 런 시작: AGENT_RUN_ALREADY_ACTIVE — detail 에
        // active_run_id/status / resume: AGENT_RUN_NOT_RESUMABLE — 다른 탭이 먼저 이어받아
        // running). 활성 런을 파악해 복구한다(#active-run-recovery).
        if (res.status === 409) {
          const active =
            (await readActiveRun(res)) ?? (await fetchActiveRun(base, sessionId, token));
          if (active && ACTIVE_RUN_STATUSES.includes(active.status)) {
            // pending/running: 재개도 재스트림도 안 되는 상태 — 새로고침·다른 탭 전의 분석이
            // 아직 도는 중에(예: 도면 업로드 카드의 "분석해 주세요") 전송한 경우다. 끝나길
            // 기다렸다가 그 런의 답을 내 말풍선 앞에 합치고 이어서 보낸다(#wait-active-run).
            // 예전엔 여기서 "HTTP 409" 로 실패해 사용자가 같은 도면을 다시 올려야 했다.
            const waitId = showWaiting();
            let settled: string | 'missing' | null;
            try {
              settled = await waitForRunToSettle(
                base,
                sessionId,
                active.id,
                resolveToken,
                controller.signal,
                pollMs,
                maxWaitMs,
              );
            } finally {
              clearWaiting(waitId);
            }
            if (settled === null) {
              throw new Error('이전 요청을 아직 처리하고 있어요. 잠시 후 다시 보내 주세요.');
            }
            token = await resolveToken();
            const history = await fetchHistory(base, sessionId, token);
            if (history.length > 0) {
              setMessages((prev) => mergeHistory(prev, history, userMessageId));
            }
            if (settled === 'missing' || TERMINAL_RUN_STATUSES.includes(settled)) {
              setResumeId(null);
              resumeModeRef.current = null;
            } else {
              setResumeId(active.id);
              resumeModeRef.current = modeForStatus(settled);
            }
            res = await deliver();
          } else if (active) {
            // resumable(awaiting_input/interrupted) — refs 를 맞추고 같은 메시지를 다시 전달한다
            // (방금 추가한 사용자 메시지 유실 방지). interrupted 는 deliver 가 먼저 no-message
            // 로 drain 한다 — 서버 재연결 경로가 message 를 무시하므로 바로 /resume 에 실어
            // 보내면 유실된다.
            setResumeId(active.id);
            resumeModeRef.current = modeForStatus(active.status);
            res = await deliver();
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
          errored = true;
          setStatus('error');
        } else {
          // done 프레임 없이 스트림이 끊김(네트워크/프록시) — reconnect 로 표시해 다음
          // send 가 no-message drain 후 이어가도록 한다(#done-required).
          resumeModeRef.current = 'reconnect';
          setError((prev) => prev ?? '연결이 끊겼습니다. 다시 보내면 이어서 진행합니다.');
          errored = true;
          setStatus('error');
        }
      } catch (err) {
        errored = true;
        if ((err as Error)?.name === 'AbortError') {
          setStatus('idle');
          return;
        }
        setError((err as Error)?.message ?? '알 수 없는 오류가 발생했습니다.');
        setStatus('error');
      } finally {
        streamingRef.current = false;
        abortRef.current = null;
        // 스트림이 끝나면 남은 'started' 단계의 스피너를 멈춘다. 단 **성공으로 끝났을 때만
        // succeeded** 로 마무리하고, 에러/중단(errored)이면 failed 로 둔다 — 실패한 런 옆에
        // "분석 완료" 체크가 뜨던 문제를 막는다(#orphan-tool-step).
        const remaining = activityRef.current;
        if (remaining.some((s) => s.status === 'started')) {
          const end: ToolStepStatusValue = errored ? 'failed' : 'succeeded';
          setActivitySynced(
            remaining.map((s) =>
              s.status === 'started'
                ? { ...s, status: end, text: toolStepText(s.toolName, end) }
                : s,
            ),
          );
        }
      }
    },
    [sessionId, setResumeId, setActivitySynced, showWaiting, clearWaiting, pollMs, maxWaitMs],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    streamingRef.current = false;
    setToolActivity(null);
    setStatus('idle');
  }, []);

  return { messages, streamingText, toolActivity, activity, plan, status, error, send, stop };
}

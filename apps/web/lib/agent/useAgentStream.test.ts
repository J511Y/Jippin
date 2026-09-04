/**
 * useAgentStream 활성 런 복구 테스트 (#wait-active-run, #reattach-active-run).
 *
 * 서버는 세션당 활성 런 1개만 허용한다(409 AGENT_RUN_ALREADY_ACTIVE). 도면 업로드 카드가
 * 분석 중에 "분석해 주세요" 를 보내다 HTTP 409 로 실패하던 경로가 폴링 대기 후 이어
 * 보내지는지, 마운트 시 활성 런에 재부착되는지 fetch 스텁으로 검증한다.
 */
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: 'tok' } } }),
      refreshSession: async () => ({ data: { session: null } })
    }
  })
}));
vi.mock('@/lib/leads/ensure-anonymous-session', () => ({
  ensureAnonymousSession: vi.fn(async () => ({ userId: 'u', token: 'tok' }))
}));
vi.mock('@/lib/api-base-url', () => ({ apiBaseUrl: () => 'http://api.test' }));

import { useAgentStream } from './useAgentStream';

const BASE = 'http://api.test/sessions/s1/agent';

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' }
  });
}

function sse(frames: Array<Record<string, unknown>>, runId: string): Response {
  const body = frames
    .map((frame) => `event: ${String(frame.type)}\ndata: ${JSON.stringify(frame)}\n\n`)
    .join('');
  return new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream', 'X-Agent-Run-Id': runId }
  });
}

const reply = (id: string, content: string, runId: string) =>
  sse(
    [
      { type: 'message', seq: 1, role: 'assistant', content, message_id: id },
      { type: 'done', seq: 2, run_status: 'succeeded' }
    ],
    runId
  );

type Call = { method: string; url: string; body: string | null };

/** URL+메서드별 호출 횟수(n, 1부터)를 넘겨 응답을 고르는 fetch 스텁. */
function installFetch(handler: (method: string, url: string, n: number) => Response) {
  const calls: Call[] = [];
  const counts = new Map<string, number>();
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? 'GET').toUpperCase();
      const key = `${method} ${url}`;
      const n = (counts.get(key) ?? 0) + 1;
      counts.set(key, n);
      calls.push({ method, url, body: typeof init?.body === 'string' ? init.body : null });
      return handler(method, url, n);
    })
  );
  return calls;
}

const notActive = () => json({ error: { code: 'AGENT_RUN_NOT_ACTIVE' } }, 404);
const unexpected = (method: string, url: string): never => {
  throw new Error(`unexpected ${method} ${url}`);
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
});

describe('useAgentStream 전송 중 409 복구', () => {
  it('새 런 시작이 409(running)면 끝날 때까지 기다렸다가 그 답을 합치고 이어서 보낸다', async () => {
    const calls = installFetch((method, url, n) => {
      if (url === `${BASE}/messages`) {
        // 1회차=마운트 히스토리(비어 있음), 2회차=대기 후 합치기(기다린 런의 답).
        return json({
          messages:
            n === 1
              ? []
              : [
                  {
                    id: 'm-prev',
                    role: 'assistant',
                    content: '이전 도면 분석 결과예요',
                    ui_components: []
                  }
                ]
        });
      }
      if (url === `${BASE}/runs/active`) return notActive();
      if (url === `${BASE}/runs` && method === 'POST') {
        if (n === 1) {
          return json(
            {
              error: { code: 'AGENT_RUN_ALREADY_ACTIVE', message: 'busy' },
              detail: { active_run_id: 'run-a', status: 'running' }
            },
            409
          );
        }
        return reply('m-new', '이어서 분석할게요', 'run-b');
      }
      if (url === `${BASE}/runs/run-a`) {
        return json({ id: 'run-a', status: n < 3 ? 'running' : 'succeeded' });
      }
      return unexpected(method, url);
    });

    const { result } = renderHook(() => useAgentStream('s1', { activeRunPollMs: 5 }));
    await waitFor(() => expect(calls.some((c) => c.url === `${BASE}/runs/active`)).toBe(true));

    await act(async () => {
      await result.current.send('도면을 첨부했어요. 분석해 주세요.');
    });

    expect(result.current.status).toBe('done');
    expect(result.current.error).toBeNull();
    expect(calls.filter((c) => c.method === 'POST' && c.url === `${BASE}/runs`)).toHaveLength(2);
    expect(calls.filter((c) => c.url === `${BASE}/runs/run-a`).length).toBeGreaterThanOrEqual(3);
    // 기다린 런의 답 → 내 메시지 → 새 런의 답 순서.
    expect(result.current.messages.map((m) => [m.role, m.content])).toEqual([
      ['assistant', '이전 도면 분석 결과예요'],
      ['user', '도면을 첨부했어요. 분석해 주세요.'],
      ['assistant', '이어서 분석할게요']
    ]);
    // 대기 표시(활동 단계)는 끝나면 지워진다.
    expect(result.current.activity).toEqual([]);
  });

  it('409 활성 런이 awaiting_input 이면 같은 메시지를 /resume 로 보낸다', async () => {
    const calls = installFetch((method, url, n) => {
      if (url === `${BASE}/messages`) return json({ messages: [] });
      if (url === `${BASE}/runs/active`) return notActive();
      if (url === `${BASE}/runs` && method === 'POST' && n === 1) {
        return json(
          {
            error: { code: 'AGENT_RUN_ALREADY_ACTIVE' },
            detail: { active_run_id: 'run-w', status: 'awaiting_input' }
          },
          409
        );
      }
      if (url === `${BASE}/runs/run-w/resume` && method === 'POST') {
        return reply('m1', '네, 이어갈게요', 'run-w');
      }
      return unexpected(method, url);
    });

    const { result } = renderHook(() => useAgentStream('s1', { activeRunPollMs: 5 }));
    await waitFor(() => expect(calls.some((c) => c.url === `${BASE}/runs/active`)).toBe(true));
    await act(async () => {
      await result.current.send('답변이에요');
    });

    expect(result.current.status).toBe('done');
    const resume = calls.find((c) => c.url === `${BASE}/runs/run-w/resume`);
    expect(resume?.body).toContain('답변이에요');
    expect(result.current.messages.map((m) => m.content)).toEqual(['답변이에요', '네, 이어갈게요']);
  });
});

describe('useAgentStream 마운트 재부착', () => {
  it('활성 런이 awaiting_input 이면 다음 전송이 409 왕복 없이 바로 /resume 로 간다', async () => {
    const calls = installFetch((method, url) => {
      if (url === `${BASE}/messages`) return json({ messages: [] });
      if (url === `${BASE}/runs/active`) return json({ id: 'run-w', status: 'awaiting_input' });
      if (url === `${BASE}/runs/run-w/resume` && method === 'POST') {
        return reply('m1', '이어갈게요', 'run-w');
      }
      return unexpected(method, url);
    });

    const { result } = renderHook(() => useAgentStream('s1', { activeRunPollMs: 5 }));
    await waitFor(() => expect(calls.some((c) => c.url === `${BASE}/runs/active`)).toBe(true));
    await act(async () => {
      await result.current.send('추가 답변');
    });

    expect(calls.filter((c) => c.method === 'POST' && c.url === `${BASE}/runs`)).toHaveLength(0);
    expect(calls.some((c) => c.url === `${BASE}/runs/run-w/resume`)).toBe(true);
    expect(result.current.status).toBe('done');
  });

  it('활성 런이 running 이면 busy 로 기다렸다가 그 런의 메시지를 합치고 idle 로 돌아온다', async () => {
    const calls = installFetch((method, url, n) => {
      if (url === `${BASE}/messages`) {
        return json({
          messages:
            n === 1
              ? []
              : [{ id: 'm-late', role: 'assistant', content: '분석을 마쳤어요', ui_components: [] }]
        });
      }
      if (url === `${BASE}/runs/active`) return json({ id: 'run-r', status: 'running' });
      if (url === `${BASE}/runs/run-r`) {
        return json({ id: 'run-r', status: n < 12 ? 'running' : 'succeeded' });
      }
      if (url === `${BASE}/runs` && method === 'POST') {
        return reply('m2', '다음 질문에 답할게요', 'run-n');
      }
      return unexpected(method, url);
    });

    const { result } = renderHook(() => useAgentStream('s1', { activeRunPollMs: 5 }));
    // 기다리는 동안은 streaming(busy) + 대기 문구.
    await waitFor(() => expect(result.current.status).toBe('streaming'), { interval: 5 });
    expect(result.current.activity.some((s) => s.text.includes('이전 요청'))).toBe(true);

    await waitFor(() => expect(result.current.status).toBe('idle'), { interval: 5 });
    expect(result.current.activity).toEqual([]);
    expect(result.current.messages.map((m) => m.content)).toEqual(['분석을 마쳤어요']);

    // 끝난 런은 id 를 비우므로 다음 전송은 새 런 시작.
    await act(async () => {
      await result.current.send('다음 질문');
    });
    expect(calls.filter((c) => c.method === 'POST' && c.url === `${BASE}/runs`)).toHaveLength(1);
    expect(result.current.messages.map((m) => m.content)).toEqual([
      '분석을 마쳤어요',
      '다음 질문',
      '다음 질문에 답할게요'
    ]);
  });
});

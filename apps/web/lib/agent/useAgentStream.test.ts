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

/** 프레임을 delayMs 뒤에 흘리는 SSE — 전송이 "진행 중" 인 동안 다른 조회가 끝나는 상황 재현. */
function sseDelayed(frames: Array<Record<string, unknown>>, runId: string, delayMs: number): Response {
  const body = frames
    .map((frame) => `event: ${String(frame.type)}\ndata: ${JSON.stringify(frame)}\n\n`)
    .join('');
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      setTimeout(() => {
        controller.enqueue(new TextEncoder().encode(body));
        controller.close();
      }, delayMs);
    }
  });
  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream', 'X-Agent-Run-Id': runId }
  });
}

describe('useAgentStream 리뷰 회귀 (Codex PR #204)', () => {
  it('스트림 안(HTTP 200)으로 온 AGENT_RUN_ALREADY_ACTIVE 도 대기 후 이어 보낸다', async () => {
    const calls = installFetch((method, url, n) => {
      if (url === `${BASE}/messages`) {
        return json({
          messages:
            n === 1 ? [] : [{ id: 'm-prev', role: 'assistant', content: '이전 답', ui_components: [] }]
        });
      }
      if (url === `${BASE}/runs/active`) return notActive();
      if (url === `${BASE}/runs` && method === 'POST') {
        if (n === 1) {
          return sse(
            [
              {
                type: 'error',
                seq: 1,
                error_code: 'AGENT_RUN_ALREADY_ACTIVE',
                message: '이미 진행 중인 런이 있습니다.',
                recoverable: false,
                active_run_id: 'run-a',
                active_run_status: 'running'
              },
              { type: 'done', seq: 2, run_status: 'failed' }
            ],
            'run-x'
          );
        }
        return reply('m-new', '이어서 답할게요', 'run-b');
      }
      if (url === `${BASE}/runs/run-a`) {
        return json({ id: 'run-a', status: n < 3 ? 'running' : 'succeeded' });
      }
      return unexpected(method, url);
    });

    const { result } = renderHook(() => useAgentStream('s1', { activeRunPollMs: 5 }));
    await waitFor(() => expect(calls.some((c) => c.url === `${BASE}/runs/active`)).toBe(true));
    await act(async () => {
      await result.current.send('질문');
    });

    expect(result.current.status).toBe('done');
    expect(result.current.error).toBeNull();
    expect(calls.filter((c) => c.method === 'POST' && c.url === `${BASE}/runs`)).toHaveLength(2);
    expect(result.current.messages.map((m) => m.content)).toEqual(['이전 답', '질문', '이어서 답할게요']);
  });

  it('409 대기 후 병합할 때 이 탭의 낙관적 user 버블(클라이언트 id)을 중복 삽입하지 않는다', async () => {
    // 1턴 정상 전송 → 2턴 409 대기. 대기 후 히스토리에는 1턴의 영속본(DB id)이 함께 온다.
    const calls = installFetch((method, url, n) => {
      if (url === `${BASE}/messages`) {
        return json({
          messages:
            n === 1
              ? []
              : [
                  { id: 'db-u1', role: 'user', content: '첫 질문', ui_components: [] },
                  { id: 'a1', role: 'assistant', content: '첫 답', ui_components: [] },
                  { id: 'db-u2', role: 'user', content: '다른 탭 질문', ui_components: [] },
                  { id: 'a2', role: 'assistant', content: '다른 탭 답', ui_components: [] }
                ]
        });
      }
      if (url === `${BASE}/runs/active`) return notActive();
      if (url === `${BASE}/runs` && method === 'POST') {
        if (n === 1) return reply('a1', '첫 답', 'run-1');
        if (n === 2) {
          return json(
            { error: { code: 'AGENT_RUN_ALREADY_ACTIVE' }, detail: { active_run_id: 'run-a', status: 'running' } },
            409
          );
        }
        return reply('a3', '둘째 답', 'run-3');
      }
      if (url === `${BASE}/runs/run-a`) return json({ id: 'run-a', status: n < 2 ? 'running' : 'succeeded' });
      return unexpected(method, url);
    });

    const { result } = renderHook(() => useAgentStream('s1', { activeRunPollMs: 5 }));
    await waitFor(() => expect(calls.some((c) => c.url === `${BASE}/runs/active`)).toBe(true));
    await act(async () => {
      await result.current.send('첫 질문');
    });
    await act(async () => {
      await result.current.send('둘째 질문');
    });

    expect(result.current.messages.map((m) => [m.role, m.content])).toEqual([
      ['user', '첫 질문'],
      ['assistant', '첫 답'],
      ['user', '다른 탭 질문'],
      ['assistant', '다른 탭 답'],
      ['user', '둘째 질문'],
      ['assistant', '둘째 답']
    ]);
  });

  it('이 탭의 send 가 이미 돌리는 런은 마운트 재부착이 건드리지 않는다', async () => {
    const calls = installFetch((method, url) => {
      if (url === `${BASE}/messages`) return json({ messages: [] });
      // 마운트 조회 시점엔 이 탭이 방금 시작한 런이 활성 런으로 보인다.
      if (url === `${BASE}/runs/active`) return json({ id: 'run-self', status: 'running' });
      if (url === `${BASE}/runs` && method === 'POST') return sseDelayed([
        { type: 'message', seq: 1, role: 'assistant', content: '첫 답', message_id: 'm1' },
        { type: 'done', seq: 2, run_status: 'succeeded' }
      ], 'run-self', 80);
      return unexpected(method, url);
    });

    const { result } = renderHook(() => useAgentStream('s1', { activeRunPollMs: 5 }));
    // 새 세션의 첫 메시지(pendingFirstMessage)처럼 마운트 조회가 끝나기 전에 보낸다.
    await act(async () => {
      await result.current.send('첫 질문');
    });
    await waitFor(() => expect(calls.some((c) => c.url === `${BASE}/runs/active`)).toBe(true));
    await new Promise((r) => setTimeout(r, 40));

    expect(calls.some((c) => c.url === `${BASE}/runs/run-self`)).toBe(false);
    expect(result.current.status).toBe('done');
    expect(result.current.activity).toEqual([]);
    expect(result.current.messages.map((m) => m.content)).toEqual(['첫 질문', '첫 답']);
  });
});

describe('useAgentStream 리뷰 회귀 2라운드 (Codex PR #204)', () => {
  it('resume 점유 레이스에서 진 쪽(스트림 내 AGENT_RUN_NOT_RESUMABLE)도 활성 런을 조회해 대기 후 이어 보낸다', async () => {
    const calls = installFetch((method, url, n) => {
      if (url === `${BASE}/messages`) {
        return json({
          messages:
            n === 1 ? [] : [{ id: 'm-win', role: 'assistant', content: '다른 탭 답', ui_components: [] }]
        });
      }
      // 마운트 땐 awaiting_input 이던 런이, 충돌 뒤 조회에선 다른 탭이 이어받아 running.
      if (url === `${BASE}/runs/active`) {
        return json({ id: 'run-w', status: n === 1 ? 'awaiting_input' : 'running' });
      }
      if (url === `${BASE}/runs/run-w/resume` && method === 'POST') {
        return sse(
          [
            {
              type: 'error',
              seq: 1,
              error_code: 'AGENT_RUN_NOT_RESUMABLE',
              message: '재개할 수 없는 런입니다.',
              recoverable: false
            },
            { type: 'done', seq: 2, run_status: 'failed' }
          ],
          'run-w'
        );
      }
      if (url === `${BASE}/runs/run-w`) return json({ id: 'run-w', status: n < 3 ? 'running' : 'succeeded' });
      if (url === `${BASE}/runs` && method === 'POST') return reply('m-new', '이어서 답할게요', 'run-n');
      return unexpected(method, url);
    });

    const { result } = renderHook(() => useAgentStream('s1', { activeRunPollMs: 5 }));
    await waitFor(() => expect(calls.some((c) => c.url === `${BASE}/runs/active`)).toBe(true));
    await act(async () => {
      await result.current.send('답변');
    });

    expect(result.current.status).toBe('done');
    expect(result.current.error).toBeNull();
    expect(calls.filter((c) => c.method === 'POST' && c.url === `${BASE}/runs`)).toHaveLength(1);
    expect(result.current.messages.map((m) => m.content)).toEqual(['다른 탭 답', '답변', '이어서 답할게요']);
  });

  it('같은 내용의 새 user 메시지(다른 탭)는 옛 영속 버블로 오인되지 않고 병합된다', async () => {
    installFetch((method, url, n) => {
      if (url === `${BASE}/messages`) {
        const old = [
          { id: 'db-u0', role: 'user', content: '네', ui_components: [] },
          { id: 'a0', role: 'assistant', content: '처음 답', ui_components: [] }
        ];
        return json({
          messages:
            n === 1
              ? old
              : [
                  ...old,
                  { id: 'db-u9', role: 'user', content: '네', ui_components: [] },
                  { id: 'a9', role: 'assistant', content: '다른 탭 답', ui_components: [] }
                ]
        });
      }
      if (url === `${BASE}/runs/active`) return notActive();
      if (url === `${BASE}/runs` && method === 'POST') {
        if (n === 1) {
          return json(
            { error: { code: 'AGENT_RUN_ALREADY_ACTIVE' }, detail: { active_run_id: 'run-a', status: 'running' } },
            409
          );
        }
        return reply('a2', '둘째 답', 'run-2');
      }
      if (url === `${BASE}/runs/run-a`) return json({ id: 'run-a', status: n < 2 ? 'running' : 'succeeded' });
      return unexpected(method, url);
    });

    const { result } = renderHook(() => useAgentStream('s1', { activeRunPollMs: 5 }));
    await waitFor(() => expect(result.current.messages).toHaveLength(2));
    await act(async () => {
      await result.current.send('둘째');
    });

    expect(result.current.messages.map((m) => [m.role, m.content])).toEqual([
      ['user', '네'],
      ['assistant', '처음 답'],
      ['user', '네'],
      ['assistant', '다른 탭 답'],
      ['user', '둘째'],
      ['assistant', '둘째 답']
    ]);
  });
});

describe('useAgentStream 리뷰 회귀 3라운드 (Codex PR #204)', () => {
  it('409 대기 후 병합 시 이긴 탭이 같은 내용을 보냈어도 두 user 턴이 모두 남는다', async () => {
    // 이 탭의 '분석해 주세요' 는 아직 전달되지 않았으니 영속본이 있을 수 없다 — 이긴 탭의
    // 같은 내용 user 턴이 내 버블에 오인돼 빠지면 안 된다.
    installFetch((method, url, n) => {
      if (url === `${BASE}/messages`) {
        return json({
          messages:
            n === 1
              ? []
              : [
                  { id: 'db-other', role: 'user', content: '분석해 주세요', ui_components: [] },
                  { id: 'a-other', role: 'assistant', content: '다른 탭 답', ui_components: [] }
                ]
        });
      }
      if (url === `${BASE}/runs/active`) return notActive();
      if (url === `${BASE}/runs` && method === 'POST') {
        if (n === 1) {
          return json(
            { error: { code: 'AGENT_RUN_ALREADY_ACTIVE' }, detail: { active_run_id: 'run-a', status: 'running' } },
            409
          );
        }
        return reply('a-mine', '내 답', 'run-m');
      }
      if (url === `${BASE}/runs/run-a`) return json({ id: 'run-a', status: n < 2 ? 'running' : 'succeeded' });
      return unexpected(method, url);
    });

    const { result } = renderHook(() => useAgentStream('s1', { activeRunPollMs: 5 }));
    await act(async () => {
      await result.current.send('분석해 주세요');
    });

    expect(result.current.messages.map((m) => [m.role, m.content])).toEqual([
      ['user', '분석해 주세요'],
      ['assistant', '다른 탭 답'],
      ['user', '분석해 주세요'],
      ['assistant', '내 답']
    ]);
  });
});

describe('useAgentStream 리뷰 회귀 4라운드 (Codex PR #204)', () => {
  it('interrupted 런의 reconnect drain 이 되돌리는 답은 새 user 버블 앞에 끼운다', async () => {
    const calls = installFetch((method, url) => {
      if (url === `${BASE}/messages`) return json({ messages: [] });
      if (url === `${BASE}/runs/active`) return json({ id: 'run-i', status: 'interrupted' });
      if (url === `${BASE}/runs/run-i/resume` && method === 'POST') {
        return reply('m-old', '이전 답(재전송)', 'run-i');
      }
      if (url === `${BASE}/runs` && method === 'POST') return reply('m-new', '새 답', 'run-n');
      return unexpected(method, url);
    });

    const { result } = renderHook(() => useAgentStream('s1', { activeRunPollMs: 5 }));
    await waitFor(() => expect(calls.some((c) => c.url === `${BASE}/runs/active`)).toBe(true));
    await act(async () => {
      await result.current.send('새 질문');
    });

    const drain = calls.find((c) => c.url === `${BASE}/runs/run-i/resume`);
    expect(drain?.body ?? '').not.toContain('새 질문'); // no-message drain
    expect(result.current.messages.map((m) => m.content)).toEqual(['이전 답(재전송)', '새 질문', '새 답']);
  });

  it('충돌 뒤 활성 런이 이미 끝났으면 그 런의 턴을 합친 뒤 새 런으로 보낸다', async () => {
    // 스트림 내 NOT_RESUMABLE → 활성 런 조회 404(이긴 탭이 끝남) → 히스토리 병합 → 새 런.
    const calls = installFetch((method, url, n) => {
      if (url === `${BASE}/messages`) {
        return json({
          messages:
            n === 1
              ? []
              : [
                  { id: 'u-win', role: 'user', content: '다른 탭 질문', ui_components: [] },
                  { id: 'a-win', role: 'assistant', content: '다른 탭 답', ui_components: [] }
                ]
        });
      }
      if (url === `${BASE}/runs/active`) {
        return n === 1 ? json({ id: 'run-w', status: 'awaiting_input' }) : notActive();
      }
      if (url === `${BASE}/runs/run-w/resume` && method === 'POST') {
        return sse(
          [
            { type: 'error', seq: 1, error_code: 'AGENT_RUN_NOT_RESUMABLE', message: 'x', recoverable: false },
            { type: 'done', seq: 2, run_status: 'failed' }
          ],
          'run-w'
        );
      }
      if (url === `${BASE}/runs` && method === 'POST') return reply('m-new', '새 답', 'run-n');
      return unexpected(method, url);
    });

    const { result } = renderHook(() => useAgentStream('s1', { activeRunPollMs: 5 }));
    await waitFor(() => expect(calls.some((c) => c.url === `${BASE}/runs/active`)).toBe(true));
    await act(async () => {
      await result.current.send('답변');
    });

    expect(result.current.status).toBe('done');
    expect(result.current.messages.map((m) => [m.role, m.content])).toEqual([
      ['user', '다른 탭 질문'],
      ['assistant', '다른 탭 답'],
      ['user', '답변'],
      ['assistant', '새 답']
    ]);
  });
});

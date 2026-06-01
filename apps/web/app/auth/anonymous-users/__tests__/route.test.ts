import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { POST } from '../route';

const PUBLIC_ENV_KEY = 'NEXT_PUBLIC_API_BASE_URL';
const INTERNAL_ENV_KEY = 'API_INTERNAL_BASE_URL';

function makeRequest(
  body: unknown,
  init?: { headers?: Record<string, string> }
): NextRequest {
  return new NextRequest('http://localhost:3000/auth/anonymous-users', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      ...(init?.headers ?? {})
    },
    body: JSON.stringify(body)
  });
}

describe('POST /auth/anonymous-users — same-origin BFF proxy (CMP-584 round-5)', () => {
  const savedEnv: { [k: string]: string | undefined } = {};
  const fetchSpy = vi.fn();

  beforeEach(() => {
    savedEnv[PUBLIC_ENV_KEY] = process.env[PUBLIC_ENV_KEY];
    savedEnv[INTERNAL_ENV_KEY] = process.env[INTERNAL_ENV_KEY];
    process.env[PUBLIC_ENV_KEY] = '/api';
    process.env[INTERNAL_ENV_KEY] = 'http://api:8000';
    fetchSpy.mockReset();
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    if (savedEnv[PUBLIC_ENV_KEY] === undefined) delete process.env[PUBLIC_ENV_KEY];
    else process.env[PUBLIC_ENV_KEY] = savedEnv[PUBLIC_ENV_KEY];
    if (savedEnv[INTERNAL_ENV_KEY] === undefined) delete process.env[INTERNAL_ENV_KEY];
    else process.env[INTERNAL_ENV_KEY] = savedEnv[INTERNAL_ENV_KEY];
    vi.unstubAllGlobals();
  });

  it('proxies to serverApiBaseUrl()/auth/anonymous-users with the same body server-side', async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          anonymous_user_id: '11111111-1111-1111-1111-111111111111',
          reused: false
        }),
        { status: 200, headers: { 'content-type': 'application/json' } }
      )
    );

    const res = await POST(
      makeRequest({ existing_anonymous_user_id: null })
    );

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [calledUrl, calledInit] = fetchSpy.mock.calls[0]!;
    // Docker-internal hostname is OK for server-side fetch — that's the whole point.
    expect(calledUrl).toBe('http://api:8000/auth/anonymous-users');
    expect((calledInit as RequestInit).method).toBe('POST');
    expect(await res.json()).toEqual({
      anonymous_user_id: '11111111-1111-1111-1111-111111111111',
      reused: false
    });
    expect(res.status).toBe(200);
  });

  it('forwards request cookies and upstream set-cookie back to the browser', async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          anonymous_user_id: '22222222-2222-2222-2222-222222222222',
          reused: true
        }),
        {
          status: 200,
          headers: {
            'content-type': 'application/json',
            'set-cookie': 'jippin_session=abc; Path=/; HttpOnly'
          }
        }
      )
    );

    const res = await POST(
      makeRequest(
        { existing_anonymous_user_id: 'reuse-me' },
        { headers: { cookie: 'jippin_anon=existing; foo=bar' } }
      )
    );

    const [, calledInit] = fetchSpy.mock.calls[0]!;
    const headers = (calledInit as RequestInit).headers as Record<string, string>;
    expect(headers.cookie).toBe('jippin_anon=existing; foo=bar');
    expect(res.headers.get('set-cookie')).toContain('jippin_session=abc');
  });

  it('passes through upstream status (e.g. 4xx) without swallowing the body', async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ error: { code: 'BAD' } }), {
        status: 422,
        headers: { 'content-type': 'application/json' }
      })
    );

    const res = await POST(makeRequest({ existing_anonymous_user_id: 'bad' }));

    expect(res.status).toBe(422);
    expect(await res.json()).toEqual({ error: { code: 'BAD' } });
  });
});

import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { NextRequest } from 'next/server';

import { signFlowCookie } from '@/lib/flow-cookie';

interface CookiesToSet {
  name: string;
  value: string;
  options?: Record<string, unknown>;
}

interface ServerClientInit {
  cookies: { getAll: () => Array<{ name: string; value: string }>; setAll: (xs: CookiesToSet[]) => void };
}

const mocks = vi.hoisted(() => ({
  createServerClient: vi.fn(),
}));

vi.mock('@supabase/ssr', () => ({
  createServerClient: mocks.createServerClient,
}));

process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co';
process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'test-anon-key';
process.env.NEXT_PUBLIC_API_BASE_URL = 'http://api.localhost';
process.env.API_INTERNAL_BASE_URL = 'http://api.localhost';
process.env.SUPABASE_FLOW_COOKIE_SECRET = 'test-flow-cookie-secret';

const SESSION_COOKIE_NAME = 'sb-example-auth-token';
const SESSION_COOKIE_VALUE = 'session-value';
const BACKEND_SESSION_COOKIE_NAME = 'jippin_session';
const BACKEND_SESSION_COOKIE_VALUE = 'backend-session-value';
const EXPIRED_SESSION_COOKIE_NAME = 'sb-example-refresh-token';
const EXPIRED_SESSION_COOKIE_VALUE = '';

function makeRequest(pathAndQuery: string, extraCookies: Array<{ name: string; value: string }> = []): NextRequest {
  const url = new URL(`http://localhost:3000${pathAndQuery}`);
  const cookies = [{ name: 'sb-example-auth-token-code-verifier', value: 'verifier' }, ...extraCookies];
  return {
    url: url.toString(),
    nextUrl: url,
    headers: {
      get: (name: string) => {
        if (name.toLowerCase() !== 'cookie') {
          return null;
        }
        return cookies.map((cookie) => `${cookie.name}=${cookie.value}`).join('; ');
      },
    },
    cookies: {
      getAll: () => cookies,
      get: (name: string) => cookies.find((cookie) => cookie.name === name),
    },
  } as unknown as NextRequest;
}

function setCookieValues(response: Response): string[] {
  return response.headers.getSetCookie?.() ?? response.headers.get('Set-Cookie')?.split(/,(?=\s*[^,;]+=)/g) ?? [];
}

describe('GET /auth/callback — session cookie preservation', () => {
  beforeEach(() => {
    mocks.createServerClient.mockReset();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('{}', {
          status: 200,
          headers: {
            'Set-Cookie': `${BACKEND_SESSION_COOKIE_NAME}=${BACKEND_SESSION_COOKIE_VALUE}; Path=/; HttpOnly; SameSite=Lax`,
          },
        }),
      ),
    );
  });

  function kakaoSigninCookie(): { name: string; value: string } {
    return {
      name: 'jippin_oauth_provider',
      value: signFlowCookie(
        { provider: 'kakao', supabase_provider: 'custom:kakao', intent: 'signin' },
        600,
      ),
    };
  }

  it('flushes every exchangeCodeForSession cookie onto the final redirect response', async () => {
    mocks.createServerClient.mockImplementation((_url: string, _key: string, init: ServerClientInit) => ({
      auth: {
        exchangeCodeForSession: vi.fn().mockImplementation(async () => {
          init.cookies.setAll([
            {
              name: SESSION_COOKIE_NAME,
              value: SESSION_COOKIE_VALUE,
              options: { httpOnly: true, secure: true, sameSite: 'lax', path: '/', maxAge: 3600 },
            },
          ]);
          return { data: { session: { access_token: 'supabase-access-token' } }, error: null };
        }),
      },
    }));

    const { GET } = await import('./route');
    const response = await GET(
      makeRequest('/auth/callback?code=abc&next=/app/reports/1', [kakaoSigninCookie()]),
    );

    expect(response.status).toBe(302);
    expect(response.headers.get('Location')).toBe('http://localhost:3000/app/reports/1');
    const cookies = setCookieValues(response).join('\n');
    expect(cookies).toMatch(
      new RegExp(`(?:^|\\n)${SESSION_COOKIE_NAME}=${SESSION_COOKIE_VALUE}`),
    );
    expect(cookies).toMatch(new RegExp(`(?:^|\\n)${BACKEND_SESSION_COOKIE_NAME}=${BACKEND_SESSION_COOKIE_VALUE}`));
    expect(fetch).toHaveBeenCalledWith('http://api.localhost/auth/supabase/session', {
      method: 'POST',
      headers: {
        Authorization: 'Bearer supabase-access-token',
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ anonymous_user_id: null, requested_provider: 'kakao' }),
      cache: 'no-store',
    });
  });

  it('forwards anonymous_user_id to backend session bridge', async () => {
    mocks.createServerClient.mockImplementation(() => ({
      auth: {
        exchangeCodeForSession: vi.fn().mockResolvedValue({
          data: { session: { access_token: 'supabase-access-token' } },
          error: null,
        }),
      },
    }));

    const { GET } = await import('./route');
    await GET(
      makeRequest('/auth/callback?code=abc&anonymous_user_id=legacy-anon-id', [
        kakaoSigninCookie(),
      ]),
    );

    expect(fetch).toHaveBeenCalledWith(
      'http://api.localhost/auth/supabase/session',
      expect.objectContaining({
        body: JSON.stringify({
          anonymous_user_id: 'legacy-anon-id',
          requested_provider: 'kakao',
        }),
      }),
    );
  });

  it('routes incomplete backend signups to terms before requested next path', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            signup_complete: false,
            missing_required_terms: ['service_terms'],
            redirect_url: 'http://localhost:3000/auth/terms',
          }),
          {
            status: 200,
            headers: {
              'Set-Cookie': `${BACKEND_SESSION_COOKIE_NAME}=${BACKEND_SESSION_COOKIE_VALUE}; Path=/; HttpOnly; SameSite=Lax`,
            },
          },
        ),
      ),
    );
    mocks.createServerClient.mockImplementation(() => ({
      auth: {
        exchangeCodeForSession: vi.fn().mockResolvedValue({
          data: { session: { access_token: 'supabase-access-token' } },
          error: null,
        }),
      },
    }));

    const { GET } = await import('./route');
    const response = await GET(
      makeRequest('/auth/callback?code=abc&next=/app/reports/1', [kakaoSigninCookie()]),
    );

    expect(response.status).toBe(302);
    expect(response.headers.get('Location')).toBe(
      'http://localhost:3000/auth/terms?next=%2Fapp%2Freports%2F1',
    );
    expect(setCookieValues(response).join('\n')).toContain(BACKEND_SESSION_COOKIE_NAME);
  });

  it('falls back to the implemented terms route when the backend omits redirect_url', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            signup_complete: false,
            missing_required_terms: ['service_terms'],
            redirect_url: null,
          }),
          {
            status: 200,
            headers: {
              'Set-Cookie': `${BACKEND_SESSION_COOKIE_NAME}=${BACKEND_SESSION_COOKIE_VALUE}; Path=/; HttpOnly; SameSite=Lax`,
            },
          },
        ),
      ),
    );
    mocks.createServerClient.mockImplementation(() => ({
      auth: {
        exchangeCodeForSession: vi.fn().mockResolvedValue({
          data: { session: { access_token: 'supabase-access-token' } },
          error: null,
        }),
      },
    }));

    const { GET } = await import('./route');
    const response = await GET(
      makeRequest('/auth/callback?code=abc&next=/app/reports/1', [kakaoSigninCookie()]),
    );

    expect(response.status).toBe(302);
    expect(response.headers.get('Location')).toBe(
      'http://localhost:3000/auth/terms?next=%2Fapp%2Freports%2F1',
    );
  });

  it('redirects link callbacks after signed Supabase linkIdentity exchange without backend shim', async () => {
    const flowCookie = signFlowCookie(
      { provider: 'kakao', supabase_provider: 'custom:kakao', intent: 'link' },
      600,
    );
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    mocks.createServerClient.mockImplementation(() => ({
      auth: {
        exchangeCodeForSession: vi.fn().mockResolvedValue({
          data: { session: { access_token: 'supabase-access-token' } },
          error: null,
        }),
      },
    }));

    const { GET } = await import('./route');
    const response = await GET(
      makeRequest('/auth/callback?code=abc&intent=link&next=/account/security', [
        { name: 'jippin_oauth_provider', value: flowCookie },
        { name: BACKEND_SESSION_COOKIE_NAME, value: 'current-backend-session' },
      ]),
    );

    expect(response.status).toBe(302);
    expect(response.headers.get('Location')).toBe('http://localhost:3000/account/security');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('fails closed for link callbacks when the signed flow context is missing', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response('{}', {
        status: 200,
        headers: {
          'Set-Cookie': `${BACKEND_SESSION_COOKIE_NAME}=${BACKEND_SESSION_COOKIE_VALUE}; Path=/; HttpOnly; SameSite=Lax`,
        },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);
    mocks.createServerClient.mockImplementation(() => ({
      auth: {
        exchangeCodeForSession: vi.fn().mockResolvedValue({
          data: { session: { access_token: 'supabase-access-token' } },
          error: null,
        }),
      },
    }));

    const { GET } = await import('./route');
    const response = await GET(makeRequest('/auth/callback?code=abc&intent=link&next=/account/security'));

    expect(response.status).toBe(302);
    expect(response.headers.get('Location')).toBe('http://localhost:3000/login?error=oauth_callback_failed');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('preserves Supabase exchange cookies on successful link callbacks', async () => {
    const flowCookie = signFlowCookie(
      { provider: 'kakao', supabase_provider: 'custom:kakao', intent: 'link' },
      600,
    );
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    mocks.createServerClient.mockImplementation((_url: string, _key: string, init: ServerClientInit) => ({
      auth: {
        exchangeCodeForSession: vi.fn().mockImplementation(async () => {
          init.cookies.setAll([
            {
              name: SESSION_COOKIE_NAME,
              value: SESSION_COOKIE_VALUE,
              options: { httpOnly: true, secure: true, sameSite: 'lax', path: '/', maxAge: 3600 },
            },
          ]);
          return { data: { session: { access_token: 'supabase-access-token' } }, error: null };
        }),
      },
    }));

    const { GET } = await import('./route');
    const response = await GET(
      makeRequest('/auth/callback?code=abc&intent=link&next=/account/security', [
        { name: 'jippin_oauth_provider', value: flowCookie },
      ]),
    );

    expect(response.status).toBe(302);
    expect(response.headers.get('Location')).toBe('http://localhost:3000/account/security');
    expect(setCookieValues(response).join('\n')).toContain(SESSION_COOKIE_NAME);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('passes the requested provider from the signed flow cookie into the session bridge', async () => {
    const flowCookie = signFlowCookie(
      { provider: 'kakao', supabase_provider: 'custom:kakao', intent: 'signin' },
      600,
    );
    mocks.createServerClient.mockImplementation(() => ({
      auth: {
        exchangeCodeForSession: vi.fn().mockResolvedValue({
          data: { session: { access_token: 'supabase-access-token' } },
          error: null,
        }),
      },
    }));

    const { GET } = await import('./route');
    await GET(
      makeRequest('/auth/callback?code=abc', [
        { name: 'jippin_oauth_provider', value: flowCookie },
      ]),
    );

    expect(fetch).toHaveBeenCalledWith(
      'http://api.localhost/auth/supabase/session',
      expect.objectContaining({
        body: JSON.stringify({
          anonymous_user_id: null,
          requested_provider: 'kakao',
        }),
      }),
    );
  });

  it('rejects backslash-prefixed next values to avoid post-auth open redirects', async () => {
    mocks.createServerClient.mockImplementation((_url: string, _key: string, init: ServerClientInit) => ({
      auth: {
        exchangeCodeForSession: vi.fn().mockImplementation(async () => {
          init.cookies.setAll([
            {
              name: SESSION_COOKIE_NAME,
              value: SESSION_COOKIE_VALUE,
              options: { httpOnly: true, secure: true, sameSite: 'lax', path: '/', maxAge: 3600 },
            },
          ]);
          return { data: { session: { access_token: 'supabase-access-token' } }, error: null };
        }),
      },
    }));

    const { GET } = await import('./route');
    const response = await GET(
      makeRequest('/auth/callback?code=abc&next=/\\evil.com', [kakaoSigninCookie()]),
    );

    expect(response.status).toBe(302);
    expect(response.headers.get('Location')).toBe('http://localhost:3000/');
    expect(setCookieValues(response).join('\n')).toMatch(
      new RegExp(`(?:^|\\n)${SESSION_COOKIE_NAME}=${SESSION_COOKIE_VALUE}`),
    );
  });

  it('fails closed when backend session minting fails after Supabase exchange', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 503 })));
    mocks.createServerClient.mockImplementation((_url: string, _key: string, init: ServerClientInit) => ({
      auth: {
        exchangeCodeForSession: vi.fn().mockImplementation(async () => {
          init.cookies.setAll([
            {
              name: SESSION_COOKIE_NAME,
              value: SESSION_COOKIE_VALUE,
              options: { httpOnly: true, secure: true, sameSite: 'lax', path: '/', maxAge: 3600 },
            },
          ]);
          return { data: { session: { access_token: 'supabase-access-token' } }, error: null };
        }),
      },
    }));

    const { GET } = await import('./route');
    const response = await GET(
      makeRequest('/auth/callback?code=abc&next=/app/reports/1', [kakaoSigninCookie()]),
    );

    expect(response.status).toBe(302);
    expect(response.headers.get('Location')).toBe('http://localhost:3000/login?error=oauth_callback_failed');
    const cookies = setCookieValues(response).join('\n');
    expect(cookies).not.toContain(BACKEND_SESSION_COOKIE_NAME);
    expect(cookies).not.toContain(SESSION_COOKIE_NAME);
  });

  it('preserves exchangeCodeForSession cleanup cookies on callback failure redirects', async () => {
    mocks.createServerClient.mockImplementation((_url: string, _key: string, init: ServerClientInit) => ({
      auth: {
        exchangeCodeForSession: vi.fn().mockImplementation(async () => {
          init.cookies.setAll([
            {
              name: SESSION_COOKIE_NAME,
              value: SESSION_COOKIE_VALUE,
              options: { httpOnly: true, secure: true, sameSite: 'lax', path: '/', maxAge: 0 },
            },
            {
              name: EXPIRED_SESSION_COOKIE_NAME,
              value: EXPIRED_SESSION_COOKIE_VALUE,
              options: { httpOnly: true, secure: true, sameSite: 'lax', path: '/', maxAge: 0 },
            },
          ]);
          return { data: { session: null }, error: { code: 'auth/missing-code-verifier' } };
        }),
      },
    }));

    const { GET } = await import('./route');
    const response = await GET(makeRequest('/auth/callback?code=stale&next=/app/reports/1'));

    expect(response.status).toBe(302);
    expect(response.headers.get('Location')).toBe('http://localhost:3000/login?error=oauth_callback_failed');

    const cookies = setCookieValues(response).join('\n');
    expect(cookies).toMatch(new RegExp(`(?:^|\\n)${SESSION_COOKIE_NAME}=${SESSION_COOKIE_VALUE}`));
    expect(cookies).toMatch(new RegExp(`(?:^|\\n)${EXPIRED_SESSION_COOKIE_NAME}=`));
  });

  it('redirects missing-code callbacks to login without creating Supabase cookies', async () => {
    const { GET } = await import('./route');
    const response = await GET(makeRequest('/auth/callback?next=/app/reports/1'));

    expect(response.status).toBe(302);
    expect(response.headers.get('Location')).toBe('http://localhost:3000/login?error=oauth_callback_failed');
    expect(mocks.createServerClient).not.toHaveBeenCalled();
    expect(setCookieValues(response)).toHaveLength(0);
  });
});

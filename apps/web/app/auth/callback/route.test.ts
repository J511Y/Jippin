import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { NextRequest } from 'next/server';

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

const SESSION_COOKIE_NAME = 'sb-example-auth-token';
const SESSION_COOKIE_VALUE = 'session-value';
const BACKEND_SESSION_COOKIE_NAME = 'jippin_session';
const BACKEND_SESSION_COOKIE_VALUE = 'backend-session-value';
const EXPIRED_SESSION_COOKIE_NAME = 'sb-example-refresh-token';
const EXPIRED_SESSION_COOKIE_VALUE = '';

function makeRequest(pathAndQuery: string): NextRequest {
  const url = new URL(`http://localhost:3000${pathAndQuery}`);
  return {
    url: url.toString(),
    nextUrl: url,
    cookies: {
      getAll: () => [{ name: 'sb-example-auth-token-code-verifier', value: 'verifier' }],
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
    const response = await GET(makeRequest('/auth/callback?code=abc&next=/app/reports/1'));

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
      body: JSON.stringify({ anonymous_user_id: null }),
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
    await GET(makeRequest('/auth/callback?code=abc&anonymous_user_id=legacy-anon-id'));

    expect(fetch).toHaveBeenCalledWith(
      'http://api.localhost/auth/supabase/session',
      expect.objectContaining({
        body: JSON.stringify({ anonymous_user_id: 'legacy-anon-id' }),
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
    const response = await GET(makeRequest('/auth/callback?code=abc&next=/app/reports/1'));

    expect(response.status).toBe(302);
    expect(response.headers.get('Location')).toBe('http://localhost:3000/auth/terms');
    expect(setCookieValues(response).join('\n')).toContain(BACKEND_SESSION_COOKIE_NAME);
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
    const response = await GET(makeRequest('/auth/callback?code=abc&next=/\\evil.com'));

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
    const response = await GET(makeRequest('/auth/callback?code=abc&next=/app/reports/1'));

    expect(response.status).toBe(302);
    expect(response.headers.get('Location')).toBe('http://localhost:3000/login?error=oauth_callback_failed');
    expect(setCookieValues(response).join('\n')).not.toContain(BACKEND_SESSION_COOKIE_NAME);
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

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

const SESSION_COOKIE_NAME = 'sb-example-auth-token';
const SESSION_COOKIE_VALUE = 'session-value';

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
          return { data: { session: {} }, error: null };
        }),
      },
    }));

    const { GET } = await import('./route');
    const response = await GET(makeRequest('/auth/callback?code=abc&next=/app/reports/1'));

    expect(response.status).toBe(302);
    expect(response.headers.get('Location')).toBe('http://localhost:3000/app/reports/1');
    expect(setCookieValues(response).join('\n')).toMatch(
      new RegExp(`(?:^|\\n)${SESSION_COOKIE_NAME}=${SESSION_COOKIE_VALUE}`),
    );
  });
});

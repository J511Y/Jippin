import { NextRequest } from 'next/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';

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

const ROTATED_COOKIE_NAME = 'sb-example-auth-token';
const ROTATED_COOKIE_VALUE = 'rotated-session';

function setCookieValues(response: Response): string[] {
  return response.headers.getSetCookie?.() ?? response.headers.get('Set-Cookie')?.split(/,(?=\s*[^,;]+=)/g) ?? [];
}

function mockGetUser(user: unknown = null): void {
  mocks.createServerClient.mockImplementation((_url: string, _key: string, init: ServerClientInit) => ({
    auth: {
      getUser: vi.fn().mockImplementation(async () => {
        init.cookies.setAll([
          {
            name: ROTATED_COOKIE_NAME,
            value: ROTATED_COOKIE_VALUE,
            options: { httpOnly: true, secure: true, sameSite: 'lax', path: '/', maxAge: 3600 },
          },
        ]);
        return { data: { user }, error: null };
      }),
    },
  }));
}

describe('proxy — Supabase Set-Cookie flush invariant', () => {
  beforeEach(() => {
    vi.resetModules();
    mocks.createServerClient.mockReset();
  });

  it('returns token rotation cookies on auth routes', async () => {
    mockGetUser();
    const { proxy } = await import('./proxy');
    const response = await proxy(new NextRequest('http://localhost:3000/auth/callback'));

    expect(response.status).toBe(200);
    expect(mocks.createServerClient).not.toHaveBeenCalled();
    expect(setCookieValues(response)).toHaveLength(0);
  });

  it('skips Supabase lookup on anonymous pre-review routes', async () => {
    mockGetUser();
    const { proxy } = await import('./proxy');
    const response = await proxy(new NextRequest('http://localhost:3000/app/pre-review/upload'));

    expect(response.status).toBe(200);
    expect(mocks.createServerClient).not.toHaveBeenCalled();
  });

  it('redirects protected routes without backend session before Supabase lookup', async () => {
    mockGetUser();
    const { proxy } = await import('./proxy');
    const response = await proxy(new NextRequest('http://localhost:3000/app/consult?draft=1'));

    expect(response.status).toBe(307);
    expect(response.headers.get('Location')).toBe('http://localhost:3000/login?next=%2Fapp%2Fconsult%3Fdraft%3D1');
    expect(mocks.createServerClient).not.toHaveBeenCalled();
    expect(setCookieValues(response)).toHaveLength(0);
  });

  it('refreshes Supabase cookies only after backend session guard passes', async () => {
    mockGetUser();
    const { proxy } = await import('./proxy');
    const response = await proxy(
      new NextRequest('http://localhost:3000/app/consult?draft=1', {
        headers: { Cookie: 'jippin_session=backend-session' },
      }),
    );

    expect(response.status).toBe(200);
    expect(setCookieValues(response).join('\n')).toMatch(
      new RegExp(`(?:^|\\n)${ROTATED_COOKIE_NAME}=${ROTATED_COOKIE_VALUE}`),
    );
  });
});

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const supabaseMocks = vi.hoisted(() => ({
  exchangeCodeForSession: vi.fn(),
  linkIdentity: vi.fn(),
  signInWithOAuth: vi.fn(),
  signOut: vi.fn(),
}));

vi.mock('@/lib/supabase/server', () => ({
  createRouteHandlerClient: () => ({
    auth: {
      exchangeCodeForSession: supabaseMocks.exchangeCodeForSession,
      linkIdentity: supabaseMocks.linkIdentity,
      signInWithOAuth: supabaseMocks.signInWithOAuth,
      signOut: supabaseMocks.signOut,
    },
  }),
}));

const previousEnv = { ...process.env };

function cookieHeader(response: Response): string {
  return response.headers.get('set-cookie') ?? '';
}

function expectCallbackCookiesExpired(response: Response): void {
  const header = cookieHeader(response);
  expect(header).toContain('jippin_merge_intent=');
  expect(header).toContain('jippin_oauth_provider=');
  expect(header).toContain('jippin_signin_intent=');
  expect(header).toContain('Max-Age=0');
  expect(header).toContain('Path=/auth/callback');
}

function callbackCookie(extra = ''): string {
  return `jippin_signin_intent=signin${extra ? `; ${extra}` : ''}`;
}

function mockSession() {
  return {
    access_token: 'access-token',
    provider_token: null,
    provider_refresh_token: null,
    user: {
      id: 'user-1',
      identities: [{ provider: 'google', created_at: '2026-06-01T00:00:00.000Z' }],
    },
  };
}

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  process.env = {
    ...previousEnv,
    NEXT_PUBLIC_API_BASE_URL: 'http://api.test',
    NEXT_PUBLIC_FRONTEND_AUTH_SUCCESS_URL: '/',
    NEXT_PUBLIC_FRONTEND_AUTH_FAILURE_URL: '/auth/failure',
    NEXT_PUBLIC_SUPABASE_URL: 'https://supabase.test',
    NEXT_PUBLIC_SUPABASE_ANON_KEY: 'anon-key',
  };
});

afterEach(() => {
  process.env = { ...previousEnv };
  cleanup();
  vi.restoreAllMocks();
});

describe('/auth/callback route', () => {
  it.each([
    'access_denied',
    'identity_already_exists',
  ])('expires callback cookies for provider error %s', async (reason) => {
    const { GET } = await import('@/app/auth/callback/route');
    const response = await GET(
      new NextRequest(`http://localhost/auth/callback?error=${reason}`),
    );

    expect(response.status).toBe(302);
    expect(response.headers.get('location')).toBe(
      `http://localhost/auth/failure?reason=${reason}`,
    );
    expectCallbackCookiesExpired(response);
  });

  it('expires callback cookies when code is missing', async () => {
    const { GET } = await import('@/app/auth/callback/route');
    const response = await GET(new NextRequest('http://localhost/auth/callback'));

    expect(response.status).toBe(302);
    expect(response.headers.get('location')).toBe(
      'http://localhost/auth/failure?reason=missing_code',
    );
    expectCallbackCookiesExpired(response);
  });

  it('expires callback cookies when code exchange fails', async () => {
    supabaseMocks.exchangeCodeForSession.mockResolvedValueOnce({
      data: null,
      error: { code: 'exchange_failed' },
    });

    const { GET } = await import('@/app/auth/callback/route');
    const response = await GET(
      new NextRequest('http://localhost/auth/callback?code=bad', {
        headers: { cookie: callbackCookie() },
      }),
    );

    expect(response.status).toBe(302);
    expect(response.headers.get('location')).toBe(
      'http://localhost/auth/failure?reason=exchange_failed',
    );
    expectCallbackCookiesExpired(response);
  });

  it('expires callback cookies after successful exchange', async () => {
    supabaseMocks.exchangeCodeForSession.mockResolvedValueOnce({
      data: { session: mockSession() },
      error: null,
    });

    const { GET } = await import('@/app/auth/callback/route');
    const response = await GET(
      new NextRequest('http://localhost/auth/callback?code=ok&next=/app/reports', {
        headers: { cookie: callbackCookie() },
      }),
    );

    expect(response.status).toBe(302);
    expect(response.headers.get('location')).toBe(
      'http://localhost/auth/callback-done?next=%2Fapp%2Freports',
    );
    expectCallbackCookiesExpired(response);
  });

  it('uses the cookie-only merge commit endpoint constant', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal('fetch', fetchMock);
    supabaseMocks.exchangeCodeForSession.mockResolvedValueOnce({
      data: { session: mockSession() },
      error: null,
    });

    const { COMMIT_PATH, GET } = await import('@/app/auth/callback/route');
    const response = await GET(
      new NextRequest('http://localhost/auth/callback?code=ok', {
        headers: {
          cookie: callbackCookie('jippin_merge_intent=signed-intent; jippin_oauth_provider=google'),
        },
      }),
    );

    expect(response.status).toBe(302);
    expect(COMMIT_PATH).toBe('/auth/anon-merge-intents/commit');
    expect(fetchMock).toHaveBeenCalledWith(
      new URL('/auth/anon-merge-intents/commit', 'http://api.test'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ signed_intent_cookie_value: 'signed-intent' }),
      }),
    );
  });
});

describe('/auth/oauth/start BFF', () => {
  it('sets merge intent cookie from signed_token for link-merge starts', async () => {
    supabaseMocks.signOut.mockResolvedValueOnce({ error: null });
    supabaseMocks.signInWithOAuth.mockResolvedValueOnce({
      data: { url: 'https://supabase.test/auth/v1/authorize?provider=google' },
      error: null,
    });

    const { GET } = await import('@/app/auth/oauth/start/route');
    const response = await GET(
      new NextRequest(
        'http://localhost/auth/oauth/start?provider=google&intent=link-merge&signed_token=signed-token',
      ),
    );

    expect(response.status).toBe(302);
    const location = new URL(response.headers.get('location') ?? '');
    expect(`${location.origin}${location.pathname}`).toBe('http://localhost/auth/redirect');
    expect(location.searchParams.get('to')).toBe(
      'https://supabase.test/auth/v1/authorize?provider=google',
    );
    expect(cookieHeader(response)).toContain('jippin_merge_intent=signed-token');
    expect(cookieHeader(response)).toContain('jippin_signin_intent=link-merge');
    expect(cookieHeader(response)).toContain('Path=/auth/callback');
  });
});

describe('/auth/failure page', () => {
  it('clears the oauth in-progress guard on mount', async () => {
    const removeItem = vi.spyOn(Storage.prototype, 'removeItem');
    const { AuthFailureView } = await import('@/app/auth/failure/page');

    render(<AuthFailureView reason="exchange_failed" />);

    await waitFor(() => {
      expect(removeItem).toHaveBeenCalledWith('jippin_oauth_in_progress');
    });
  });

  it('shows the identity conflict ladder entry for identity_already_exists', async () => {
    const { AuthFailureView } = await import('@/app/auth/failure/page');

    render(<AuthFailureView reason="identity_already_exists" />);

    expect(screen.getByRole('heading', { name: '이미 가입된 계정이 있습니다' })).toBeVisible();
    expect(screen.getByRole('button', { name: '예, 옮기고 로그인' })).toBeVisible();
  });
});

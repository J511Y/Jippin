import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const supabaseMocks = vi.hoisted(() => ({
  exchangeCodeForSession: vi.fn(),
  linkIdentity: vi.fn(),
  signInWithOAuth: vi.fn(),
  signOut: vi.fn(),
}));

const browserSupabaseMocks = vi.hoisted(() => ({
  getSession: vi.fn(),
}));

const routerMocks = vi.hoisted(() => ({
  replace: vi.fn(),
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

vi.mock('@/lib/supabase/browser', () => ({
  createBrowserSupabaseClient: () => ({
    auth: {
      getSession: browserSupabaseMocks.getSession,
    },
  }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => routerMocks,
}));

const previousEnv = { ...process.env };

function cookieHeader(response: Response): string {
  return response.headers.get('set-cookie') ?? '';
}

function expectCallbackCookiesExpired(response: Response): void {
  const header = cookieHeader(response);
  expect(header).toContain('jippin_merge_intent=');
  expect(header).toContain('jippin_oauth_provider=');
  expect(header).toContain('Max-Age=0');
  expect(header).toContain('Path=/auth/callback');
}

function mockSession(provider = 'custom:kakao', createdAt = new Date().toISOString()) {
  return {
    access_token: 'access-token',
    provider_token: null,
    provider_refresh_token: null,
    user: {
      id: 'user-1',
      created_at: createdAt,
      identities: [{ provider, created_at: '2026-06-01T00:00:00.000Z' }],
    },
  };
}

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  process.env = {
    ...previousEnv,
    NEXT_PUBLIC_API_BASE_URL: 'http://api.test',
    NEXT_PUBLIC_SITE_URL: 'http://localhost',
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
      new NextRequest('http://localhost/auth/callback?code=bad'),
    );

    expect(response.status).toBe(302);
    expect(response.headers.get('location')).toBe(
      'http://localhost/auth/failure?reason=exchange_failed',
    );
    expectCallbackCookiesExpired(response);
  });

  it('expires callback cookies after successful exchange', async () => {
    process.env.NEXT_PUBLIC_AUTH_KAKAO_SYNC_AUDIT_ENABLED = 'true';
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }));
    const freshContext = encodeURIComponent(`custom:kakao|${Date.now()}`);
    supabaseMocks.exchangeCodeForSession.mockResolvedValueOnce({
      data: { session: mockSession() },
      error: null,
    });

    const { GET } = await import('@/app/auth/callback/route');
    const response = await GET(
      new NextRequest('http://localhost/auth/callback?code=ok&next=/app/reports', {
        headers: {
          cookie: `jippin_oauth_provider=${freshContext}`,
        },
      }),
    );

    expect(response.status).toBe(302);
    expect(response.headers.get('location')).toBe(
      'http://localhost/auth/callback-done?next=%2Fapp%2Freports',
    );
    expectCallbackCookiesExpired(response);
  });

  it('fails closed for Kakao callbacks until sync audit is enabled', async () => {
    const freshContext = encodeURIComponent(`custom:kakao|${Date.now()}`);
    supabaseMocks.exchangeCodeForSession.mockResolvedValueOnce({
      data: { session: mockSession() },
      error: null,
    });

    const { GET } = await import('@/app/auth/callback/route');
    const response = await GET(
      new NextRequest('http://localhost/auth/callback?code=ok&next=/app/reports', {
        headers: {
          cookie: `jippin_oauth_provider=${freshContext}`,
        },
      }),
    );

    expect(response.status).toBe(302);
    expect(response.headers.get('location')).toBe(
      'http://localhost/auth/failure?reason=kakao_sync_unavailable&next=%2Fapp%2Freports&provider=kakao',
    );
    expect(supabaseMocks.signOut).toHaveBeenCalledTimes(1);
    expectCallbackCookiesExpired(response);
  });

  it('uses the cookie-only merge commit endpoint constant', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal('fetch', fetchMock);
    supabaseMocks.exchangeCodeForSession.mockResolvedValueOnce({
      data: { session: mockSession('google') },
      error: null,
    });

    const { COMMIT_PATH, GET } = await import('@/app/auth/callback/route');
    const freshContext = encodeURIComponent(`google|${Date.now()}`);
    const response = await GET(
      new NextRequest('http://localhost/auth/callback?code=ok', {
        headers: {
          cookie: `jippin_merge_intent=signed-intent; jippin_oauth_provider=${freshContext}`,
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

  it('gates Google and Naver callbacks on internal terms', async () => {
    const freshContext = encodeURIComponent(`google|${Date.now()}`);
    supabaseMocks.exchangeCodeForSession.mockResolvedValueOnce({
      data: { session: mockSession('google') },
      error: null,
    });

    const { GET } = await import('@/app/auth/callback/route');
    const response = await GET(
      new NextRequest('http://localhost/auth/callback?code=ok&next=/app/reports', {
        headers: {
          cookie: `jippin_oauth_provider=${freshContext}`,
        },
      }),
    );

    expect(response.status).toBe(302);
    expect(response.headers.get('location')).toBe(
      'http://localhost/auth/terms?next=%2Fapp%2Freports',
    );
    expectCallbackCookiesExpired(response);
  });

  it('does not re-gate existing Google users on every login', async () => {
    const freshContext = encodeURIComponent(`google|${Date.now()}`);
    supabaseMocks.exchangeCodeForSession.mockResolvedValueOnce({
      data: { session: mockSession('google', '2025-01-01T00:00:00.000Z') },
      error: null,
    });

    const { GET } = await import('@/app/auth/callback/route');
    const response = await GET(
      new NextRequest('http://localhost/auth/callback?code=ok&next=/app/reports', {
        headers: {
          cookie: `jippin_oauth_provider=${freshContext}`,
        },
      }),
    );

    expect(response.status).toBe(302);
    expect(response.headers.get('location')).toBe(
      'http://localhost/auth/callback-done?next=%2Fapp%2Freports',
    );
    expectCallbackCookiesExpired(response);
  });

  it('surfaces merge commit failures on the failure page with retry context', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
    const freshContext = encodeURIComponent(`google|${Date.now()}`);
    supabaseMocks.exchangeCodeForSession.mockResolvedValueOnce({
      data: { session: mockSession('google') },
      error: null,
    });

    const { GET } = await import('@/app/auth/callback/route');
    const response = await GET(
      new NextRequest('http://localhost/auth/callback?code=ok&next=/app/reports', {
        headers: {
          cookie: `jippin_merge_intent=signed-intent; jippin_oauth_provider=${freshContext}`,
        },
      }),
    );

    expect(response.status).toBe(302);
    expect(response.headers.get('location')).toBe(
      'http://localhost/auth/failure?reason=merge_commit_failed&next=%2Fapp%2Freports&provider=google',
    );
    expect(supabaseMocks.signOut).toHaveBeenCalledTimes(1);
    expectCallbackCookiesExpired(response);
  });

  it('rejects stale OAuth guard cookies before code exchange', async () => {
    const staleContext = encodeURIComponent('google|1');
    const { GET } = await import('@/app/auth/callback/route');
    const response = await GET(
      new NextRequest('http://localhost/auth/callback?code=ok', {
        headers: {
          cookie: `jippin_oauth_provider=${staleContext}`,
        },
      }),
    );

    expect(response.status).toBe(302);
    expect(response.headers.get('location')).toBe(
      'http://localhost/auth/failure?reason=oauth_guard_stale&provider=google',
    );
    expect(supabaseMocks.exchangeCodeForSession).not.toHaveBeenCalled();
    expectCallbackCookiesExpired(response);
  });
});

describe('/auth/oauth/start BFF', () => {
  it('returns a real 302 with flow cookies before provider redirect', async () => {
    supabaseMocks.signInWithOAuth.mockResolvedValueOnce({
      data: { url: 'https://supabase.test/auth/v1/authorize?provider=google' },
      error: null,
    });

    const { GET } = await import('@/app/auth/oauth/start/route');
    const response = await GET(
      new NextRequest('http://localhost/auth/oauth/start?provider=google&intent=signin'),
    );

    expect(response.status).toBe(302);
    expect(response.headers.get('location')).toBe(
      'https://supabase.test/auth/v1/authorize?provider=google',
    );
    expect(response.headers.get('x-middleware-next')).toBeNull();
    expect(cookieHeader(response)).toMatch(/jippin_oauth_provider=google(%7C|\|)\d+/);
    expect(cookieHeader(response)).toContain('Path=/auth/callback');
    expect(cookieHeader(response)).toContain('Max-Age=300');
  });

  it('sets merge intent cookie from server-side enqueue for link-merge starts', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ signed_token: 'signed-token' }),
    });
    vi.stubGlobal('fetch', fetchMock);
    supabaseMocks.signOut.mockResolvedValueOnce({ error: null });
    supabaseMocks.signInWithOAuth.mockResolvedValueOnce({
      data: { url: 'https://supabase.test/auth/v1/authorize?provider=google' },
      error: null,
    });

    const { GET } = await import('@/app/auth/oauth/start/route');
    const response = await GET(
      new NextRequest(
        'http://localhost/auth/oauth/start?provider=google&intent=link-merge&anonymous_user_id=anon-1&next=/app/reports',
      ),
    );

    expect(response.status).toBe(302);
    expect(response.headers.get('location')).toBe(
      'https://supabase.test/auth/v1/authorize?provider=google',
    );
    expect(cookieHeader(response)).toContain('jippin_merge_intent=signed-token');
    expect(cookieHeader(response)).toContain('Path=/auth/callback');
    expect(cookieHeader(response)).toContain('Max-Age=300');
    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/auth/anon-merge-intents',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          anonymous_user_id: 'anon-1',
          provider: 'google',
          next: '/app/reports',
        }),
      }),
    );
    expect(supabaseMocks.signOut).toHaveBeenCalledTimes(1);
  });

  it('does not sign out when merge intent enqueue fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }));

    const { GET } = await import('@/app/auth/oauth/start/route');
    const response = await GET(
      new NextRequest(
        'http://localhost/auth/oauth/start?provider=google&intent=link-merge&anonymous_user_id=anon-1&next=/app/reports&signed_token=leaked',
      ),
    );

    expect(response.status).toBe(302);
    const location = new URL(response.headers.get('location') ?? '');
    expect(location.pathname).toBe('/auth/failure');
    expect(location.searchParams.get('reason')).toBe('merge_unavailable');
    expect(location.searchParams.get('provider')).toBe('google');
    expect(location.searchParams.get('next')).toBe('/app/reports');
    expect(supabaseMocks.signOut).not.toHaveBeenCalled();
    expect(cookieHeader(response)).not.toContain('leaked');
  });

  it('redirects to failure and clears callback cookies when OAuth URL generation fails', async () => {
    supabaseMocks.linkIdentity.mockResolvedValueOnce({
      data: { url: null },
      error: { code: 'provider_not_enabled', message: 'provider disabled' },
    });

    const { GET } = await import('@/app/auth/oauth/start/route');
    const response = await GET(
      new NextRequest('http://localhost/auth/oauth/start?provider=google&intent=link'),
    );

    expect(response.status).toBe(302);
    expect(response.headers.get('location')).toBe(
      'http://localhost/auth/failure?reason=oauth_init_failed&provider=google',
    );
    expectCallbackCookiesExpired(response);
  });

  it('uses NEXT_PUBLIC_SITE_URL for callback redirect origin when configured', async () => {
    process.env.NEXT_PUBLIC_SITE_URL = 'https://www.jippin.example';
    supabaseMocks.signInWithOAuth.mockResolvedValueOnce({
      data: { url: 'https://supabase.test/auth/v1/authorize?provider=google' },
      error: null,
    });

    const { GET } = await import('@/app/auth/oauth/start/route');
    const response = await GET(
      new NextRequest('http://localhost/auth/oauth/start?provider=google&intent=signin&next=/app/reports'),
    );

    expect(response.status).toBe(302);
    expect(supabaseMocks.signInWithOAuth).toHaveBeenCalledWith(
      expect.objectContaining({
        options: expect.objectContaining({
          redirectTo: 'https://www.jippin.example/auth/callback?next=%2Fapp%2Freports',
        }),
      }),
    );
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

    render(
      <AuthFailureView
        reason="identity_already_exists"
        provider="google"
        nextPath="/app/reports"
      />,
    );

    expect(screen.getByRole('heading', { name: '이미 가입된 계정이 있습니다' })).toBeVisible();
    expect(screen.getByRole('button', { name: '예, 옮기고 로그인' })).toBeVisible();
    expect(screen.getByRole('combobox')).toHaveValue('google');
  });
});

describe('/auth/terms page', () => {
  it('submits enabled terms acceptance and redirects to the safe next path', async () => {
    process.env.NEXT_PUBLIC_AUTH_TERMS_ACCEPT_ENABLED = 'true';
    browserSupabaseMocks.getSession.mockResolvedValueOnce({
      data: { session: { access_token: 'supabase-access-token' } },
      error: null,
    });
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal('fetch', fetchMock);
    const { TermsGate } = await import('@/app/auth/terms/terms-gate');

    render(<TermsGate nextPath="/app/reports" />);

    fireEvent.click(screen.getByLabelText('서비스 이용약관에 동의합니다'));
    fireEvent.click(screen.getByLabelText('개인정보 처리방침에 동의합니다'));
    fireEvent.click(screen.getByRole('button', { name: '동의하고 /app/reports로 이동' }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        'http://api.test/auth/terms/accept',
        expect.objectContaining({
          method: 'POST',
          credentials: 'include',
          headers: expect.objectContaining({
            authorization: 'Bearer supabase-access-token',
          }),
          body: JSON.stringify({
            consents: [
              { term_id: 'service_terms', agreed: true },
              { term_id: 'privacy_policy', agreed: true },
            ],
          }),
        }),
      );
    });
    expect(routerMocks.replace).toHaveBeenCalledWith('/app/reports');
  });
});

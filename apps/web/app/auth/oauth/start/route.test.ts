/**
 * Unit test — PKCE verifier cookie preservation through OAuth start redirect (CMP-580 / R2 + R10).
 *
 * `@supabase/ssr` 의 `createServerClient` 를 mock 하여 SDK 가 setAll 콜백으로 발급한
 * PKCE verifier cookie 가 단일 NextResponse 의 Set-Cookie 헤더에 보존되는지를 검증한다.
 *
 * 본 테스트가 깨지면 callback 의 `exchangeCodeForSession` 이 `auth/missing-code-verifier`
 * 로 실패하는 것과 등가 — 실 Supabase 없이 어댑터/응답 invariant 만 검증 (live OAuth 는 별도 트랙).
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { NextRequest } from 'next/server';

import { verifyFlowCookie } from '@/lib/flow-cookie';

interface CookiesToSet {
  name: string;
  value: string;
  options?: Record<string, unknown>;
}
interface ServerClientInit {
  cookies: { getAll: () => Array<{ name: string; value: string }>; setAll: (xs: CookiesToSet[]) => void };
}

// Vitest hoisted mock factory — createServerClient 가 import 되기 전에 자리 잡아야 한다.
const mocks = vi.hoisted(() => ({
  createServerClient: vi.fn(),
}));

vi.mock('@supabase/ssr', () => ({
  createServerClient: mocks.createServerClient,
}));

// env reader 는 모듈 평가 시 process.env 를 직접 읽으므로 import 전에 채워둔다.
process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co';
process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'test-anon-key';
process.env.SUPABASE_FLOW_COOKIE_SECRET = 'test-flow-cookie-secret';

const PKCE_COOKIE_NAME = 'sb-example-auth-token-code-verifier';
const PKCE_COOKIE_VALUE = 'pkce-verifier-12345';
const AUTHZ_URL = 'https://example.supabase.co/auth/v1/authorize?provider=google&state=abc';

function makeRequest(pathAndQuery: string): NextRequest {
  // NextRequest 를 직접 인스턴스화하기 보다 GET handler 가 실제 사용하는 메서드만 stub.
  const url = new URL(`http://localhost:3000${pathAndQuery}`);
  const cookieStore: Array<{ name: string; value: string }> = [];
  const request = {
    url: url.toString(),
    nextUrl: url,
    cookies: {
      getAll: () => cookieStore,
      get: (name: string) => cookieStore.find((c) => c.name === name),
    },
  } as unknown as NextRequest;
  return request;
}

function setCookieValues(response: Response): string[] {
  return response.headers.getSetCookie?.() ?? response.headers.get('Set-Cookie')?.split(/,(?=\s*[^,;]+=)/g) ?? [];
}

function cookieValue(setCookies: string[], name: string): string | null {
  const prefix = `${name}=`;
  const cookie = setCookies.find((value) => value.startsWith(prefix));
  return cookie ? cookie.slice(prefix.length).split(';')[0] ?? null : null;
}

describe('GET /auth/oauth/start — PKCE cookie preservation (R2 + R10)', () => {
  beforeEach(() => {
    mocks.createServerClient.mockReset();
  });

  it('forwards PKCE verifier cookie set by SDK to the 302 response and never loses it', async () => {
    // Arrange — Supabase SDK 가 linkIdentity 안에서 setAll 을 호출해 PKCE verifier 를 발급하는 시나리오.
    mocks.createServerClient.mockImplementation((_url: string, _key: string, init: ServerClientInit) => {
      return {
        auth: {
          linkIdentity: vi.fn().mockImplementation(async () => {
            init.cookies.setAll([
              {
                name: PKCE_COOKIE_NAME,
                value: PKCE_COOKIE_VALUE,
                options: { httpOnly: true, secure: true, sameSite: 'lax', path: '/', maxAge: 600 },
              },
            ]);
            return { data: { url: AUTHZ_URL, provider: 'google' }, error: null };
          }),
          signInWithOAuth: vi.fn(),
          signOut: vi.fn(),
        },
      };
    });

    const { GET } = await import('./route');
    const request = makeRequest('/auth/oauth/start?provider=google&intent=link');

    // Act
    const response = await GET(request);

    // Assert — 302 + Location 보존 + PKCE verifier cookie 가 응답에 부착.
    expect(response.status).toBe(302);
    expect(response.headers.get('Location')).toBe(AUTHZ_URL);

    const allSetCookies = setCookieValues(response);
    const setCookieJoined = allSetCookies.join('\n');
    expect(setCookieJoined).toMatch(new RegExp(`(?:^|\\n)${PKCE_COOKIE_NAME}=${PKCE_COOKIE_VALUE}`));
    const flowCookie = cookieValue(allSetCookies, 'jippin_oauth_provider');
    expect(flowCookie).not.toBeNull();
    const verified = verifyFlowCookie(decodeURIComponent(flowCookie ?? ''));
    expect(verified).toEqual(
      expect.objectContaining({
        ok: true,
        payload: expect.objectContaining({ provider: 'google', supabase_provider: 'google', intent: 'link' }),
      }),
    );
    // flow context cookie 는 callback path 로만 좁혀져 있어야 한다.
    expect(setCookieJoined).toMatch(/Path=\/auth\/callback/);
  });

  it('preserves a safe next path on the Supabase callback redirectTo URL', async () => {
    const linkIdentity = vi.fn().mockResolvedValue({ data: { url: AUTHZ_URL, provider: 'google' }, error: null });
    mocks.createServerClient.mockImplementation(() => ({
      auth: {
        linkIdentity,
        signInWithOAuth: vi.fn(),
        signOut: vi.fn(),
      },
    }));

    const { GET } = await import('./route');
    const response = await GET(makeRequest('/auth/oauth/start?provider=google&intent=link&next=/app/consult?draft=1'));

    expect(response.status).toBe(302);
    expect(linkIdentity).toHaveBeenCalledWith({
      provider: 'google',
      options: {
        redirectTo: 'http://localhost:3000/auth/callback?intent=link&next=%2Fapp%2Fconsult%3Fdraft%3D1',
        skipBrowserRedirect: true,
      },
    });
  });

  it('preserves the legacy anonymous user id on the Supabase callback redirectTo URL', async () => {
    const linkIdentity = vi.fn().mockResolvedValue({ data: { url: AUTHZ_URL, provider: 'google' }, error: null });
    mocks.createServerClient.mockImplementation(() => ({
      auth: {
        linkIdentity,
        signInWithOAuth: vi.fn(),
        signOut: vi.fn(),
      },
    }));

    const { GET } = await import('./route');
    const anonymousUserId = '0f5f8f33-7f55-48e8-9bf1-1bda6e8db91d';
    const response = await GET(
      makeRequest(`/auth/oauth/start?provider=google&intent=link&anonymous_user_id=${anonymousUserId}`),
    );

    expect(response.status).toBe(302);
    expect(linkIdentity).toHaveBeenCalledWith({
      provider: 'google',
      options: {
        redirectTo: `http://localhost:3000/auth/callback?intent=link&anonymous_user_id=${anonymousUserId}`,
        skipBrowserRedirect: true,
      },
    });
  });

  it('drops non-UUID anonymous user ids before building redirectTo', async () => {
    const linkIdentity = vi.fn().mockResolvedValue({ data: { url: AUTHZ_URL, provider: 'google' }, error: null });
    mocks.createServerClient.mockImplementation(() => ({
      auth: {
        linkIdentity,
        signInWithOAuth: vi.fn(),
        signOut: vi.fn(),
      },
    }));

    const { GET } = await import('./route');
    const longInvalidId = 'x'.repeat(4096);
    const response = await GET(
      makeRequest(`/auth/oauth/start?provider=google&intent=link&anonymous_user_id=${longInvalidId}`),
    );

    expect(response.status).toBe(302);
    expect(linkIdentity).toHaveBeenCalledWith({
      provider: 'google',
      options: {
        redirectTo: 'http://localhost:3000/auth/callback?intent=link',
        skipBrowserRedirect: true,
      },
    });
  });

  it('drops unsafe backslash next paths before building redirectTo', async () => {
    const linkIdentity = vi.fn().mockResolvedValue({ data: { url: AUTHZ_URL, provider: 'google' }, error: null });
    mocks.createServerClient.mockImplementation(() => ({
      auth: {
        linkIdentity,
        signInWithOAuth: vi.fn(),
        signOut: vi.fn(),
      },
    }));

    const { GET } = await import('./route');
    const response = await GET(makeRequest('/auth/oauth/start?provider=google&intent=link&next=/\\evil.com'));

    expect(response.status).toBe(302);
    expect(linkIdentity).toHaveBeenCalledWith({
      provider: 'google',
      options: {
        redirectTo: 'http://localhost:3000/auth/callback?intent=link',
        skipBrowserRedirect: true,
      },
    });
  });

  it('uses signInWithOAuth (not linkIdentity) for intent=signin and still preserves PKCE cookie', async () => {
    mocks.createServerClient.mockImplementation((_url: string, _key: string, init: ServerClientInit) => {
      const linkIdentity = vi.fn();
      const signInWithOAuth = vi.fn().mockImplementation(async () => {
        init.cookies.setAll([
          {
            name: PKCE_COOKIE_NAME,
            value: PKCE_COOKIE_VALUE,
            options: { httpOnly: true, secure: true, sameSite: 'lax', path: '/', maxAge: 600 },
          },
        ]);
        return { data: { url: AUTHZ_URL, provider: 'kakao' }, error: null };
      });
      return {
        auth: { linkIdentity, signInWithOAuth, signOut: vi.fn() },
      };
    });

    const { GET } = await import('./route');
    const request = makeRequest('/auth/oauth/start?provider=kakao&intent=signin');
    const response = await GET(request);

    expect(response.status).toBe(302);
    const allSetCookies = setCookieValues(response);
    expect(allSetCookies.join('\n')).toContain(PKCE_COOKIE_NAME);
    const flowCookie = cookieValue(allSetCookies, 'jippin_oauth_provider');
    const verified = verifyFlowCookie(decodeURIComponent(flowCookie ?? ''));
    expect(verified).toEqual(
      expect.objectContaining({
        ok: true,
        payload: expect.objectContaining({ provider: 'kakao', supabase_provider: 'custom:kakao', intent: 'signin' }),
      }),
    );
  });

  it('fails closed for intent=link-merge when merge intent state cannot be created', async () => {
    const { GET } = await import('./route');
    const response = await GET(makeRequest('/auth/oauth/start?provider=naver&intent=link-merge'));

    expect(response.status).toBe(302);
    expect(response.headers.get('Location')).toBe('http://localhost:3000/auth/failure?reason=merge_unavailable&provider=naver');
    expect(setCookieValues(response).join('\n')).toContain('jippin_oauth_provider=');
  });

  it('rejects unknown provider with 400', async () => {
    mocks.createServerClient.mockImplementation(() => ({
      auth: { linkIdentity: vi.fn(), signInWithOAuth: vi.fn(), signOut: vi.fn() },
    }));
    const { GET } = await import('./route');
    const response = await GET(makeRequest('/auth/oauth/start?provider=evil&intent=link'));
    expect(response.status).toBe(400);
  });

  it('rejects missing or invalid intent with 400 instead of defaulting to link', async () => {
    mocks.createServerClient.mockImplementation(() => ({
      auth: { linkIdentity: vi.fn(), signInWithOAuth: vi.fn(), signOut: vi.fn() },
    }));
    const { GET } = await import('./route');
    const missing = await GET(makeRequest('/auth/oauth/start?provider=google'));
    const typo = await GET(makeRequest('/auth/oauth/start?provider=google&intent=singin'));

    expect(missing.status).toBe(400);
    expect(typo.status).toBe(400);
    expect(mocks.createServerClient).not.toHaveBeenCalled();
  });

  it('redirects to failure when SDK fails to mint OAuth URL and expires flow cookies', async () => {
    mocks.createServerClient.mockImplementation((_url: string, _key: string, init: ServerClientInit) => ({
      auth: {
        linkIdentity: vi.fn().mockImplementation(async () => {
          init.cookies.setAll([
            {
              name: PKCE_COOKIE_NAME,
              value: PKCE_COOKIE_VALUE,
              options: { httpOnly: true, secure: true, sameSite: 'lax', path: '/', maxAge: 600 },
            },
          ]);
          return {
            data: null,
            error: { code: 'provider_not_enabled', message: 'Provider is not enabled' },
          };
        }),
        signInWithOAuth: vi.fn(),
        signOut: vi.fn(),
      },
    }));
    const { GET } = await import('./route');
    const response = await GET(makeRequest('/auth/oauth/start?provider=google&intent=link'));
    expect(response.status).toBe(302);
    expect(response.headers.get('Location')).toBe('http://localhost:3000/auth/failure?reason=oauth_init_failed&provider=google');
    expect(setCookieValues(response).join('\n')).toContain('jippin_oauth_provider=');
  });

  it('redirects to failure when SDK throws and expires flow cookies', async () => {
    mocks.createServerClient.mockImplementation(() => ({
      auth: {
        linkIdentity: vi.fn().mockRejectedValue(new Error('oauth provider unavailable')),
        signInWithOAuth: vi.fn(),
        signOut: vi.fn(),
      },
    }));
    const { GET } = await import('./route');
    const response = await GET(makeRequest('/auth/oauth/start?provider=google&intent=link'));
    expect(response.status).toBe(302);
    expect(response.headers.get('Location')).toBe('http://localhost:3000/auth/failure?reason=oauth_init_failed&provider=google');
    expect(setCookieValues(response).join('\n')).toContain('jippin_oauth_provider=');
  });
});

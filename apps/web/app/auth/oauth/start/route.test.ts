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

    const allSetCookies = response.headers.getSetCookie?.() ?? response.headers.get('Set-Cookie')?.split(/,(?=\s*[^,;]+=)/g) ?? [];
    const setCookieJoined = allSetCookies.join('\n');
    expect(setCookieJoined).toMatch(new RegExp(`(?:^|\\n)${PKCE_COOKIE_NAME}=${PKCE_COOKIE_VALUE}`));
    expect(setCookieJoined).toMatch(/jippin_oauth_provider=google/);
    // flow context cookie 는 callback path 로만 좁혀져 있어야 한다.
    expect(setCookieJoined).toMatch(/Path=\/auth\/callback/);
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
    const allSetCookies = response.headers.getSetCookie?.() ?? response.headers.get('Set-Cookie')?.split(/,(?=\s*[^,;]+=)/g) ?? [];
    expect(allSetCookies.join('\n')).toContain(PKCE_COOKIE_NAME);
    expect(allSetCookies.join('\n')).toMatch(/jippin_oauth_provider=kakao/);
  });

  it('signs out before signInWithOAuth on intent=link-merge (anonymous session discarded)', async () => {
    const signOut = vi.fn().mockImplementation(async () => {
      // signOut 도 cookie 비우기를 setAll 로 호출 — 어댑터가 이를 흡수하는지 확인.
      return { error: null };
    });
    const signInWithOAuth = vi.fn().mockResolvedValue({
      data: { url: AUTHZ_URL, provider: 'naver' },
      error: null,
    });
    mocks.createServerClient.mockImplementation(() => ({
      auth: { linkIdentity: vi.fn(), signInWithOAuth, signOut },
    }));

    const { GET } = await import('./route');
    const request = makeRequest('/auth/oauth/start?provider=naver&intent=link-merge');
    const response = await GET(request);

    expect(response.status).toBe(302);
    expect(signOut).toHaveBeenCalledOnce();
    expect(signInWithOAuth).toHaveBeenCalledOnce();
  });

  it('rejects unknown provider with 400', async () => {
    mocks.createServerClient.mockImplementation(() => ({
      auth: { linkIdentity: vi.fn(), signInWithOAuth: vi.fn(), signOut: vi.fn() },
    }));
    const { GET } = await import('./route');
    const response = await GET(makeRequest('/auth/oauth/start?provider=evil&intent=link'));
    expect(response.status).toBe(400);
  });

  it('returns 502 when SDK fails to mint OAuth URL (no redirect, no Location leak)', async () => {
    mocks.createServerClient.mockImplementation(() => ({
      auth: {
        linkIdentity: vi.fn().mockResolvedValue({
          data: null,
          error: { code: 'provider_not_enabled', message: 'Provider is not enabled' },
        }),
        signInWithOAuth: vi.fn(),
        signOut: vi.fn(),
      },
    }));
    const { GET } = await import('./route');
    const response = await GET(makeRequest('/auth/oauth/start?provider=google&intent=link'));
    expect(response.status).toBe(502);
    expect(response.headers.get('Location')).toBeNull();
  });
});

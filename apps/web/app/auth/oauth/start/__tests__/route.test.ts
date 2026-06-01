import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { GET } from '../route';

function makeRequest(query: Record<string, string>): NextRequest {
  const url = new URL('http://localhost:3000/auth/oauth/start');
  for (const [k, v] of Object.entries(query)) {
    url.searchParams.set(k, v);
  }
  return new NextRequest(url);
}

const ENV_KEYS = ['API_PUBLIC_BASE_URL', 'NEXT_PUBLIC_API_BASE_URL'] as const;

describe('GET /auth/oauth/start — provider whitelist guard', () => {
  const savedEnv: Partial<Record<(typeof ENV_KEYS)[number], string | undefined>> = {};

  beforeEach(() => {
    for (const key of ENV_KEYS) savedEnv[key] = process.env[key];
    // route 단위 테스트는 browser-reachable URL 을 명시적으로 지정 — Docker 내부 host
    // 케이스는 별도 describe 가 검증.
    process.env.API_PUBLIC_BASE_URL = 'http://localhost:8000';
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
  });

  afterEach(() => {
    for (const key of ENV_KEYS) {
      if (savedEnv[key] === undefined) delete process.env[key];
      else process.env[key] = savedEnv[key];
    }
  });

  it('rejects non-whitelisted provider with 400 + PROVIDER_NOT_ALLOWED', async () => {
    const res = GET(makeRequest({ provider: 'facebook' }));
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error.code).toBe('PROVIDER_NOT_ALLOWED');
  });

  it('rejects email/password/magic link attempts with 400', async () => {
    for (const provider of ['email', 'password', 'magic_link', 'otp', 'sms']) {
      const res = GET(makeRequest({ provider }));
      expect(res.status).toBe(400);
      const body = await res.json();
      expect(body.error.code).toBe('PROVIDER_NOT_ALLOWED');
    }
  });

  it('rejects missing provider param with 400', async () => {
    const res = GET(makeRequest({}));
    expect(res.status).toBe(400);
  });

  it.each(['google', 'kakao', 'naver'])(
    'redirects allowed provider %s to backend /auth/{provider}/start (302)',
    (provider) => {
      const res = GET(
        makeRequest({
          provider,
          return_url: 'http://localhost:3000/',
          anonymous_user_id: '00000000-0000-0000-0000-000000000000'
        })
      );
      expect(res.status).toBe(302);
      const location = res.headers.get('location');
      expect(location).not.toBeNull();
      const target = new URL(location!);
      expect(target.pathname).toBe(`/auth/${provider}/start`);
      expect(target.searchParams.get('return_url')).toBe('http://localhost:3000/');
      expect(target.searchParams.get('anonymous_user_id')).toBe(
        '00000000-0000-0000-0000-000000000000'
      );
    }
  );

  it('does not forward unrecognized query params (defense in depth)', () => {
    const res = GET(
      makeRequest({
        provider: 'google',
        return_url: 'http://localhost:3000/',
        // attacker-controlled noise
        password: 'pwn',
        email: 'attacker@example.com',
        next: '//evil.com'
      })
    );
    expect(res.status).toBe(302);
    const target = new URL(res.headers.get('location')!);
    expect(target.searchParams.get('password')).toBeNull();
    expect(target.searchParams.get('email')).toBeNull();
    expect(target.searchParams.get('next')).toBeNull();
  });
});

describe('GET /auth/oauth/start — browser-reachable URL guard (round-3)', () => {
  const savedEnv: Partial<Record<(typeof ENV_KEYS)[number], string | undefined>> = {};

  beforeEach(() => {
    for (const key of ENV_KEYS) savedEnv[key] = process.env[key];
  });

  afterEach(() => {
    for (const key of ENV_KEYS) {
      if (savedEnv[key] === undefined) delete process.env[key];
      else process.env[key] = savedEnv[key];
    }
  });

  it('returns 500 OAUTH_BASE_URL_MISCONFIGURED when only Docker internal host is set', async () => {
    delete process.env.API_PUBLIC_BASE_URL;
    process.env.NEXT_PUBLIC_API_BASE_URL = 'http://api:8000';

    const res = GET(makeRequest({ provider: 'google' }));
    expect(res.status).toBe(500);
    const body = await res.json();
    expect(body.error.code).toBe('OAUTH_BASE_URL_MISCONFIGURED');
  });

  it('prefers API_PUBLIC_BASE_URL over NEXT_PUBLIC_API_BASE_URL for 302 Location', () => {
    process.env.API_PUBLIC_BASE_URL = 'https://api.jippin.example';
    process.env.NEXT_PUBLIC_API_BASE_URL = 'http://api:8000';

    const res = GET(makeRequest({ provider: 'naver' }));
    expect(res.status).toBe(302);
    const location = res.headers.get('location')!;
    expect(location.startsWith('https://api.jippin.example/auth/naver/start')).toBe(true);
    expect(location).not.toContain('api:8000');
  });

  it('falls back to NEXT_PUBLIC_API_BASE_URL when it is browser-reachable', () => {
    delete process.env.API_PUBLIC_BASE_URL;
    process.env.NEXT_PUBLIC_API_BASE_URL = 'http://localhost:8000';

    const res = GET(makeRequest({ provider: 'kakao' }));
    expect(res.status).toBe(302);
    const location = res.headers.get('location')!;
    expect(location.startsWith('http://localhost:8000/auth/kakao/start')).toBe(true);
  });

  it('returns 500 when API_PUBLIC_BASE_URL itself is a Docker internal host (operator misconfig)', async () => {
    process.env.API_PUBLIC_BASE_URL = 'http://api:8000';
    delete process.env.NEXT_PUBLIC_API_BASE_URL;

    const res = GET(makeRequest({ provider: 'google' }));
    expect(res.status).toBe(500);
    const body = await res.json();
    expect(body.error.code).toBe('OAUTH_BASE_URL_MISCONFIGURED');
  });
});

import { NextRequest } from 'next/server';
import { describe, expect, it } from 'vitest';

import { GET } from '../route';

function makeRequest(query: Record<string, string>): NextRequest {
  const url = new URL('http://localhost:3000/auth/oauth/start');
  for (const [k, v] of Object.entries(query)) {
    url.searchParams.set(k, v);
  }
  return new NextRequest(url);
}

describe('GET /auth/oauth/start — provider whitelist guard', () => {
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

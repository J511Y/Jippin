/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { getOrCreateAnonymousUserId } from '@/lib/anonymous-user';

describe('getOrCreateAnonymousUserId — same-origin BFF (CMP-584 round-5)', () => {
  const ENV_KEY = 'NEXT_PUBLIC_API_BASE_URL';
  let savedEnv: string | undefined;
  const fetchSpy = vi.fn();

  beforeEach(() => {
    savedEnv = process.env[ENV_KEY];
    // Compose-like: NEXT_PUBLIC_API_BASE_URL is the Docker-only host.
    process.env[ENV_KEY] = 'http://api:8000';
    window.localStorage.clear();
    fetchSpy.mockReset();
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    if (savedEnv === undefined) delete process.env[ENV_KEY];
    else process.env[ENV_KEY] = savedEnv;
    vi.unstubAllGlobals();
  });

  it('calls the same-origin BFF path, NOT NEXT_PUBLIC_API_BASE_URL', async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          anonymous_user_id: '33333333-3333-3333-3333-333333333333',
          reused: false
        }),
        { status: 200, headers: { 'content-type': 'application/json' } }
      )
    );

    const id = await getOrCreateAnonymousUserId();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const calledUrl = String(fetchSpy.mock.calls[0]![0]);
    // 정합 — Docker-only hostname 으로 가지 않는다.
    expect(calledUrl).not.toMatch(/api:8000/);
    expect(calledUrl).not.toMatch(/^https?:\/\//);
    expect(calledUrl).toBe('/auth/anonymous-users');
    expect(id).toBe('33333333-3333-3333-3333-333333333333');
  });

  it('persists the resolved ID to localStorage and replays it on the next call', async () => {
    fetchSpy
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            anonymous_user_id: '44444444-4444-4444-4444-444444444444',
            reused: false
          }),
          { status: 200, headers: { 'content-type': 'application/json' } }
        )
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            anonymous_user_id: '44444444-4444-4444-4444-444444444444',
            reused: true
          }),
          { status: 200, headers: { 'content-type': 'application/json' } }
        )
      );

    await getOrCreateAnonymousUserId();
    await getOrCreateAnonymousUserId();

    const secondBody = JSON.parse(
      (fetchSpy.mock.calls[1]![1] as RequestInit).body as string
    );
    expect(secondBody).toEqual({
      existing_anonymous_user_id: '44444444-4444-4444-4444-444444444444'
    });
  });

  it('throws on non-OK upstream', async () => {
    fetchSpy.mockResolvedValueOnce(new Response('boom', { status: 500 }));
    await expect(getOrCreateAnonymousUserId()).rejects.toThrow(/500/);
  });
});

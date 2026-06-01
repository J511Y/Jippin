import { describe, it, expect, vi } from 'vitest';
import {
  evaluateAnonymousGate,
  type AnonymousGateConfig,
} from '@/lib/anonymous-gate';
import {
  persistKakaoSyncConsent,
  KakaoSyncAuditError,
  type KakaoSyncAuditInput,
} from '@/lib/kakao-sync-audit';
import {
  resolveKakaoProviderId,
  toSupabaseProviderId,
  isKakaoProvider,
} from '@/lib/oauth-providers';

const BASE_GATE: AnonymousGateConfig = {
  requireExplicitIntent: true,
  requireChallengeToken: false,
  minIntervalMs: 0,
  maxAttemptsPerSession: 0,
};

class MemoryStorage {
  private readonly map = new Map<string, string>();
  getItem(key: string): string | null {
    return this.map.has(key) ? (this.map.get(key) as string) : null;
  }
  setItem(key: string, value: string): void {
    this.map.set(key, value);
  }
}

describe('CMP-581 anonymous-gate (R4)', () => {
  it('blocks bootstrap when explicit intent is required and reason is missing', async () => {
    const decision = await evaluateAnonymousGate(
      { ...BASE_GATE, requireExplicitIntent: true },
      // @ts-expect-error — simulate a passive layout-mount call that omits the explicit reason.
      { reason: 'layout_mount' },
    );
    expect(decision.allowed).toBe(false);
    if (!decision.allowed) {
      expect(decision.reason).toBe('explicit_intent_required');
    }
  });

  it('allows bootstrap once explicit intent is supplied', async () => {
    const decision = await evaluateAnonymousGate(
      { ...BASE_GATE, requireExplicitIntent: true },
      { reason: 'explicit_intent', storage: new MemoryStorage() },
    );
    expect(decision.allowed).toBe(true);
  });

  it('enforces challenge token when requireChallengeToken is true', async () => {
    const missing = await evaluateAnonymousGate(
      { ...BASE_GATE, requireChallengeToken: true },
      { reason: 'challenge', storage: new MemoryStorage() },
    );
    expect(missing.allowed).toBe(false);
    if (!missing.allowed) expect(missing.reason).toBe('challenge_token_required');

    const verify = vi.fn().mockResolvedValue(false);
    const invalid = await evaluateAnonymousGate(
      { ...BASE_GATE, requireChallengeToken: true, verifyChallengeToken: verify },
      { reason: 'challenge', challengeToken: 'bad', storage: new MemoryStorage() },
    );
    expect(verify).toHaveBeenCalledWith('bad');
    expect(invalid.allowed).toBe(false);
    if (!invalid.allowed) expect(invalid.reason).toBe('challenge_token_invalid');
  });

  it('rate-limits repeat attempts within minIntervalMs', async () => {
    const storage = new MemoryStorage();
    const config: AnonymousGateConfig = {
      ...BASE_GATE,
      requireExplicitIntent: false,
      minIntervalMs: 60_000,
    };
    const first = await evaluateAnonymousGate(config, {
      reason: 'explicit_intent',
      storage,
      now: () => 1_000,
    });
    expect(first.allowed).toBe(true);
    const second = await evaluateAnonymousGate(config, {
      reason: 'explicit_intent',
      storage,
      now: () => 30_000,
    });
    expect(second.allowed).toBe(false);
    if (!second.allowed) expect(second.reason).toBe('rate_limited');
  });
});

describe('CMP-581 kakao-sync-audit (R3, R13)', () => {
  const input: KakaoSyncAuditInput = {
    supabaseUserId: 'user-1',
    linkedProvider: 'kakao',
    supabaseAccessToken: 'supabase-jwt',
    providerAccessToken: 'kakao-oauth-access-token',
    providerRefreshToken: null,
  };

  it('R3: sends provider_access_token (not id_token) and omits id_token entirely', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } }),
    );
    await persistKakaoSyncConsent(input, {
      apiBaseUrl: 'http://api.test',
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('http://api.test/auth/terms/kakao-sync');
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer supabase-jwt');
    expect(headers['Content-Type']).toBe('application/json');
    const body = JSON.parse(String(init.body));
    expect(body).toEqual({
      supabase_user_id: 'user-1',
      linked_provider: 'kakao',
      provider_access_token: 'kakao-oauth-access-token',
      provider_refresh_token: null,
    });
    expect(body).not.toHaveProperty('id_token');
    expect(body).not.toHaveProperty('raw_kakao_payload');
  });

  it('R13: throws KakaoSyncAuditError on 4xx response (no silent success)', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response('{"error":"forbidden"}', { status: 403 }),
    );
    await expect(
      persistKakaoSyncConsent(input, {
        apiBaseUrl: 'http://api.test',
        fetchImpl: fetchImpl as unknown as typeof fetch,
      }),
    ).rejects.toBeInstanceOf(KakaoSyncAuditError);
  });

  it('R13: throws KakaoSyncAuditError on 5xx response and exposes status + body', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response('upstream timeout', { status: 502 }),
    );
    let caught: unknown;
    try {
      await persistKakaoSyncConsent(input, {
        apiBaseUrl: 'http://api.test',
        fetchImpl: fetchImpl as unknown as typeof fetch,
      });
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(KakaoSyncAuditError);
    if (caught instanceof KakaoSyncAuditError) {
      expect(caught.status).toBe(502);
      expect(caught.responseBody).toBe('upstream timeout');
    }
  });
});

describe('CMP-581 oauth-providers (R9)', () => {
  it('defaults to native kakao when env var is unset', () => {
    expect(resolveKakaoProviderId(undefined)).toBe('kakao');
    expect(resolveKakaoProviderId('')).toBe('kakao');
    expect(toSupabaseProviderId('kakao', undefined)).toBe('kakao');
  });

  it('switches kakao default to custom:kakao when env var matches console setup', () => {
    expect(resolveKakaoProviderId('custom:kakao')).toBe('custom:kakao');
    expect(toSupabaseProviderId('kakao', 'custom:kakao')).toBe('custom:kakao');
    expect(isKakaoProvider(toSupabaseProviderId('kakao', 'custom:kakao'))).toBe(true);
  });

  it('rejects invalid env values to fail loudly instead of sending a stale id', () => {
    expect(() => resolveKakaoProviderId('custom:other')).toThrow(/허용되지 않는 값/);
    expect(() => resolveKakaoProviderId('google')).toThrow(/허용되지 않는 값/);
  });

  it('keeps Naver pinned to custom:naver regardless of Kakao env', () => {
    expect(toSupabaseProviderId('naver', undefined)).toBe('custom:naver');
    expect(toSupabaseProviderId('naver', 'custom:kakao')).toBe('custom:naver');
    expect(toSupabaseProviderId('google', undefined)).toBe('google');
  });
});

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  evaluateAnonymousGate,
  withAnonymousSingleFlight,
  backfillLegacyAnonymousId,
  __resetAnonymousSingleFlightForTests,
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
import {
  evaluateOAuthIntentGuard,
  shouldIssueAnonymousSignIn,
  isOAuthIntent,
} from '@/lib/anonymous-signin-guard';

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

describe('CMP-581 anonymous-gate single-flight (round-11 race)', () => {
  beforeEach(() => {
    __resetAnonymousSingleFlightForTests();
  });

  it('dedupes concurrent calls into one in-flight promise', async () => {
    let resolveInner!: (value: string) => void;
    const invoke = vi.fn(
      () =>
        new Promise<string>((resolve) => {
          resolveInner = resolve;
        }),
    );
    const p1 = withAnonymousSingleFlight(invoke);
    const p2 = withAnonymousSingleFlight(invoke);
    expect(invoke).toHaveBeenCalledTimes(1);
    resolveInner('anon-user-id');
    await expect(p1).resolves.toBe('anon-user-id');
    await expect(p2).resolves.toBe('anon-user-id');
  });

  it('releases the slot after rejection so retries can re-enter', async () => {
    const failing = vi.fn(() => Promise.reject(new Error('boom')));
    await expect(withAnonymousSingleFlight(failing)).rejects.toThrow('boom');
    const succeeding = vi.fn(() => Promise.resolve('ok'));
    await expect(withAnonymousSingleFlight(succeeding)).resolves.toBe('ok');
    expect(failing).toHaveBeenCalledTimes(1);
    expect(succeeding).toHaveBeenCalledTimes(1);
  });
});

describe('CMP-581 legacy anonymous id backfill (round-11 item 2)', () => {
  it('does nothing when no legacy id is present', async () => {
    const update = vi.fn();
    const result = await backfillLegacyAnonymousId({
      currentMetadata: {},
      legacyAnonymousId: null,
      updateUserMetadata: update,
    });
    expect(result).toEqual({ backfilled: false, reason: 'no_legacy_id' });
    expect(update).not.toHaveBeenCalled();
  });

  it('does nothing when metadata already has legacy_anonymous_id', async () => {
    const update = vi.fn();
    const result = await backfillLegacyAnonymousId({
      currentMetadata: { legacy_anonymous_id: 'existing-uuid' },
      legacyAnonymousId: 'fresh-uuid',
      updateUserMetadata: update,
    });
    expect(result).toEqual({ backfilled: false, reason: 'already_backfilled' });
    expect(update).not.toHaveBeenCalled();
  });

  it('merges legacy id into existing metadata without dropping prior keys', async () => {
    const update = vi.fn().mockResolvedValue(undefined);
    const result = await backfillLegacyAnonymousId({
      currentMetadata: { display_name: 'Alice', other_key: 1 },
      legacyAnonymousId: 'legacy-uuid',
      updateUserMetadata: update,
    });
    expect(result).toEqual({ backfilled: true, legacyAnonymousId: 'legacy-uuid' });
    expect(update).toHaveBeenCalledWith({
      display_name: 'Alice',
      other_key: 1,
      legacy_anonymous_id: 'legacy-uuid',
    });
  });
});

describe('CMP-581 anonymous-signin-guard (round-11 items 2/6/7)', () => {
  it('blocks signin intent on anonymous session (item 2 — no new auth.users row)', () => {
    const decision = evaluateOAuthIntentGuard(
      { kind: 'anonymous', userId: 'anon-1' },
      'signin',
    );
    expect(decision.allowed).toBe(false);
    if (!decision.allowed) expect(decision.reason).toBe('signin_blocked_anonymous_session');
  });

  it('allows link intent on anonymous session (manual linkIdentity is the only conversion path)', () => {
    const decision = evaluateOAuthIntentGuard(
      { kind: 'anonymous', userId: 'anon-1' },
      'link',
    );
    expect(decision.allowed).toBe(true);
    if (decision.allowed) expect(decision.intent).toBe('link');
  });

  it('allows link-merge only inside the anonymous fallback ladder', () => {
    const merge = evaluateOAuthIntentGuard(
      { kind: 'anonymous', userId: 'anon-1' },
      'link-merge',
    );
    expect(merge.allowed).toBe(true);

    const fromAuthed = evaluateOAuthIntentGuard(
      { kind: 'authenticated', userId: 'u-1', isAnonymous: false },
      'link-merge',
    );
    expect(fromAuthed.allowed).toBe(false);
    if (!fromAuthed.allowed) {
      expect(fromAuthed.reason).toBe('link_merge_requires_anonymous_session');
    }
  });

  it('allows signin only when no session is present', () => {
    expect(evaluateOAuthIntentGuard({ kind: 'none' }, 'signin').allowed).toBe(true);
    const fromAuth = evaluateOAuthIntentGuard(
      { kind: 'authenticated', userId: 'u-1', isAnonymous: false },
      'link',
    );
    expect(fromAuth.allowed).toBe(false);
    if (!fromAuth.allowed) expect(fromAuth.reason).toBe('link_blocked_authenticated_session');
  });

  it('rejects unknown intents (defence in depth for BFF query parsing)', () => {
    expect(isOAuthIntent('signin')).toBe(true);
    expect(isOAuthIntent('register')).toBe(false);
    const decision = evaluateOAuthIntentGuard({ kind: 'none' }, 'register');
    expect(decision.allowed).toBe(false);
    if (!decision.allowed) expect(decision.reason).toBe('unknown_intent');
  });

  it('server-side anonymous sign-in only fires when no session exists (item 6)', () => {
    expect(shouldIssueAnonymousSignIn({ existingSessionUserId: null })).toBe(true);
    expect(shouldIssueAnonymousSignIn({ existingSessionUserId: 'u-1' })).toBe(false);
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

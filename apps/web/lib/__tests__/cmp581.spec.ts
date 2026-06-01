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
  KAKAO_SYNC_AUDIT_ENDPOINT_PATH,
  type KakaoSyncAuditInput,
} from '@/lib/kakao-sync-audit';
import {
  resolveKakaoProviderId,
  toSupabaseProviderId,
  isKakaoProvider,
  normalizeProviderForBackend,
} from '@/lib/oauth-providers';
import {
  evaluateOAuthIntentGuard,
  shouldIssueAnonymousSignIn,
  isOAuthIntent,
  evaluateAnonymousDiscardDecision,
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
    // round-15 — verifier is now required first, so existing token-missing case
    // must also supply a verifier; the verifier-missing case is covered in the
    // round-15 fix tests below.
    const verifyForMissingTokenCase = vi.fn();
    const missing = await evaluateAnonymousGate(
      {
        ...BASE_GATE,
        requireChallengeToken: true,
        verifyChallengeToken: verifyForMissingTokenCase,
      },
      { reason: 'challenge', storage: new MemoryStorage() },
    );
    expect(missing.allowed).toBe(false);
    if (!missing.allowed) expect(missing.reason).toBe('challenge_token_required');
    // verifier never invoked when token is missing.
    expect(verifyForMissingTokenCase).not.toHaveBeenCalled();

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
      enabled: true,
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
        enabled: true,
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
        enabled: true,
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

  it('round-11 item 1: stale id_token fields on caller input never leak into the request body', async () => {
    // Defence in depth — even if a careless caller spreads a Kakao SDK payload that
    // still carries id_token / oidc_token / raw_kakao_payload, the audit helper must
    // only forward the explicit fields it owns. Supabase Auth is the single id_token
    // verifier; the web/API layer never parses or forwards id_token.
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } }),
    );
    // The cast forces a careless caller's payload through the helper. The
    // structural-type fence below (`Keys` test) enforces the *type* boundary —
    // this test enforces the *runtime* boundary by proving the helper only
    // serializes its declared fields even when extras are present.
    const dirtyInput = {
      ...input,
      id_token: 'kakao-oidc-jwt',
      oidc_token: 'kakao-oidc-jwt',
      raw_kakao_payload: { id_token: 'kakao-oidc-jwt' },
    } as unknown as KakaoSyncAuditInput;
    await persistKakaoSyncConsent(dirtyInput, {
      apiBaseUrl: 'http://api.test',
      enabled: true,
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    const [, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(String(init.body));
    expect(body).not.toHaveProperty('id_token');
    expect(body).not.toHaveProperty('oidc_token');
    expect(body).not.toHaveProperty('raw_kakao_payload');
    // And the allowed path is preserved.
    expect(body.provider_access_token).toBe('kakao-oauth-access-token');
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer supabase-jwt');
  });

  it('round-11 item 1: KakaoSyncAuditInput type does not declare any id_token-like field', () => {
    // Compile-time fence: this block intentionally lists every forbidden key and
    // requires TypeScript to reject it. If a future refactor adds id_token to the
    // interface, this test fails to compile.
    type Keys = keyof KakaoSyncAuditInput;
    const _forbidden: ReadonlyArray<Exclude<'id_token' | 'oidc_token' | 'idToken' | 'raw_kakao_payload', Keys>> = [
      'id_token',
      'oidc_token',
      'idToken',
      'raw_kakao_payload',
    ];
    expect(_forbidden).toHaveLength(4);
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

  it('allows link-merge only inside the anonymous fallback ladder + with linkIdentity-attempted evidence', () => {
    // round-17 항목 3 — link-merge 는 normal linkIdentity 실패 evidence 가 함께
    // 제출되어야만 통과 (manual-link-first 우회 차단).
    const merge = evaluateOAuthIntentGuard(
      { kind: 'anonymous', userId: 'anon-1' },
      'link-merge',
      {
        linkMergePrerequisite: {
          linkIdentityAttempted: true,
          linkIdentityFailureReason: 'identity_already_exists',
        },
      },
    );
    expect(merge.allowed).toBe(true);

    const fromAuthed = evaluateOAuthIntentGuard(
      { kind: 'authenticated', userId: 'u-1', isAnonymous: false },
      'link-merge',
      {
        linkMergePrerequisite: {
          linkIdentityAttempted: true,
          linkIdentityFailureReason: 'identity_already_exists',
        },
      },
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

describe('CMP-581 anonymous-discard ordering (round-11 item 9 / signOut seal)', () => {
  it('blocks discard when link_identity fails — keep anonymous session for retry', () => {
    const decision = evaluateAnonymousDiscardDecision({
      stage: 'link_identity',
      outcome: 'failure',
    });
    expect(decision.allowed).toBe(false);
    if (!decision.allowed) {
      expect(decision.reason).toBe('discard_blocked_failure_outcome');
      // The detail must mention the data-loss risk so a callsite reviewing
      // logs / Sentry breadcrumbs sees *why* the discard was refused.
      expect(decision.detail).toContain('데이터 손실');
    }
  });

  it('blocks discard when merge_enqueue fails — Kakao audit failure path', () => {
    const decision = evaluateAnonymousDiscardDecision({
      stage: 'merge_enqueue',
      outcome: 'failure',
    });
    expect(decision.allowed).toBe(false);
    if (!decision.allowed) expect(decision.reason).toBe('discard_blocked_failure_outcome');
  });

  it('blocks discard while the outcome is still pending', () => {
    const decision = evaluateAnonymousDiscardDecision({
      stage: 'callback_finalize',
      outcome: 'pending',
    });
    expect(decision.allowed).toBe(false);
    if (!decision.allowed) expect(decision.reason).toBe('discard_blocked_pending_outcome');
  });

  it('allows discard only on success — Supabase has issued the new session', () => {
    const decision = evaluateAnonymousDiscardDecision({
      stage: 'callback_finalize',
      outcome: 'success',
    });
    expect(decision.allowed).toBe(true);
    if (decision.allowed) expect(decision.stage).toBe('callback_finalize');
  });

  it('rejects unknown outcomes (defence in depth for callback param parsing)', () => {
    const decision = evaluateAnonymousDiscardDecision({
      stage: 'link_identity',
      outcome: 'rolled_back',
    });
    expect(decision.allowed).toBe(false);
    if (!decision.allowed) expect(decision.reason).toBe('unknown_outcome');
  });
});

describe('CMP-581 anonymous-discard CSRF gate (round-11 item 16)', () => {
  it('required policy + matching tokens allows discard on success', () => {
    const decision = evaluateAnonymousDiscardDecision({
      stage: 'callback_finalize',
      outcome: 'success',
      csrf: {
        policy: 'required',
        providedToken: 'nonce-abc-123',
        expectedToken: 'nonce-abc-123',
      },
    });
    expect(decision.allowed).toBe(true);
  });

  it('required policy + missing providedToken blocks as csrf_token_missing', () => {
    const decision = evaluateAnonymousDiscardDecision({
      stage: 'callback_finalize',
      outcome: 'success',
      csrf: {
        policy: 'required',
        providedToken: null,
        expectedToken: 'nonce-abc-123',
      },
    });
    expect(decision.allowed).toBe(false);
    if (!decision.allowed) expect(decision.reason).toBe('csrf_token_missing');
  });

  it('required policy + empty expectedToken blocks as csrf_token_missing', () => {
    const decision = evaluateAnonymousDiscardDecision({
      stage: 'callback_finalize',
      outcome: 'success',
      csrf: {
        policy: 'required',
        providedToken: 'nonce-abc-123',
        expectedToken: '',
      },
    });
    expect(decision.allowed).toBe(false);
    if (!decision.allowed) expect(decision.reason).toBe('csrf_token_missing');
  });

  it('required policy + mismatched tokens blocks as csrf_token_mismatch (forge attempt)', () => {
    const decision = evaluateAnonymousDiscardDecision({
      stage: 'callback_finalize',
      outcome: 'success',
      csrf: {
        policy: 'required',
        providedToken: 'attacker-supplied',
        expectedToken: 'session-stored',
      },
    });
    expect(decision.allowed).toBe(false);
    if (!decision.allowed) {
      expect(decision.reason).toBe('csrf_token_mismatch');
      // The detail must surface the forge-attempt framing so operators see
      // the security intent in Sentry breadcrumbs.
      expect(decision.detail).toContain('위조');
    }
  });

  it('CSRF check runs before outcome — mismatch blocks even on success outcome', () => {
    // Without CSRF: success → allow. With CSRF mismatch: blocked despite success.
    const allowed = evaluateAnonymousDiscardDecision({
      stage: 'callback_finalize',
      outcome: 'success',
    });
    expect(allowed.allowed).toBe(true);

    const blocked = evaluateAnonymousDiscardDecision({
      stage: 'callback_finalize',
      outcome: 'success',
      csrf: { policy: 'required', providedToken: 'a', expectedToken: 'b' },
    });
    expect(blocked.allowed).toBe(false);
    if (!blocked.allowed) expect(blocked.reason).toBe('csrf_token_mismatch');
  });

  it('session_cookie_only policy skips CSRF and falls back to outcome judgment', () => {
    const success = evaluateAnonymousDiscardDecision({
      stage: 'callback_finalize',
      outcome: 'success',
      csrf: { policy: 'session_cookie_only' },
    });
    expect(success.allowed).toBe(true);

    const failure = evaluateAnonymousDiscardDecision({
      stage: 'callback_finalize',
      outcome: 'failure',
      csrf: { policy: 'session_cookie_only' },
    });
    expect(failure.allowed).toBe(false);
    if (!failure.allowed) expect(failure.reason).toBe('discard_blocked_failure_outcome');
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

describe('CMP-581 round-12 review fixes', () => {
  it('item 1: oauth-providers.ts references process.env.NEXT_PUBLIC_SUPABASE_KAKAO_PROVIDER_ID via direct member access (Next.js client-bundle inlining)', async () => {
    // Static guard — Next.js inlines `process.env.NEXT_PUBLIC_*` at build time ONLY
    // when the source references it via direct member access. Computed-property
    // forms (`process.env[varName]`) survive into the client bundle as undefined,
    // so this test reads the source as a string and asserts the literal access
    // pattern is present.
    const fs = await import('node:fs');
    const path = await import('node:path');
    const sourcePath = path.resolve(__dirname, '..', 'oauth-providers.ts');
    const source = fs.readFileSync(sourcePath, 'utf8');
    expect(source).toContain('process.env.NEXT_PUBLIC_SUPABASE_KAKAO_PROVIDER_ID');
    // And the forbidden computed-property form must not be present.
    expect(source).not.toMatch(/process\.env\[[^\]]*KAKAO/);
  });

  it('item 2: authenticated session + signin intent is blocked (no new OAuth flow on logged-in users)', () => {
    const decision = evaluateOAuthIntentGuard(
      { kind: 'authenticated', userId: 'u-1', isAnonymous: false },
      'signin',
    );
    expect(decision.allowed).toBe(false);
    if (!decision.allowed) {
      expect(decision.reason).toBe('signin_blocked_authenticated_session');
      expect(decision.detail).toContain('signOut');
    }
  });

  it('item 3: anonymous gate returns storage_unavailable when sessionStorage.setItem throws (quota / private mode)', async () => {
    const throwingStorage: Pick<Storage, 'getItem' | 'setItem'> = {
      getItem: () => null,
      setItem: () => {
        throw new DOMException('QuotaExceededError', 'QuotaExceededError');
      },
    };
    const decision = await evaluateAnonymousGate(
      {
        requireExplicitIntent: false,
        requireChallengeToken: false,
        minIntervalMs: 60_000,
        maxAttemptsPerSession: 5,
      },
      { reason: 'explicit_intent', storage: throwingStorage, now: () => 1_000 },
    );
    expect(decision.allowed).toBe(false);
    if (!decision.allowed) {
      expect(decision.reason).toBe('storage_unavailable');
      expect(decision.detail).toContain('setItem');
    }
  });

  it('item 4: Kakao Sync audit payload normalizes custom:kakao SDK id to backend enum "kakao"', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response('{}', { status: 200 }),
    );
    await persistKakaoSyncConsent(
      {
        supabaseUserId: 'user-x',
        linkedProvider: 'custom:kakao',
        supabaseAccessToken: 'jwt',
        providerAccessToken: 'access-tok',
        providerRefreshToken: null,
      },
      {
        apiBaseUrl: 'http://api.test',
        enabled: true,
        fetchImpl: fetchImpl as unknown as typeof fetch,
      },
    );
    const [, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(String(init.body));
    // SDK passed 'custom:kakao' but wire payload must be normalized to 'kakao'.
    expect(body.linked_provider).toBe('kakao');
  });

  it('item 4 (sister): normalizeProviderForBackend collapses Supabase SDK ids to backend enum', () => {
    expect(normalizeProviderForBackend('kakao')).toBe('kakao');
    expect(normalizeProviderForBackend('custom:kakao')).toBe('kakao');
    expect(normalizeProviderForBackend('naver')).toBe('naver');
    expect(normalizeProviderForBackend('custom:naver')).toBe('naver');
    expect(normalizeProviderForBackend('google')).toBe('google');
    expect(() => normalizeProviderForBackend('github')).toThrow(/normalize/);
  });

  it('item 5: audit helper hard-fails when enabled flag is missing (endpoint not yet shipped)', async () => {
    const fetchImpl = vi.fn();
    let caught: unknown;
    try {
      await persistKakaoSyncConsent(
        {
          supabaseUserId: 'user-1',
          linkedProvider: 'kakao',
          supabaseAccessToken: 'jwt',
          providerAccessToken: 'tok',
          providerRefreshToken: null,
        },
        { apiBaseUrl: 'http://api.test', fetchImpl: fetchImpl as unknown as typeof fetch },
      );
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(KakaoSyncAuditError);
    if (caught instanceof KakaoSyncAuditError) {
      expect(caught.code).toBe('endpoint_not_enabled');
      expect(caught.status).toBe(0);
    }
    // And no fetch was attempted — defensive hard-fail before network.
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('item 5: enabled:false produces the same endpoint_not_enabled hard-fail', async () => {
    const fetchImpl = vi.fn();
    let caught: unknown;
    try {
      await persistKakaoSyncConsent(
        {
          supabaseUserId: 'u',
          linkedProvider: 'kakao',
          supabaseAccessToken: 'jwt',
          providerAccessToken: 'tok',
          providerRefreshToken: null,
        },
        {
          apiBaseUrl: 'http://api.test',
          enabled: false,
          fetchImpl: fetchImpl as unknown as typeof fetch,
        },
      );
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(KakaoSyncAuditError);
    if (caught instanceof KakaoSyncAuditError) expect(caught.code).toBe('endpoint_not_enabled');
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('item 6: non-numeric attempt_count is reset to 0 instead of re-storing NaN', async () => {
    const writes: Array<[string, string]> = [];
    const storage: Pick<Storage, 'getItem' | 'setItem'> = {
      getItem: (key) => {
        if (key === 'jippin_anon_gate.attempt_count') return 'not-a-number';
        return null;
      },
      setItem: (key, value) => {
        writes.push([key, value]);
      },
    };
    const decision = await evaluateAnonymousGate(
      {
        requireExplicitIntent: false,
        requireChallengeToken: false,
        minIntervalMs: 0,
        maxAttemptsPerSession: 3,
      },
      { reason: 'explicit_intent', storage, now: () => 1_000 },
    );
    expect(decision.allowed).toBe(true);
    const countWrite = writes.find(([k]) => k === 'jippin_anon_gate.attempt_count');
    expect(countWrite).toBeDefined();
    // Bad input was 'not-a-number' → reset to 0, then +1 = '1'. Must NOT be 'NaN'.
    expect(countWrite?.[1]).toBe('1');
    expect(countWrite?.[1]).not.toBe('NaN');
  });

  it('item 6: non-numeric last_attempt is ignored (not used as a comparison anchor)', async () => {
    const storage: Pick<Storage, 'getItem' | 'setItem'> = {
      getItem: (key) => {
        if (key === 'jippin_anon_gate.last_attempt_ms') return 'corrupted';
        return null;
      },
      setItem: () => {},
    };
    // With non-numeric last_attempt, the gate must treat it as "no prior attempt"
    // and ALLOW the call (rather than incorrectly comparing now - NaN < window).
    const decision = await evaluateAnonymousGate(
      {
        requireExplicitIntent: false,
        requireChallengeToken: false,
        minIntervalMs: 60_000,
        maxAttemptsPerSession: 0,
      },
      { reason: 'explicit_intent', storage, now: () => 1_000 },
    );
    expect(decision.allowed).toBe(true);
  });
});

describe('CMP-581 round-14 review fixes', () => {
  it('item 1: signin intent is structurally denied for any non-none session (positive-list)', () => {
    // 항목 1 reviewer 재차 지적 — authenticated+signin 이 어떤 fallthrough 로도
    // allow 되지 않음을 모든 세션 형태에서 검증.
    const fromAuth = evaluateOAuthIntentGuard(
      { kind: 'authenticated', userId: 'u-1', isAnonymous: false },
      'signin',
    );
    expect(fromAuth.allowed).toBe(false);
    if (!fromAuth.allowed) expect(fromAuth.reason).toBe('signin_blocked_authenticated_session');

    const fromAnon = evaluateOAuthIntentGuard(
      { kind: 'anonymous', userId: 'anon-1' },
      'signin',
    );
    expect(fromAnon.allowed).toBe(false);
    if (!fromAnon.allowed) expect(fromAnon.reason).toBe('signin_blocked_anonymous_session');

    const fromNone = evaluateOAuthIntentGuard({ kind: 'none' }, 'signin');
    expect(fromNone.allowed).toBe(true);
  });

  it('item 1: anonymous-signin-guard.ts source has no path that allows signin on non-none session', async () => {
    // Forensic guard — 단일 책임 헬퍼 `isSigninAllowedForSession` 이 session.kind
    // === "none" 만 true 로 반환해야 한다. 미래 refactor 가 이 조건을 깨면 본
    // 테스트가 fail. body 만 정확히 추출해서 검증 (regex 가 return-type annotation
    // 의 `{ kind: 'none' }` 와 충돌하지 않게 brace counting).
    const fs = await import('node:fs');
    const path = await import('node:path');
    const src = fs.readFileSync(
      path.resolve(__dirname, '..', 'anonymous-signin-guard.ts'),
      'utf8',
    );
    const fnHeadIdx = src.indexOf('function isSigninAllowedForSession');
    expect(fnHeadIdx).toBeGreaterThan(-1);
    // 함수 시그니처 이후 첫 `{` 부터 매칭되는 `}` 까지 brace 카운트로 추출.
    const sigEnd = src.indexOf(' {\n', fnHeadIdx);
    expect(sigEnd).toBeGreaterThan(-1);
    const bodyStart = sigEnd + 2;
    let depth = 1;
    let i = bodyStart + 1;
    for (; i < src.length && depth > 0; i++) {
      if (src[i] === '{') depth++;
      else if (src[i] === '}') depth--;
    }
    const body = src.slice(bodyStart, i);
    expect(body).toContain("session.kind === 'none'");
    // 본 헬퍼 body 가 'authenticated' / 'anonymous' 를 true 로 반환하는 분기는 없어야 한다.
    expect(body).not.toContain("'authenticated'");
    expect(body).not.toContain("'anonymous'");
  });

  it('item 2: backend stub `POST /auth/terms/kakao-sync` is present in apps/api/src/routers/auth.py', async () => {
    // Forensic cross-check — web helper 의 URL path 가 가리키는 backend route 가
    // 실제로 repo 에 존재함을 source-level 로 박제. 미래에 누군가 backend route 를
    // 삭제하면 본 테스트가 fail 해서 helper 가 dangling endpoint 를 가리키지
    // 않도록 한다.
    const fs = await import('node:fs');
    const path = await import('node:path');
    const apiRouterPath = path.resolve(
      __dirname,
      '..',
      '..',
      '..',
      '..',
      'apps',
      'api',
      'src',
      'routers',
      'auth.py',
    );
    expect(fs.existsSync(apiRouterPath)).toBe(true);
    const src = fs.readFileSync(apiRouterPath, 'utf8');
    expect(src).toContain('"/terms/kakao-sync"');
    expect(src).toContain('KakaoSyncAuditRequest');
    expect(src).toContain('KakaoSyncAuditResponse');
  });

  it('item 2: KAKAO_SYNC_AUDIT_ENDPOINT_PATH constant matches the backend route definition', () => {
    // helper 가 hardcode 하던 path 를 단일 export 로 외부화. backend router prefix
    // `/auth` + route `/terms/kakao-sync` = `/auth/terms/kakao-sync`.
    expect(KAKAO_SYNC_AUDIT_ENDPOINT_PATH).toBe('/auth/terms/kakao-sync');
  });

  it('item 2: helper uses options.endpointPath override when caller supplies it', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    await persistKakaoSyncConsent(
      {
        supabaseUserId: 'u',
        linkedProvider: 'kakao',
        supabaseAccessToken: 'jwt',
        providerAccessToken: 'tok',
        providerRefreshToken: null,
      },
      {
        apiBaseUrl: 'http://api.test',
        enabled: true,
        endpointPath: '/custom/audit/path',
        fetchImpl: fetchImpl as unknown as typeof fetch,
      },
    );
    const [url] = fetchImpl.mock.calls[0] as [string];
    expect(url).toBe('http://api.test/custom/audit/path');
  });

  it('item 3: fetch reject (network error) is wrapped as KakaoSyncAuditError code=network_error', async () => {
    // Raw TypeError / network down → callsite 가 try/catch 에서 KakaoSyncAuditError
    // 만 보고 code 로 분기할 수 있어야 한다. round-11 hard-fail 정책 + round-14 의
    // 일관된 error envelope 봉인.
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
    let caught: unknown;
    try {
      await persistKakaoSyncConsent(
        {
          supabaseUserId: 'u',
          linkedProvider: 'kakao',
          supabaseAccessToken: 'jwt',
          providerAccessToken: 'tok',
          providerRefreshToken: null,
        },
        {
          apiBaseUrl: 'http://api.test',
          enabled: true,
          fetchImpl: fetchImpl as unknown as typeof fetch,
        },
      );
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(KakaoSyncAuditError);
    if (caught instanceof KakaoSyncAuditError) {
      expect(caught.code).toBe('network_error');
      expect(caught.status).toBe(0);
      expect(caught.message).toContain('Failed to fetch');
    }
  });

  it('item r15-1: requireChallengeToken=true without verifier blocks as challenge_verifier_missing', async () => {
    // Reviewer round-15 — verifier 가 없으면 CAPTCHA/Turnstile 이 사실상 무효화.
    // configuration failure 로 즉시 차단.
    const decision = await evaluateAnonymousGate(
      {
        requireExplicitIntent: false,
        requireChallengeToken: true,
        minIntervalMs: 0,
        maxAttemptsPerSession: 0,
        // verifyChallengeToken intentionally omitted.
      },
      { reason: 'challenge', challengeToken: 'some-token', storage: new MemoryStorage() },
    );
    expect(decision.allowed).toBe(false);
    if (!decision.allowed) {
      expect(decision.reason).toBe('challenge_verifier_missing');
      expect(decision.detail).toContain('verifyChallengeToken');
    }
  });

  it('item r15-1: missing verifier blocks regardless of whether the token is also missing', async () => {
    // 토큰까지 없어도 verifier 부재가 우선 — 잘못된 설정을 가장 먼저 감지.
    const decision = await evaluateAnonymousGate(
      {
        requireExplicitIntent: false,
        requireChallengeToken: true,
        minIntervalMs: 0,
        maxAttemptsPerSession: 0,
      },
      { reason: 'challenge', storage: new MemoryStorage() },
    );
    expect(decision.allowed).toBe(false);
    if (!decision.allowed) expect(decision.reason).toBe('challenge_verifier_missing');
  });

  it('item r15-2: 2xx response with stubbed:true body throws KakaoSyncAuditError(code=stub_response)', async () => {
    // Reviewer round-15 — backend stub 의 202 + {stubbed:true} 를 success 로
    // 처리하면 `terms_consents(source='kakao_sync')` 가 비는 회귀. helper 가
    // explicit fail 로 surface 해야 callsite 가 reconcile 경로 진입 가능.
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ accepted: true, stubbed: true, detail: 'Phase 1 stub' }), {
        status: 202,
        headers: { 'content-type': 'application/json' },
      }),
    );
    let caught: unknown;
    try {
      await persistKakaoSyncConsent(
        {
          supabaseUserId: 'u',
          linkedProvider: 'kakao',
          supabaseAccessToken: 'jwt',
          providerAccessToken: 'tok',
          providerRefreshToken: null,
        },
        {
          apiBaseUrl: 'http://api.test',
          enabled: true,
          fetchImpl: fetchImpl as unknown as typeof fetch,
        },
      );
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(KakaoSyncAuditError);
    if (caught instanceof KakaoSyncAuditError) {
      expect(caught.code).toBe('stub_response');
      expect(caught.status).toBe(202);
      // responseBody 에는 stub body 가 보존되어 운영이 forensics 가능해야 한다.
      expect(caught.responseBody).toContain('stubbed');
    }
  });

  it('item r15-2: 2xx with stubbed:false (or no stubbed key) is treated as success (no false positive)', async () => {
    // Backend 가 production 진입 후 `stubbed: false` 또는 stubbed 키 미포함을
    // 반환할 때 helper 가 정상 success 로 통과해야 한다 — round-15 fence 가
    // 모든 2xx 를 throw 시키지 않음을 검증. round-17 에서 return type 이
    // { persisted: true } 로 변경되어 그 값까지 검증.
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ accepted: true, stubbed: false }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
    await expect(
      persistKakaoSyncConsent(
        {
          supabaseUserId: 'u',
          linkedProvider: 'kakao',
          supabaseAccessToken: 'jwt',
          providerAccessToken: 'tok',
          providerRefreshToken: null,
        },
        {
          apiBaseUrl: 'http://api.test',
          enabled: true,
          fetchImpl: fetchImpl as unknown as typeof fetch,
        },
      ),
    ).resolves.toEqual({ persisted: true });
  });

  it('item r15-2: 2xx with non-JSON body still succeeds (graceful)', async () => {
    // production 백엔드가 empty body / plain text 를 반환해도 stub 신호 부재로
    // 정상 success — round-17 의 { persisted: true } 반환.
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response('', { status: 200 }),
    );
    await expect(
      persistKakaoSyncConsent(
        {
          supabaseUserId: 'u',
          linkedProvider: 'kakao',
          supabaseAccessToken: 'jwt',
          providerAccessToken: 'tok',
          providerRefreshToken: null,
        },
        {
          apiBaseUrl: 'http://api.test',
          enabled: true,
          fetchImpl: fetchImpl as unknown as typeof fetch,
        },
      ),
    ).resolves.toEqual({ persisted: true });
  });

  it('item r16-2: sessionStorage.getItem throw (SecurityError) returns storage_unavailable', async () => {
    // Reviewer round-16 — read 도 SecurityError / partitioned-storage 등에서
    // throw 가능. setItem 만 catch 한 코드는 첫 read 에서 uncaught error.
    const throwingStorage: Pick<Storage, 'getItem' | 'setItem'> = {
      getItem: () => {
        throw new DOMException('SecurityError', 'SecurityError');
      },
      setItem: () => {},
    };
    const decision = await evaluateAnonymousGate(
      {
        requireExplicitIntent: false,
        requireChallengeToken: false,
        minIntervalMs: 60_000,
        maxAttemptsPerSession: 0,
      },
      { reason: 'explicit_intent', storage: throwingStorage, now: () => 1_000 },
    );
    expect(decision.allowed).toBe(false);
    if (!decision.allowed) {
      expect(decision.reason).toBe('storage_unavailable');
      expect(decision.detail).toContain('getItem');
      expect(decision.detail).toContain('SecurityError');
    }
  });

  it('item r16-2: getItem throw on attempt_count path also surfaces as storage_unavailable', async () => {
    const throwingStorage: Pick<Storage, 'getItem' | 'setItem'> = {
      getItem: () => {
        throw new Error('storage access blocked');
      },
      setItem: () => {},
    };
    const decision = await evaluateAnonymousGate(
      {
        requireExplicitIntent: false,
        requireChallengeToken: false,
        minIntervalMs: 0,
        maxAttemptsPerSession: 3, // attempt_count path 만 활성화
      },
      { reason: 'explicit_intent', storage: throwingStorage, now: () => 1_000 },
    );
    expect(decision.allowed).toBe(false);
    if (!decision.allowed) {
      expect(decision.reason).toBe('storage_unavailable');
      expect(decision.detail).toContain('attempt_count');
    }
  });

  it('item r16-4: reason=challenge alone does NOT satisfy explicit_intent when challenge mode is not configured', async () => {
    // Reviewer round-16 — requireExplicitIntent=true 일 때 reason='challenge' 가
    // requireChallengeToken=false 인 상태에서도 통과하던 회귀. challenge mode 가
    // 실 구성 (requireChallengeToken=true + verifier) 된 경우에만 G1 만족.
    const decision = await evaluateAnonymousGate(
      {
        requireExplicitIntent: true,
        requireChallengeToken: false, // challenge mode 가 구성되지 않음
        minIntervalMs: 0,
        maxAttemptsPerSession: 0,
      },
      { reason: 'challenge', storage: new MemoryStorage() },
    );
    expect(decision.allowed).toBe(false);
    if (!decision.allowed) expect(decision.reason).toBe('explicit_intent_required');
  });

  it('item r16-4: reason=challenge satisfies explicit_intent when challenge mode IS configured (with verifier)', async () => {
    const decision = await evaluateAnonymousGate(
      {
        requireExplicitIntent: true,
        requireChallengeToken: true,
        verifyChallengeToken: async () => true,
        minIntervalMs: 0,
        maxAttemptsPerSession: 0,
      },
      { reason: 'challenge', challengeToken: 'verified-token', storage: new MemoryStorage() },
    );
    expect(decision.allowed).toBe(true);
  });

  it('item r16-4: reason=challenge with requireChallengeToken=true but no verifier is blocked at the verifier-missing layer (not silently allowed)', async () => {
    // Defence in depth — G1 의 challenge-mode-configured 검증은 verifier 함수
    // 존재까지 요구하지만, G2 의 challenge_verifier_missing block 이 그 다음 단계
    // 에서도 작동. 두 layer 모두 빠뜨리지 않도록.
    const decision = await evaluateAnonymousGate(
      {
        requireExplicitIntent: true,
        requireChallengeToken: true,
        // verifyChallengeToken intentionally omitted.
        minIntervalMs: 0,
        maxAttemptsPerSession: 0,
      },
      { reason: 'challenge', challengeToken: 'tok', storage: new MemoryStorage() },
    );
    expect(decision.allowed).toBe(false);
    if (!decision.allowed) {
      // G1 의 challenge-mode-configured 가 verifier 부재로 인해 false →
      // reason='explicit_intent_required' 가 먼저 hit. 만약 G1 을 통과하면
      // G2 가 challenge_verifier_missing 으로 catch — 둘 다 valid block.
      expect(['explicit_intent_required', 'challenge_verifier_missing']).toContain(decision.reason);
    }
  });

  it('item r17-3: anonymous + link-merge is blocked without linkIdentity-attempted evidence (manual-link-first)', () => {
    // Reviewer round-17 — link-merge 가 normal linkIdentity 실패 없이 통과하면
    // manual-link-first 우회. evidence 가 없으면 block.
    const decision = evaluateOAuthIntentGuard(
      { kind: 'anonymous', userId: 'anon-1' },
      'link-merge',
      // context omitted intentionally
    );
    expect(decision.allowed).toBe(false);
    if (!decision.allowed) {
      expect(decision.reason).toBe('link_merge_requires_link_attempt');
      expect(decision.detail).toContain('linkIdentity');
    }
  });

  it('item r17-3: link-merge with linkIdentityAttempted=true but missing failure reason is also blocked', () => {
    const decision = evaluateOAuthIntentGuard(
      { kind: 'anonymous', userId: 'anon-1' },
      'link-merge',
      {
        linkMergePrerequisite: {
          linkIdentityAttempted: true,
          linkIdentityFailureReason: '',
        },
      },
    );
    expect(decision.allowed).toBe(false);
    if (!decision.allowed) expect(decision.reason).toBe('link_merge_requires_link_attempt');
  });

  it('item r17-3: link-merge with both evidence fields passes', () => {
    const decision = evaluateOAuthIntentGuard(
      { kind: 'anonymous', userId: 'anon-1' },
      'link-merge',
      {
        linkMergePrerequisite: {
          linkIdentityAttempted: true,
          linkIdentityFailureReason: 'identity_already_exists',
        },
      },
    );
    expect(decision.allowed).toBe(true);
    if (decision.allowed) expect(decision.intent).toBe('link-merge');
  });

  it('item r17-1: persistKakaoSyncConsent success returns { persisted: true } (type-level fence)', async () => {
    // Reviewer round-17 — return type 을 Promise<{persisted:true}> 로 변경하여
    // callsite 가 success 경로에서 `result.persisted === true` 를 명시 확인.
    // stub 응답은 throw 되므로 본 success path 에 도달 불가.
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ accepted: true, stubbed: false }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
    const result = await persistKakaoSyncConsent(
      {
        supabaseUserId: 'u',
        linkedProvider: 'kakao',
        supabaseAccessToken: 'jwt',
        providerAccessToken: 'tok',
        providerRefreshToken: null,
      },
      {
        apiBaseUrl: 'http://api.test',
        enabled: true,
        fetchImpl: fetchImpl as unknown as typeof fetch,
      },
    );
    expect(result).toEqual({ persisted: true });
    // Compile-time fence — result.persisted must be `true` literal.
    const _typeCheck: true = result.persisted;
    expect(_typeCheck).toBe(true);
  });

  it('item r16-1: kakao-sync-audit.ts docstring documents stub_response policy (forensic guard)', async () => {
    // Round-15 에서 stub_response throw 를 ship 했으나 PR review thread 에서
    // 자동 resolve 가 일어나지 않음. round-16 에서 정책을 module docstring 에
    // explicit 단락으로 박제 — forensic test 가 변경/삭제를 즉시 catch.
    const fs = await import('node:fs');
    const path = await import('node:path');
    const src = fs.readFileSync(
      path.resolve(__dirname, '..', 'kakao-sync-audit.ts'),
      'utf8',
    );
    expect(src).toContain("code='stub_response'");
    expect(src).toContain('stub-response 회귀 차단');
    expect(src).toContain('reconcile');
  });

  it('item 3: fetch reject of non-Error value also wraps cleanly (no leaked raw value)', async () => {
    const fetchImpl = vi.fn().mockRejectedValue('cors-blocked');
    let caught: unknown;
    try {
      await persistKakaoSyncConsent(
        {
          supabaseUserId: 'u',
          linkedProvider: 'kakao',
          supabaseAccessToken: 'jwt',
          providerAccessToken: 'tok',
          providerRefreshToken: null,
        },
        {
          apiBaseUrl: 'http://api.test',
          enabled: true,
          fetchImpl: fetchImpl as unknown as typeof fetch,
        },
      );
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(KakaoSyncAuditError);
    if (caught instanceof KakaoSyncAuditError) {
      expect(caught.code).toBe('network_error');
      expect(caught.message).toContain('cors-blocked');
    }
  });
});

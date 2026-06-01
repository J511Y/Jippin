/**
 * Anonymous sign-in abuse-control gate (CMP-581 / runbook §4.1 / §4.4).
 *
 * SSOT:
 *   - `docs/runbooks/supabase-web-auth.md` §4.1 익명 sign-in 호출 시점.
 *   - `docs/adr/0003-anon-user-and-sso.md` §2.5 / §5 — anonymous identifier 정책.
 *     본 모듈은 ADR-0003 의 legacy `localStorage.jippin_anonymous_user_id` 와
 *     Supabase anonymous user 가 Phase 1 동안 dual-write 되는 모델을 봉인한다.
 *
 * R4 회귀 방지 — `app/*` 의 첫 paint 에서 무조건 `supabase.auth.signInAnonymously()`
 * 를 호출하면 봇·크롤러·반복 미인증 방문이 `auth.users` 행을 무한 생성한다.
 * Supabase anonymous user 는 실 user 와 동일하게 영속하므로 사후 cleanup 비용이 크다.
 *
 * 본 gate 는 익명 발급을 다음 중 **하나 이상이 만족될 때까지** 지연시킨다 (review 의
 * "abuse-control gate such as Turnstile/CAPTCHA or move sign-in to the first real
 * pre-review action plus a cleanup/rate-limit plan" 에 1:1 대응):
 *
 *   (G1) **명시적 사용자 의도** — `requireExplicitIntent`. layout mount 만으로 발급하지
 *        않고, 실제 pre-review 첫 입력(예: "사전검토 시작" 버튼 클릭, 업로드 시도)
 *        에서 `requestAnonymousBootstrap('explicit_intent')` 호출.
 *   (G2) **챌린지 토큰** — `requireChallengeToken`. Turnstile / hCAPTCHA / reCAPTCHA 토큰을
 *        받은 후에만 발급. 호출자는 토큰 획득 후 `requestAnonymousBootstrap('challenge', { token })`.
 *   (G3) **클라이언트 rate-limit** — 같은 브라우저에서 짧은 윈도우 안의 반복 발급 요청
 *        차단. `sessionStorage` 기반 (서버 IP rate-limit 은 backend 의 책임 — §4.4).
 *   (G4) **client-side single-flight** — 같은 브라우저 탭에서 동시에 호출되는
 *        anonymous bootstrap 요청을 하나의 in-flight promise 로 묶는다. race 시
 *        같은 브라우저가 여러 anonymous user 를 만들지 않도록 보장. server-side
 *        dedupe key 는 `anonymous-signin-guard.shouldIssueAnonymousSignIn` 가 책임.
 *
 * 본 gate 는 **클라이언트 1차 방어**. backend (`POST /auth/anonymous-users`, 익명
 * 핸들 발급 라우트) 와 Supabase Auth 콘솔의 anonymous quota / IP rate-limit 이 항상
 * 2차 방어로 동작한다 — 본 gate 를 우회한 호출도 backend / Supabase 가 막는다.
 *
 * 본 모듈은 Supabase SDK 에 직접 의존하지 않고, "익명 발급을 진행해도 되는가?" 판정만
 * 책임진다. 발급 자체는 호출자(SessionProvider 의 anonymous-bootstrap singleton)가 한다.
 *
 * ADR-0003 §2.3 정책 봉인 — 동일 verified email 의 automatic identity link/merge 는
 * 영구 금지. Supabase 콘솔 `Auth → Settings → Account Linking = manual only` +
 * `dangerously_enable_same_email_link_identity: false` (기본값) 가 보드 책임 (§8).
 * 본 모듈이 발급한 anonymous user 가 OAuth 로 전환될 때는 항상 `auth.linkIdentity()`
 * (= manual 흐름) 만 사용한다 — `anonymous-signin-guard.evaluateOAuthIntentGuard` 참조.
 */

export type AnonymousGateReason = 'explicit_intent' | 'challenge';

export interface AnonymousGateConfig {
  /**
   * G1 — explicit intent 만족 사유 없이 발급을 차단할지. layout 첫 paint 차단에 사용.
   * 기본값 false (옵트인) — Phase 1 활성화 시점은 호출부가 결정.
   */
  requireExplicitIntent: boolean;
  /**
   * G2 — challenge 토큰이 없을 때 발급 차단 여부. Turnstile/hCAPTCHA 등.
   * 기본값 false (옵트인). 활성화 시 `verifyChallengeToken` 도 함께 제공.
   */
  requireChallengeToken: boolean;
  /**
   * G3 — 동일 브라우저(=동일 sessionStorage) 안에서 최소 발급 간격(ms).
   * 0 또는 음수면 비활성. 기본값 0.
   */
  minIntervalMs: number;
  /**
   * G3 보조 — 동일 sessionStorage 안 최대 발급 시도 횟수. minIntervalMs 와 함께 사용.
   * 음수/0 이면 비활성. 기본값 0.
   */
  maxAttemptsPerSession: number;
  /**
   * G2 검증 콜백. 토큰이 있는 경우에만 호출된다. throw 또는 false 반환 시 발급 차단.
   * 본 모듈은 토큰 발급/표시 책임을 가지지 않는다 — 호출자가 Turnstile/hCAPTCHA SDK 와
   * 본 콜백을 연결한다.
   */
  verifyChallengeToken?: (token: string) => Promise<boolean> | boolean;
}

export const DEFAULT_ANONYMOUS_GATE_CONFIG: AnonymousGateConfig = {
  requireExplicitIntent: false,
  requireChallengeToken: false,
  minIntervalMs: 0,
  maxAttemptsPerSession: 0,
};

export interface AnonymousGateRequest {
  reason: AnonymousGateReason;
  challengeToken?: string;
  /** 테스트/SSR 주입용. 기본값은 `window.sessionStorage`. */
  storage?: Pick<Storage, 'getItem' | 'setItem'>;
  /** 테스트 주입용. 기본값은 `Date.now`. */
  now?: () => number;
}

export type AnonymousGateDecision =
  | { allowed: true }
  | { allowed: false; reason: AnonymousGateBlockReason; detail?: string };

export type AnonymousGateBlockReason =
  | 'explicit_intent_required'
  | 'challenge_token_required'
  | 'challenge_token_invalid'
  | 'rate_limited'
  | 'storage_unavailable';

const STORAGE_PREFIX = 'jippin_anon_gate';
const LAST_ATTEMPT_KEY = `${STORAGE_PREFIX}.last_attempt_ms`;
const ATTEMPT_COUNT_KEY = `${STORAGE_PREFIX}.attempt_count`;

function readStorage(storage: Pick<Storage, 'getItem'> | undefined): Storage | null {
  if (storage) return storage as Storage;
  if (typeof window === 'undefined') return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/**
 * 발급 요청 1건에 대한 gate 판정. allow 시 호출자는 `signInAnonymously` 진행.
 * deny 시 호출자는 사유에 맞는 UX 분기 — challenge 표시 / "사전검토 시작" CTA 유지 / retry toast.
 *
 * 본 함수는 **사이드 이펙트** 가 있다 — `allowed: true` 시 G3 의 attempt counter / timestamp
 * 를 storage 에 기록한다 (다음 호출의 rate-limit 판정 기준).
 */
export async function evaluateAnonymousGate(
  config: AnonymousGateConfig,
  request: AnonymousGateRequest,
): Promise<AnonymousGateDecision> {
  // G1 — explicit intent.
  if (config.requireExplicitIntent && request.reason !== 'explicit_intent' && request.reason !== 'challenge') {
    return { allowed: false, reason: 'explicit_intent_required' };
  }

  // G2 — challenge token.
  if (config.requireChallengeToken) {
    if (!request.challengeToken) {
      return { allowed: false, reason: 'challenge_token_required' };
    }
    if (config.verifyChallengeToken) {
      let ok = false;
      try {
        ok = await config.verifyChallengeToken(request.challengeToken);
      } catch (err) {
        return {
          allowed: false,
          reason: 'challenge_token_invalid',
          detail: err instanceof Error ? err.message : String(err),
        };
      }
      if (!ok) {
        return { allowed: false, reason: 'challenge_token_invalid' };
      }
    }
  }

  // G3 — client rate-limit.
  const rateLimitActive = config.minIntervalMs > 0 || config.maxAttemptsPerSession > 0;
  if (rateLimitActive) {
    const storage = readStorage(request.storage);
    if (!storage) {
      return { allowed: false, reason: 'storage_unavailable' };
    }
    const now = (request.now ?? Date.now)();
    if (config.minIntervalMs > 0) {
      const lastRaw = storage.getItem(LAST_ATTEMPT_KEY);
      const last = lastRaw === null ? NaN : Number(lastRaw);
      if (Number.isFinite(last) && now - last < config.minIntervalMs) {
        return {
          allowed: false,
          reason: 'rate_limited',
          detail: `minIntervalMs=${config.minIntervalMs} 윈도우 안 재시도.`,
        };
      }
    }
    if (config.maxAttemptsPerSession > 0) {
      const countRaw = storage.getItem(ATTEMPT_COUNT_KEY);
      const count = countRaw === null ? 0 : Number(countRaw);
      if (Number.isFinite(count) && count >= config.maxAttemptsPerSession) {
        return {
          allowed: false,
          reason: 'rate_limited',
          detail: `maxAttemptsPerSession=${config.maxAttemptsPerSession} 초과.`,
        };
      }
      storage.setItem(ATTEMPT_COUNT_KEY, String(count + 1));
    }
    storage.setItem(LAST_ATTEMPT_KEY, String(now));
  }

  return { allowed: true };
}

// ---------------------------------------------------------------------------
// G4 — client-side single-flight (race 방지).
//
// 같은 브라우저 탭에서 anonymous bootstrap 이 동시에 호출돼도 in-flight promise
// 하나로 묶어 `auth.users` 중복 생성을 막는다. 호출자는 본 helper 를 anonymous
// bootstrap singleton (SessionProvider) 에서 사용한다.
//
// 동일 호출이 끝나면 in-flight slot 을 비워서 다음 호출이 정상 진입할 수 있다.
// reject 도 동일하게 slot 을 비운다 — 실패한 호출이 cache 되어 재시도를 막는
// 회귀를 피하기 위해.
// ---------------------------------------------------------------------------

let inFlightAnonymousBootstrap: Promise<unknown> | null = null;

export function withAnonymousSingleFlight<T>(invoke: () => Promise<T>): Promise<T> {
  if (inFlightAnonymousBootstrap !== null) {
    return inFlightAnonymousBootstrap as Promise<T>;
  }
  const promise = invoke()
    .finally(() => {
      if (inFlightAnonymousBootstrap === promise) {
        inFlightAnonymousBootstrap = null;
      }
    });
  inFlightAnonymousBootstrap = promise;
  return promise;
}

/** Test-only — single-flight slot 을 강제 리셋. 운영 코드에서 호출 금지. */
export function __resetAnonymousSingleFlightForTests(): void {
  inFlightAnonymousBootstrap = null;
}

// ---------------------------------------------------------------------------
// Legacy `localStorage.jippin_anonymous_user_id` → Supabase user_metadata 백필.
//
// Phase 1 dual-write 동안 두 ID 체계가 공존하지만 (runbook §0 / §4.1), Phase 2 에서
// localStorage 키를 폐기하기 전에 Supabase anonymous user 에 legacy id 를 1회성
// 백필해 두어야 도면/리포트 claim 경로가 끊기지 않는다.
//
//   - 1회성: `user_metadata.legacy_anonymous_id` 가 이미 존재하면 호출하지 않는다.
//   - 비파괴: legacy id 가 null/빈 문자열이면 호출하지 않는다.
//   - 본 helper 는 Supabase SDK 에 직접 의존하지 않고 `updateUserMetadata` 콜백을
//     주입받는다 — 테스트와 SSR 모두 SDK 없이 검증 가능.
// ---------------------------------------------------------------------------

export interface LegacyAnonymousIdBackfillInput {
  /** 현재 Supabase anonymous user 의 user_metadata. */
  currentMetadata: Record<string, unknown> | null | undefined;
  /** localStorage 에 남아 있는 legacy uuid (또는 null). */
  legacyAnonymousId: string | null;
  /** 실제 update 호출 (SDK / fetch). 테스트에서는 mock. */
  updateUserMetadata: (
    next: Record<string, unknown> & { legacy_anonymous_id: string },
  ) => Promise<void>;
}

export type LegacyAnonymousIdBackfillResult =
  | { backfilled: true; legacyAnonymousId: string }
  | { backfilled: false; reason: 'no_legacy_id' | 'already_backfilled' };

export async function backfillLegacyAnonymousId(
  input: LegacyAnonymousIdBackfillInput,
): Promise<LegacyAnonymousIdBackfillResult> {
  const legacyId = input.legacyAnonymousId;
  if (legacyId === null || legacyId.length === 0) {
    return { backfilled: false, reason: 'no_legacy_id' };
  }
  const metadata = input.currentMetadata ?? {};
  if (typeof metadata.legacy_anonymous_id === 'string' && metadata.legacy_anonymous_id.length > 0) {
    return { backfilled: false, reason: 'already_backfilled' };
  }
  await input.updateUserMetadata({
    ...metadata,
    legacy_anonymous_id: legacyId,
  });
  return { backfilled: true, legacyAnonymousId: legacyId };
}

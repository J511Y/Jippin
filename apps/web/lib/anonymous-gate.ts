/**
 * Anonymous sign-in abuse-control gate (CMP-581 / runbook §4.1 / §4.4).
 *
 * SSOT: `docs/runbooks/supabase-web-auth.md` §4.1 익명 sign-in 호출 시점.
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
 *
 * 본 gate 는 **클라이언트 1차 방어**. backend (`POST /auth/anonymous-users`, 익명
 * 핸들 발급 라우트) 와 Supabase Auth 콘솔의 anonymous quota / IP rate-limit 이 항상
 * 2차 방어로 동작한다 — 본 gate 를 우회한 호출도 backend / Supabase 가 막는다.
 *
 * 본 모듈은 Supabase SDK 에 직접 의존하지 않고, "익명 발급을 진행해도 되는가?" 판정만
 * 책임진다. 발급 자체는 호출자(SessionProvider 의 anonymous-bootstrap singleton)가 한다.
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

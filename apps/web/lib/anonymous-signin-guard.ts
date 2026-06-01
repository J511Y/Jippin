/**
 * Anonymous-session OAuth intent guard (CMP-581 / runbook §4.2.1 / ADR-0003 §2.3).
 *
 * SSOT:
 *   - `docs/runbooks/supabase-web-auth.md` §0.0, §4.2 (CMP-572 CEO 결정 — manual
 *     linking only).
 *   - `docs/adr/0003-anon-user-and-sso.md` §2.3 (동일 이메일 자동 병합 금지).
 *
 * CMP-577 보드 리뷰어 round-11 지침 항목 2/6/7 봉인:
 *   - **항목 2.** `signIn` intent (로그인 버튼 클릭) 에서 새 anonymous user 를
 *     **생성해서는 안 된다** — anonymous user 는 앱 최초 진입 시점에만 발급한다.
 *     익명 세션 상태에서 OAuth 진입은 `linkIdentity()` 만 허용. `signInWithOAuth`
 *     를 그대로 호출하면 새 user 가 만들어지며 익명 user 의 도면/리포트 ownership
 *     이 끊긴다 (runbook §4.2.1 마지막 bullet).
 *   - **항목 6.** anonymous sign-in 은 server component / middleware 에서 기존
 *     세션 없음이 확인된 경우에만 호출되어야 한다. 본 guard 는 OAuth start BFF
 *     (`apps/web/app/auth/oauth/start/route.ts`) 와 login CTA 양쪽에서 호출되어
 *     익명 세션이 있는데 signin intent 가 들어오는 케이스를 즉시 차단한다.
 *   - **항목 7.** ADR-0003 §2.3 — 동일 verified email 의 automatic identity
 *     link/merge 는 **금지**. Supabase 콘솔의 "Auto-link verified emails" /
 *     "Link accounts with same email" 토글은 모두 OFF (= 기본값 `dangerously_
 *     enable_same_email_link_identity: false`) 이어야 하며, manual flow 는
 *     `auth.linkIdentity()` 명시적 호출로만 진입한다. 본 guard 는 그 manual
 *     경로의 클라이언트 쪽 단일 진입점이다.
 *
 * 본 guard 는 Supabase SDK 에 직접 의존하지 않는다. 호출자가 현재 세션의
 * `is_anonymous` 와 진입 intent 를 인자로 넘기면, guard 는 다음 다섯 가지 케이스를
 * 판정해 (allow | block) 만 반환한다:
 *
 *   1. 익명 세션 + `link` intent      → allow (linkIdentity 호출 OK).
 *   2. 익명 세션 + `link-merge` intent → allow (§4.2.2 fallback ladder 의
 *                                          명시적 signOut 후 signInWithOAuth).
 *   3. 익명 세션 + `signin` intent    → **block** (회귀 차단 — 익명 user 폐기 위험).
 *   4. 비익명 세션 + `link` intent     → block (이미 실명 user. UI 가 잘못 표시).
 *   5. 미로그인 + `signin` intent      → allow (정상 로그인 진입).
 *
 * 본 guard 의 결정은 BFF 의 302 응답과 callback 의 정합을 위한 단일 진입점.
 * 실 SDK 호출 (`linkIdentity` / `signInWithOAuth`) 은 본 모듈이 아닌
 * `apps/web/app/auth/oauth/start/route.ts` (Phase 1 봉인) 가 책임진다.
 */

export type OAuthIntent = 'signin' | 'link' | 'link-merge';

export type SessionShape =
  | { kind: 'none' }
  | { kind: 'anonymous'; userId: string }
  | { kind: 'authenticated'; userId: string; isAnonymous: false };

export type OAuthGuardDecision =
  | { allowed: true; intent: OAuthIntent }
  | { allowed: false; reason: OAuthGuardBlockReason; detail: string };

export type OAuthGuardBlockReason =
  | 'signin_blocked_anonymous_session'
  | 'link_blocked_authenticated_session'
  | 'link_merge_requires_anonymous_session'
  | 'unknown_intent';

const KNOWN_INTENTS: ReadonlySet<OAuthIntent> = new Set(['signin', 'link', 'link-merge']);

export function isOAuthIntent(value: unknown): value is OAuthIntent {
  return typeof value === 'string' && KNOWN_INTENTS.has(value as OAuthIntent);
}

/**
 * 익명 세션에서 OAuth 진입 intent 가 합법인지 판정.
 *
 * 호출 예 (BFF `apps/web/app/auth/oauth/start/route.ts`):
 *
 * ```ts
 * const { data: { session } } = await supabase.auth.getSession();
 * const shape: SessionShape = session
 *   ? session.user.is_anonymous
 *     ? { kind: 'anonymous', userId: session.user.id }
 *     : { kind: 'authenticated', userId: session.user.id, isAnonymous: false }
 *   : { kind: 'none' };
 * const decision = evaluateOAuthIntentGuard(shape, requestedIntent);
 * if (!decision.allowed) {
 *   return redirectWithError(decision.reason, decision.detail);
 * }
 * // decision.intent 기준으로 linkIdentity / signInWithOAuth 분기.
 * ```
 */
export function evaluateOAuthIntentGuard(
  session: SessionShape,
  intent: OAuthIntent | string,
): OAuthGuardDecision {
  if (!isOAuthIntent(intent)) {
    return {
      allowed: false,
      reason: 'unknown_intent',
      detail: `intent="${String(intent)}" 는 허용되지 않습니다.`,
    };
  }

  switch (session.kind) {
    case 'anonymous':
      if (intent === 'signin') {
        return {
          allowed: false,
          reason: 'signin_blocked_anonymous_session',
          detail:
            '익명 세션 상태에서는 signInWithOAuth 직접 호출이 금지됩니다. ' +
            'linkIdentity (intent="link") 또는 §4.2.2 fallback ladder (intent="link-merge") 로 진입해야 합니다.',
        };
      }
      return { allowed: true, intent };

    case 'authenticated':
      if (intent === 'link-merge') {
        return {
          allowed: false,
          reason: 'link_merge_requires_anonymous_session',
          detail:
            'link-merge 는 익명 세션의 fallback ladder 분기 전용입니다. 실명 세션에서는 사용할 수 없습니다.',
        };
      }
      if (intent === 'link') {
        return {
          allowed: false,
          reason: 'link_blocked_authenticated_session',
          detail:
            '이미 실명 user 로 로그인된 상태입니다. provider 추가 연결은 별도 UX (account-settings) 에서 진입해야 합니다.',
        };
      }
      return { allowed: true, intent };

    case 'none':
    default:
      if (intent === 'link' || intent === 'link-merge') {
        return {
          allowed: false,
          reason: 'link_merge_requires_anonymous_session',
          detail:
            'link 계열 intent 는 익명 세션이 존재할 때만 허용됩니다. 미로그인 상태는 signin intent 만 허용.',
        };
      }
      return { allowed: true, intent };
  }
}

/**
 * 익명 sign-in 호출이 허용되는지 server-side 판정 (runbook §4.1 / 항목 6).
 *
 * 호출 예 (middleware / server component):
 *
 * ```ts
 * if (shouldIssueAnonymousSignIn({ existingSessionUserId: session?.user.id ?? null })) {
 *   await supabase.auth.signInAnonymously();
 * }
 * ```
 *
 * 본 helper 는 **서버 측 단일 진입점**. anonymous-gate.ts 의 client-side gate 가
 * G1 (intent) / G2 (challenge) / G3 (rate-limit) 으로 발급을 늦춰도, 두 클라이언트가
 * 같은 시점에 발급 호출을 trigger 할 수 있다 — client-side single-flight (anonymous-gate
 * 의 `withAnonymousSingleFlight`) 와 server-side "기존 세션 없음" 검증이 모두 통과해야
 * `signInAnonymously` 가 실제로 호출된다.
 */
export function shouldIssueAnonymousSignIn(args: {
  existingSessionUserId: string | null;
}): boolean {
  return args.existingSessionUserId === null;
}

/**
 * Anonymous 세션 폐기 (`signOut`) 호출 순서 봉인 (round-11 항목 9 / CMP-577 3차 리뷰
 * 보드 코멘트 `66899187`).
 *
 * **봉인 룰.** `linkIdentity()` 또는 backend merge enqueue 가 *실패* 한 경로에서
 * `supabase.auth.signOut()` 을 먼저 호출하면, 익명 세션이 사라진 상태로 실패 처리가
 * 진행되어 사용자가 익명 상태로 돌아갈 수 없고 (재시도 불가), 작성하던 도면/리포트
 * ownership 이 단절되어 **데이터 손실** 위험이 생긴다. 따라서:
 *
 *   - 실패 (`failure`): 익명 세션 **유지**. 사용자에게 재시도 UX 노출.
 *   - 진행 중 (`pending`): 익명 세션 유지 (아직 결과 미확정).
 *   - 성공 (`success`): 익명 세션 폐기 허용 (Supabase 가 link/merge 로 새 세션 발급 후).
 *
 * 본 helper 는 `signOut` 호출 직전의 단일 게이트. callback Route Handler 와 client
 * fallback ladder 양쪽에서 호출해, 실패 경로에서 signOut 이 새어 나가지 못하도록
 * 강제한다. 실제 SDK signOut 호출은 본 모듈이 아닌 호출자가 책임진다 — 본 helper
 * 는 결정만 반환한다.
 *
 * **sign-out CSRF 봉인 (round-11 항목 16 / 보드 코멘트 `ab06d3b5`).** 익명 세션
 * 폐기는 본질적으로 파괴적인 동작이며, 공격자가 타인의 익명 세션을 강제 폐기하는
 * CSRF (sign-out 위조) 공격을 차단해야 한다. 본 helper 는 두 정책을 지원한다:
 *
 *   - `policy: 'required'` — 호출자가 안전 저장소(서명된 cookie / Supabase session
 *     storage / SSR 발급 토큰) 에서 expectedToken 을 읽어오고, 요청에서 받은
 *     providedToken 과 동등 비교한다. mismatch / 누락 시 즉시 block (CSRF 차단).
 *   - `policy: 'session_cookie_only'` — 호출자가 별도 메커니즘 (Supabase SSR
 *     cookie 존재 + same-origin 강제 + Sec-Fetch-Site 검증 등) 으로 forge 가능성을
 *     배제했다고 선언. 본 helper 는 CSRF 검증을 건너뛰고 outcome 만 판정.
 *
 * 호출자가 `csrf` 를 생략하면 fallback 은 `session_cookie_only` — 보수적으로 가려면
 * 호출자가 명시적으로 `policy: 'required'` 를 지정해야 한다. callback Route Handler
 * 와 client fallback ladder 가 PKCE state cookie / Supabase auth cookie 를 SSR 단계
 * 에서 검증하는 흐름과 정합. 토큰 비교는 단순 `!==` (짧은 nonce 기준; 필요 시
 * 호출자가 timingSafeEqual 로 사전 비교 후 본 helper 에 outcome 만 전달).
 *
 * 호출 예:
 *
 * ```ts
 * const decision = evaluateAnonymousDiscardDecision({
 *   stage: 'link_identity',
 *   outcome: linkError ? 'failure' : 'success',
 *   csrf: { policy: 'required', providedToken: req.body.csrfToken, expectedToken: sessionStore.csrfToken },
 * });
 * if (!decision.allowed) {
 *   return renderRetryUx(decision.detail);
 * }
 * await supabase.auth.signOut(); // CSRF 통과 + success 경로에서만 도달.
 * ```
 */
export type AnonymousMergeStage = 'link_identity' | 'merge_enqueue' | 'callback_finalize';

export type AnonymousMergeOutcome = 'pending' | 'failure' | 'success';

export type AnonymousDiscardCsrfPolicy = 'required' | 'session_cookie_only';

export type AnonymousDiscardCsrfInput =
  | {
      policy: 'required';
      providedToken: string | null | undefined;
      expectedToken: string | null | undefined;
    }
  | { policy: 'session_cookie_only' };

export type AnonymousDiscardDecision =
  | { allowed: true; stage: AnonymousMergeStage }
  | { allowed: false; reason: AnonymousDiscardBlockReason; detail: string };

export type AnonymousDiscardBlockReason =
  | 'discard_blocked_pending_outcome'
  | 'discard_blocked_failure_outcome'
  | 'csrf_token_missing'
  | 'csrf_token_mismatch'
  | 'unknown_outcome';

export function evaluateAnonymousDiscardDecision(args: {
  stage: AnonymousMergeStage;
  outcome: AnonymousMergeOutcome | string;
  csrf?: AnonymousDiscardCsrfInput;
}): AnonymousDiscardDecision {
  // CSRF 게이트가 먼저 — 토큰 검증 실패는 outcome 과 무관하게 즉시 차단.
  if (args.csrf?.policy === 'required') {
    const { providedToken, expectedToken } = args.csrf;
    if (
      providedToken === null ||
      providedToken === undefined ||
      providedToken === '' ||
      expectedToken === null ||
      expectedToken === undefined ||
      expectedToken === ''
    ) {
      return {
        allowed: false,
        reason: 'csrf_token_missing',
        detail:
          'CSRF 정책이 required 인 sign-out 호출에 providedToken 또는 expectedToken 이 ' +
          '비어 있습니다. 호출자가 안전 저장소에서 토큰을 주입했는지 확인하세요.',
      };
    }
    if (providedToken !== expectedToken) {
      return {
        allowed: false,
        reason: 'csrf_token_mismatch',
        detail:
          'CSRF 토큰이 일치하지 않습니다. 다른 origin / 다른 세션에서의 sign-out 위조 ' +
          '시도일 수 있으므로 즉시 차단합니다.',
      };
    }
  }

  switch (args.outcome) {
    case 'success':
      return { allowed: true, stage: args.stage };
    case 'pending':
      return {
        allowed: false,
        reason: 'discard_blocked_pending_outcome',
        detail:
          `${args.stage} 단계가 아직 결과를 확정하지 않았습니다. ` +
          `익명 세션은 성공 콜백 이후에만 폐기할 수 있습니다.`,
      };
    case 'failure':
      return {
        allowed: false,
        reason: 'discard_blocked_failure_outcome',
        detail:
          `${args.stage} 단계가 실패했습니다. 익명 세션을 먼저 폐기하면 ` +
          `사용자가 익명 상태로 복귀할 수 없어 데이터 손실 위험이 있습니다. ` +
          `실패 상태를 UI/에러 핸들러로 전달하고 익명 세션은 유지하세요.`,
      };
    default:
      return {
        allowed: false,
        reason: 'unknown_outcome',
        detail: `outcome="${String(args.outcome)}" 는 허용되지 않습니다.`,
      };
  }
}

import type { Session } from '@supabase/supabase-js';
import { NextResponse, type NextRequest } from 'next/server';

import { serverApiBaseUrl } from '@/lib/api-base-url';
import { verifyFlowCookie } from '@/lib/flow-cookie';
import { isSafeNext, resolveSafeNext } from '@/lib/safe-redirect';
import { siteOriginFromRequest } from '@/lib/site-url';
import { createRouteHandlerClient } from '@/lib/supabase/server';
import {
  isSupabaseProvider,
  isUiProvider,
  toUiProviderId,
  type SupabaseProvider,
  type UiProvider,
} from '@/lib/supabase/providers';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export const COMMIT_PATH = '/auth/anon-merge-intents/commit';

const FLOW_CONTEXT_COOKIE = 'jippin_oauth_provider';
const MERGE_INTENT_COOKIE = 'jippin_merge_intent';
const PENDING_ANONYMOUS_COOKIE = 'jippin_pending_anonymous_user_id';
const TERMS_PENDING_HINT_COOKIE = 'jippin_terms_pending';
const TERMS_PENDING_HINT_MAX_AGE_SECONDS = 10 * 60;
const BACKEND_CALLBACK_TIMEOUT_MS = 5_000;
const VALID_INTENTS = ['link', 'signin', 'link-merge'] as const;
const KNOWN_REASONS = new Set([
  'missing_code',
  'exchange_failed',
  'oauth_error',
  'access_denied',
  'server_error',
  'temporarily_unavailable',
  'identity_already_exists',
  'oauth_init_failed',
  'oauth_guard_stale',
  'merge_commit_failed',
  'merge_unavailable',
  'kakao_sync_unavailable',
]);

type FlowIntent = (typeof VALID_INTENTS)[number];
type FlowContext = {
  intent: FlowIntent;
  provider: UiProvider;
  supabaseProvider: SupabaseProvider;
  createdAt: number | null;
};
type FlowContextResult =
  | { ok: true; context: FlowContext | null }
  | { ok: false; provider: SupabaseProvider | null };

type BackendSessionBridgeResult = {
  signup_complete?: boolean;
  missing_required_terms?: string[];
  redirect_url?: string | null;
};

function origin(request: NextRequest): string {
  return siteOriginFromRequest(request);
}

function defaultNext(): string {
  const configured = process.env.NEXT_PUBLIC_FRONTEND_AUTH_SUCCESS_URL;
  return configured ? resolveSafeNext(configured, '/') : '/';
}

function sanitizeReason(raw: string | null | undefined): string {
  return raw && KNOWN_REASONS.has(raw) ? raw : 'oauth_error';
}

function sanitizeFailureBase(request: NextRequest): string {
  const fallback = '/auth/failure';
  const configured = process.env.NEXT_PUBLIC_FRONTEND_AUTH_FAILURE_URL ?? fallback;
  try {
    const target = new URL(configured, origin(request));
    return target.origin === origin(request) ? `${target.pathname}${target.search}` : fallback;
  } catch {
    return fallback;
  }
}

function isFlowIntent(value: string | null | undefined): value is FlowIntent {
  return typeof value === 'string' && (VALID_INTENTS as readonly string[]).includes(value);
}

function setCookieValues(headers: Headers): string[] {
  const withGetSetCookie = headers as Headers & { getSetCookie?: () => string[] };
  const values = withGetSetCookie.getSetCookie?.();
  if (values?.length) return values;
  const value = headers.get('set-cookie');
  return value ? value.split(/,(?=\s*[^,;]+=)/g) : [];
}

function copyBackendSessionCookies(source: Response, target: NextResponse): void {
  for (const cookie of setCookieValues(source.headers)) {
    target.headers.append('Set-Cookie', cookie);
  }
}

export function expireCallbackCookies(response: NextResponse): NextResponse {
  appendCookie(response, `${MERGE_INTENT_COOKIE}=; Path=/auth/callback; Max-Age=0`);
  appendCookie(response, `${FLOW_CONTEXT_COOKIE}=; Path=/auth/callback; Max-Age=0`);
  return response;
}

function expirePendingAnonymousCookie(response: NextResponse): NextResponse {
  appendCookie(response, `${PENDING_ANONYMOUS_COOKIE}=; Path=/auth; Max-Age=0`);
  return response;
}

function expireTermsPendingCookie(response: NextResponse): NextResponse {
  appendCookie(response, `${TERMS_PENDING_HINT_COOKIE}=; Path=/; Max-Age=0`);
  return response;
}

function appendCookie(response: NextResponse, cookie: string): void {
  response.headers.append('Set-Cookie', cookie);
}

function redirectFromSeed(seed: NextResponse, target: URL): NextResponse {
  seed.headers.set('Location', target.toString());
  return new NextResponse(null, { status: 302, headers: seed.headers });
}

function failureRedirect(
  request: NextRequest,
  reason: string | null | undefined,
  seed: NextResponse = new NextResponse(null),
  context?: { next?: string | null; provider?: SupabaseProvider | null },
): NextResponse {
  const target = new URL(sanitizeFailureBase(request), origin(request));
  target.search = '';
  target.searchParams.set('reason', sanitizeReason(reason));
  const safeNext = resolveSafeNext(context?.next ?? request.nextUrl.searchParams.get('next'), '/');
  if (safeNext !== '/') target.searchParams.set('next', safeNext);
  if (context?.provider) target.searchParams.set('provider', toUiProviderId(context.provider));
  return expireTermsPendingCookie(
    expirePendingAnonymousCookie(expireCallbackCookies(redirectFromSeed(seed, target))),
  );
}

async function failureRedirectAfterExchange(
  request: NextRequest,
  reason: string | null | undefined,
  supabase: ReturnType<typeof createRouteHandlerClient>,
  context?: { next?: string | null; provider?: SupabaseProvider | null },
): Promise<NextResponse> {
  try {
    await supabase.auth.signOut();
  } catch {
    // Do not expose a half-authenticated browser state on post-exchange failures.
  }
  return failureRedirect(request, reason, new NextResponse(null), context);
}

function flowContext(request: NextRequest): FlowContextResult {
  const raw = request.cookies.get(FLOW_CONTEXT_COOKIE)?.value;
  if (!raw) return { ok: true, context: null };

  const verified = verifyFlowCookie(raw);
  if (!verified.ok) return { ok: false, provider: null };

  const intent = verified.payload.intent;
  const provider = verified.payload.provider;
  const supabaseProvider = verified.payload.supabase_provider;
  if (!isFlowIntent(intent) || !isUiProvider(provider) || !isSupabaseProvider(supabaseProvider)) {
    return { ok: false, provider: null };
  }

  const iat = Number.parseInt(verified.payload.iat ?? '', 10);
  return {
    ok: true,
    context: {
      intent,
      provider,
      supabaseProvider,
      createdAt: Number.isFinite(iat) ? iat * 1000 : null,
    },
  };
}

function callbackIntent(request: NextRequest, context: FlowContext | null): FlowIntent | null {
  const intent = request.nextUrl.searchParams.get('intent');
  if (isFlowIntent(intent)) return intent;
  return context?.intent ?? null;
}

async function boundedFetch(input: string | URL, init: RequestInit): Promise<Response | null> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), BACKEND_CALLBACK_TIMEOUT_MS);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

async function mintBackendSession(
  session: Session,
  anonymousUserId: string | null,
  requestedProvider: UiProvider | null,
  response: NextResponse,
): Promise<BackendSessionBridgeResult | null> {
  const bridge = await boundedFetch(`${serverApiBaseUrl()}/auth/supabase/session`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${session.access_token}`,
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      anonymous_user_id: anonymousUserId,
      requested_provider: requestedProvider,
    }),
    cache: 'no-store',
  });
  if (!bridge?.ok) return null;
  copyBackendSessionCookies(bridge, response);
  return (await bridge.json()) as BackendSessionBridgeResult;
}

async function linkBackendAccount(
  session: Session,
  requestedProvider: UiProvider,
  request: NextRequest,
): Promise<boolean> {
  const cookie = request.headers.get('cookie');
  const headers: Record<string, string> = {
    Authorization: `Bearer ${session.access_token}`,
    Accept: 'application/json',
    'Content-Type': 'application/json',
  };
  if (cookie) headers.Cookie = cookie;

  const link = await boundedFetch(`${serverApiBaseUrl()}/auth/supabase/link`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ requested_provider: requestedProvider }),
    cache: 'no-store',
  });
  return Boolean(link?.ok);
}

async function commitMergeIntent(session: Session, signedIntentCookie: string): Promise<boolean> {
  const response = await boundedFetch(new URL(COMMIT_PATH, serverApiBaseUrl()), {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      authorization: `Bearer ${session.access_token}`,
    },
    body: JSON.stringify({ signed_intent_cookie_value: signedIntentCookie }),
    cache: 'no-store',
  });
  return Boolean(response?.ok);
}

function termsRedirect(
  request: NextRequest,
  seed: NextResponse,
  safeNext: string,
  redirectUrl?: string | null,
): NextResponse {
  const target = new URL(redirectUrl ?? '/auth/terms', origin(request));
  target.searchParams.set('next', safeNext);
  appendCookie(
    seed,
    `${TERMS_PENDING_HINT_COOKIE}=1; Path=/; Max-Age=${TERMS_PENDING_HINT_MAX_AGE_SECONDS}; SameSite=Lax`,
  );
  return expirePendingAnonymousCookie(expireCallbackCookies(redirectFromSeed(seed, target)));
}

function successRedirect(request: NextRequest, seed: NextResponse, safeNext: string): NextResponse {
  const done = new URL('/auth/callback-done', origin(request));
  done.searchParams.set('next', safeNext);
  return expireTermsPendingCookie(
    expirePendingAnonymousCookie(expireCallbackCookies(redirectFromSeed(seed, done))),
  );
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const url = request.nextUrl;
  const errorCode = url.searchParams.get('error');
  const code = url.searchParams.get('code');
  const nextRaw = url.searchParams.get('next');
  const safeNext = nextRaw && isSafeNext(nextRaw) ? nextRaw : defaultNext();
  const parsedFlow = flowContext(request);
  const context = parsedFlow.ok ? parsedFlow.context : null;

  if (!parsedFlow.ok) {
    return failureRedirect(request, 'oauth_guard_stale', undefined, {
      next: nextRaw,
      provider: parsedFlow.provider,
    });
  }
  if (errorCode) {
    return failureRedirect(request, errorCode, undefined, {
      next: nextRaw,
      provider: context?.supabaseProvider,
    });
  }
  if (!code) {
    return failureRedirect(request, 'missing_code', undefined, {
      next: nextRaw,
      provider: context?.supabaseProvider,
    });
  }

  const seed = new NextResponse(null);
  const supabase = createRouteHandlerClient({ request, response: seed });
  const { data, error } = await supabase.auth.exchangeCodeForSession(code);

  if (error || !data?.session) {
    return failureRedirect(request, error?.code ?? 'exchange_failed', seed, {
      next: nextRaw,
      provider: context?.supabaseProvider,
    });
  }

  const intent = callbackIntent(request, context);
  if (intent === 'link') {
    if (!context || !(await linkBackendAccount(data.session, context.provider, request))) {
      return failureRedirectAfterExchange(request, 'oauth_error', supabase, {
        next: safeNext,
        provider: context?.supabaseProvider,
      });
    }
    return successRedirect(request, seed, safeNext);
  }

  const bridge = await mintBackendSession(
    data.session,
    url.searchParams.get('anonymous_user_id'),
    context?.provider ?? null,
    seed,
  );
  if (!bridge) {
    return failureRedirectAfterExchange(request, 'exchange_failed', supabase, {
      next: safeNext,
      provider: context?.supabaseProvider,
    });
  }

  const mergeIntentCookie = request.cookies.get(MERGE_INTENT_COOKIE)?.value ?? null;
  if (mergeIntentCookie && !(await commitMergeIntent(data.session, mergeIntentCookie))) {
    return failureRedirectAfterExchange(request, 'merge_commit_failed', supabase, {
      next: safeNext,
      provider: context?.supabaseProvider,
    });
  }

  if (bridge.signup_complete === false || (bridge.missing_required_terms?.length ?? 0) > 0) {
    return termsRedirect(request, seed, safeNext, bridge.redirect_url);
  }

  return successRedirect(request, seed, safeNext);
}

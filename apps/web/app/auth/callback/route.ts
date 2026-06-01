import type { Session } from '@supabase/supabase-js';
import { NextResponse, type NextRequest } from 'next/server';

import { apiBaseUrl } from '@/lib/api-base-url';
import { isSafeNext, resolveSafeNext } from '@/lib/safe-redirect';
import { siteOriginFromRequest } from '@/lib/site-url';
import { isOAuthFlowContextStale, parseOAuthFlowContext } from '@/lib/supabase/flow-context';
import { detectNewlyLinkedProvider } from '@/lib/supabase/identities';
import { createRouteHandlerClient } from '@/lib/supabase/server';
import {
  isKakaoProvider,
  requiresInternalTerms,
  toUiProviderId,
  type SupabaseProvider,
} from '@/lib/supabase/providers';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export const COMMIT_PATH = '/auth/anon-merge-intents/commit';

const CALLBACK_COOKIES = ['jippin_merge_intent', 'jippin_oauth_provider'] as const;
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

function kakaoAuditEnabled(): boolean {
  return process.env.NEXT_PUBLIC_AUTH_KAKAO_SYNC_AUDIT_ENABLED === 'true';
}

export function expireCallbackCookies(response: NextResponse): NextResponse {
  for (const name of CALLBACK_COOKIES) {
    response.cookies.set(name, '', { path: '/auth/callback', maxAge: 0 });
  }
  return response;
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
  return expireCallbackCookies(redirectFromSeed(seed, target));
}

async function commitMergeIntent(session: Session, signedIntentCookie: string): Promise<boolean> {
  const response = await fetch(new URL(COMMIT_PATH, apiBaseUrl()), {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      authorization: `Bearer ${session.access_token}`,
    },
    body: JSON.stringify({ signed_intent_cookie_value: signedIntentCookie }),
  });
  return response.ok;
}

async function persistKakaoSyncConsent(
  session: Session,
  linkedProvider: Extract<SupabaseProvider, 'kakao' | 'custom:kakao'>,
): Promise<boolean> {
  if (!kakaoAuditEnabled()) return false;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 750);
  try {
    const response = await fetch(`${apiBaseUrl()}/auth/terms/kakao-sync`, {
      method: 'POST',
      signal: controller.signal,
      headers: {
        'content-type': 'application/json',
        authorization: `Bearer ${session.access_token}`,
      },
      body: JSON.stringify({
        supabase_user_id: session.user.id,
        linked_provider: linkedProvider,
        provider_access_token: session.provider_token ?? null,
        provider_refresh_token: session.provider_refresh_token ?? null,
      }),
    });
    return response.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

function termsRedirect(request: NextRequest, seed: NextResponse, safeNext: string): NextResponse {
  const target = new URL('/auth/terms', origin(request));
  target.searchParams.set('next', safeNext);
  return expireCallbackCookies(redirectFromSeed(seed, target));
}

function successRedirect(request: NextRequest, seed: NextResponse, safeNext: string): NextResponse {
  const done = new URL('/auth/callback-done', origin(request));
  done.searchParams.set('next', safeNext);
  return expireCallbackCookies(redirectFromSeed(seed, done));
}

function isLikelyFirstSignup(session: Session): boolean {
  const createdAt = Date.parse(session.user.created_at ?? '');
  if (!Number.isFinite(createdAt)) return false;
  return Math.abs(Date.now() - createdAt) <= 10 * 60 * 1000;
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const url = request.nextUrl;
  const errorCode = url.searchParams.get('error');
  const code = url.searchParams.get('code');
  const nextRaw = url.searchParams.get('next');
  const safeNext = nextRaw && isSafeNext(nextRaw) ? nextRaw : defaultNext();
  const intendedProviderCookie = request.cookies.get('jippin_oauth_provider')?.value ?? null;
  const flowContext = parseOAuthFlowContext(intendedProviderCookie);

  if (errorCode) {
    return failureRedirect(request, errorCode, undefined, {
      next: nextRaw,
      provider: flowContext?.provider,
    });
  }
  if (!code) {
    return failureRedirect(request, 'missing_code', undefined, {
      next: nextRaw,
      provider: flowContext?.provider,
    });
  }
  if (isOAuthFlowContextStale(intendedProviderCookie)) {
    return failureRedirect(request, 'oauth_guard_stale', undefined, {
      next: nextRaw,
      provider: flowContext?.provider,
    });
  }

  const seed = new NextResponse(null);
  const supabase = createRouteHandlerClient({ request, response: seed });
  const { data, error } = await supabase.auth.exchangeCodeForSession(code);

  if (error || !data?.session) {
    return failureRedirect(request, error?.code ?? 'exchange_failed', seed, {
      next: nextRaw,
      provider: flowContext?.provider,
    });
  }

  const mergeIntentCookie = request.cookies.get('jippin_merge_intent')?.value ?? null;
  let mergeStatus: 'none' | 'committed' | 'commit_failed' = 'none';
  if (mergeIntentCookie) {
    try {
      mergeStatus = (await commitMergeIntent(data.session, mergeIntentCookie))
        ? 'committed'
        : 'commit_failed';
    } catch {
      mergeStatus = 'commit_failed';
    }
  }

  const linkedProvider = detectNewlyLinkedProvider(data.session.user, intendedProviderCookie);
  if (isKakaoProvider(linkedProvider)) {
    const persisted = await persistKakaoSyncConsent(data.session, linkedProvider);
    if (!persisted) {
      return failureRedirect(request, 'kakao_sync_unavailable', seed, {
        next: safeNext,
        provider: linkedProvider,
      });
    }
  }

  if (mergeStatus === 'commit_failed') {
    return failureRedirect(request, 'merge_commit_failed', seed, {
      next: safeNext,
      provider: linkedProvider,
    });
  }

  if (requiresInternalTerms(linkedProvider) && isLikelyFirstSignup(data.session)) {
    return termsRedirect(request, seed, safeNext);
  }

  return successRedirect(request, seed, safeNext);
}

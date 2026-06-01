import type { Session } from '@supabase/supabase-js';
import { NextResponse, type NextRequest } from 'next/server';

import { apiBaseUrl } from '@/lib/api-base-url';
import { isSafeNext } from '@/lib/safe-redirect';
import { detectNewlyLinkedProvider } from '@/lib/supabase/identities';
import { createRouteHandlerClient } from '@/lib/supabase/server';
import type { SupabaseProvider } from '@/lib/supabase/providers';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export const COMMIT_PATH = '/auth/anon-merge-intents/commit';

const SIGNIN_INTENT_COOKIE = 'jippin_signin_intent';
const CALLBACK_COOKIES = [
  'jippin_merge_intent',
  'jippin_oauth_provider',
  SIGNIN_INTENT_COOKIE,
] as const;
const KNOWN_REASONS = new Set([
  'missing_code',
  'missing_signin_intent',
  'exchange_failed',
  'oauth_error',
  'access_denied',
  'server_error',
  'temporarily_unavailable',
  'identity_already_exists',
]);

function origin(request: NextRequest): string {
  return new URL('/', request.url).origin;
}

function defaultNext(): string {
  return process.env.NEXT_PUBLIC_FRONTEND_AUTH_SUCCESS_URL ?? '/';
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
): NextResponse {
  const target = new URL(sanitizeFailureBase(request), origin(request));
  target.search = '';
  target.searchParams.set('reason', sanitizeReason(reason));
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
): Promise<void> {
  await fetch(`${apiBaseUrl()}/auth/terms/kakao-sync`, {
    method: 'POST',
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
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const url = request.nextUrl;
  const errorCode = url.searchParams.get('error');
  const code = url.searchParams.get('code');
  const nextRaw = url.searchParams.get('next');
  const safeNext = nextRaw && isSafeNext(nextRaw) ? nextRaw : defaultNext();

  if (errorCode) return failureRedirect(request, errorCode);
  if (!code) return failureRedirect(request, 'missing_code');
  if (!request.cookies.has(SIGNIN_INTENT_COOKIE)) {
    return failureRedirect(request, 'missing_signin_intent');
  }

  const seed = new NextResponse(null);
  const supabase = createRouteHandlerClient({ request, response: seed });
  const { data, error } = await supabase.auth.exchangeCodeForSession(code);

  if (error || !data?.session) {
    return failureRedirect(request, error?.code ?? 'exchange_failed', seed);
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

  const intendedProviderCookie = request.cookies.get('jippin_oauth_provider')?.value ?? null;
  const linkedProvider = detectNewlyLinkedProvider(data.session.user, intendedProviderCookie);
  if (linkedProvider === 'kakao' || linkedProvider === 'custom:kakao') {
    await persistKakaoSyncConsent(data.session, linkedProvider).catch(() => undefined);
  }

  const done = new URL('/auth/callback-done', origin(request));
  done.searchParams.set('next', safeNext);
  if (mergeStatus === 'commit_failed') {
    done.searchParams.set('merge', 'failed');
  }

  return expireCallbackCookies(redirectFromSeed(seed, done));
}

import { NextResponse, type NextRequest } from 'next/server';

import { apiBaseUrl } from '@/lib/api-base-url';
import { resolveSafeNext } from '@/lib/safe-redirect';
import { siteOriginFromRequest } from '@/lib/site-url';
import { createRouteHandlerClient } from '@/lib/supabase/server';
import { encodeOAuthFlowContext } from '@/lib/supabase/flow-context';
import {
  isUiProvider,
  toSupabaseProviderId,
  type UiProvider,
  type SupabaseProvider,
} from '@/lib/supabase/providers';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

const FLOW_CONTEXT_COOKIE = 'jippin_oauth_provider';
const MERGE_INTENT_COOKIE = 'jippin_merge_intent';
const PENDING_ANONYMOUS_COOKIE = 'jippin_pending_anonymous_user_id';
const CALLBACK_COOKIE_MAX_AGE_SECONDS = 300;
const PENDING_ANONYMOUS_MAX_AGE_SECONDS = 10 * 60;
const VALID_INTENTS = ['link', 'signin', 'link-merge'] as const;

type Intent = (typeof VALID_INTENTS)[number];

function isIntent(value: string | null): value is Intent {
  return value !== null && (VALID_INTENTS as readonly string[]).includes(value);
}

function badRequest(message: string): NextResponse {
  return NextResponse.json(
    { error: { code: 'invalid_request', message } },
    { status: 400 },
  );
}

function callbackUrl(request: NextRequest): string {
  const configured = process.env.NEXT_PUBLIC_FRONTEND_AUTH_CALLBACK_URL;
  const callback = configured
    ? new URL(configured)
    : new URL('/auth/callback', siteOriginFromRequest(request));
  callback.searchParams.set(
    'next',
    resolveSafeNext(
      request.nextUrl.searchParams.get('next'),
      process.env.NEXT_PUBLIC_FRONTEND_AUTH_SUCCESS_URL ?? '/',
    ),
  );
  return callback.toString();
}

function anonymousUserIdFromRequest(request: NextRequest): string | null {
  return (
    request.nextUrl.searchParams.get('anonymous_user_id') ??
    request.cookies.get('jippin_anonymous_user_id')?.value ??
    null
  );
}

async function enqueueMergeIntent(
  request: NextRequest,
  provider: SupabaseProvider,
): Promise<string> {
  const anonymousUserId = anonymousUserIdFromRequest(request);
  if (!anonymousUserId) {
    throw new Error('anonymous_user_id is required for merge intent enqueue');
  }
  const response = await fetch(`${apiBaseUrl()}/auth/anon-merge-intents`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      anonymous_user_id: anonymousUserId,
      provider,
      next: resolveSafeNext(request.nextUrl.searchParams.get('next'), '/'),
    }),
  });

  if (!response.ok) {
    throw new Error(`merge intent enqueue failed (${response.status})`);
  }

  const data = (await response.json()) as { signed_token?: string };
  if (!data.signed_token) {
    throw new Error('merge intent response missing signed_token');
  }
  return data.signed_token;
}

function setCallbackCookie(response: NextResponse, name: string, value: string): void {
  // New OAuth starts overwrite stale callback flow cookies with a 5-minute TTL.
  // Supabase's PKCE state/code_verifier cookies are emitted by @supabase/ssr in the same response;
  // this app does not re-sign them and relies on Supabase SSR's built-in PKCE verifier handling.
  response.cookies.set({
    name,
    value,
    httpOnly: true,
    secure: true,
    sameSite: 'lax',
    path: '/auth/callback',
    maxAge: CALLBACK_COOKIE_MAX_AGE_SECONDS,
  });
}

function expireCallbackCookie(response: NextResponse, name: string): void {
  response.cookies.set(name, '', { path: '/auth/callback', maxAge: 0 });
}

function expirePendingAnonymousCookie(response: NextResponse): void {
  response.cookies.set(PENDING_ANONYMOUS_COOKIE, '', { path: '/auth', maxAge: 0 });
}

function setPendingAnonymousCookie(response: NextResponse, anonymousUserId: string): void {
  response.cookies.set({
    name: PENDING_ANONYMOUS_COOKIE,
    value: anonymousUserId,
    httpOnly: true,
    secure: true,
    sameSite: 'lax',
    path: '/auth',
    maxAge: PENDING_ANONYMOUS_MAX_AGE_SECONDS,
  });
}

function redirectToFailure(
  request: NextRequest,
  response: NextResponse,
  reason: string,
  context?: { provider?: UiProvider; next?: string | null },
): NextResponse {
  expireCallbackCookie(response, FLOW_CONTEXT_COOKIE);
  expireCallbackCookie(response, MERGE_INTENT_COOKIE);
  expirePendingAnonymousCookie(response);
  const failure = new URL('/auth/failure', siteOriginFromRequest(request));
  failure.searchParams.set('reason', reason);
  if (context?.provider) failure.searchParams.set('provider', context.provider);
  const safeNext = resolveSafeNext(context?.next ?? request.nextUrl.searchParams.get('next'), '/');
  if (safeNext !== '/') failure.searchParams.set('next', safeNext);
  response.headers.set('Location', failure.toString());
  return new NextResponse(null, { status: 302, headers: response.headers });
}

function redirectWithAccumulatedCookies(response: NextResponse, location: string): NextResponse {
  response.headers.set('Location', location);
  return new NextResponse(null, { status: 302, headers: response.headers });
}

async function signOutAfterServerMergeIntent(
  supabase: ReturnType<typeof createRouteHandlerClient>,
): Promise<void> {
  await supabase.auth.signOut();
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const url = request.nextUrl;
  const providerRaw = url.searchParams.get('provider');

  if (!isUiProvider(providerRaw)) {
    return badRequest('provider must be google, kakao, or naver');
  }

  const intentRaw = url.searchParams.get('intent');
  const intent: Intent = isIntent(intentRaw) ? intentRaw : 'link';
  const provider = toSupabaseProviderId(providerRaw);
  // Route Handler accumulator only. Do not use NextResponse.next() here; that is middleware-only.
  // The final return is always a real 302/JSON response carrying this accumulator's headers.
  const response = new NextResponse(null);
  const supabase = createRouteHandlerClient({ request, response });
  const anonymousUserId = anonymousUserIdFromRequest(request);

  setCallbackCookie(response, FLOW_CONTEXT_COOKIE, encodeOAuthFlowContext(provider));
  if (anonymousUserId) {
    setPendingAnonymousCookie(response, anonymousUserId);
  }

  if (intent === 'link-merge') {
    let signedToken: string;
    try {
      signedToken = await enqueueMergeIntent(request, provider);
    } catch (error) {
      console.warn('[auth/oauth/start] merge intent enqueue failed', {
        message: error instanceof Error ? error.message : 'unknown',
      });
      return redirectToFailure(request, response, 'merge_unavailable', {
        provider: providerRaw,
        next: url.searchParams.get('next'),
      });
    }
    setCallbackCookie(response, MERGE_INTENT_COOKIE, signedToken);
    await signOutAfterServerMergeIntent(supabase);
  }

  const options = {
    redirectTo: callbackUrl(request),
    skipBrowserRedirect: true,
  };
  const result =
    intent === 'link'
      ? await supabase.auth.linkIdentity({
          provider: provider as never,
          options,
        })
      : await supabase.auth.signInWithOAuth({
          provider: provider as never,
          options,
        });

  if (result.error || !result.data?.url) {
    const reason =
      result.error?.code === 'identity_already_exists'
        ? 'identity_already_exists'
        : 'oauth_init_failed';
    console.warn('[auth/oauth/start] oauth url generation failed', {
      code: result.error?.code ?? reason,
    });
    return redirectToFailure(request, response, reason, {
      provider: providerRaw,
      next: url.searchParams.get('next'),
    });
  }

  return redirectWithAccumulatedCookies(response, result.data.url);
}

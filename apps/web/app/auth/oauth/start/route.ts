import { NextResponse, type NextRequest } from 'next/server';

import { apiBaseUrl } from '@/lib/api-base-url';
import { resolveSafeNext } from '@/lib/safe-redirect';
import { siteOriginFromRequest } from '@/lib/site-url';
import { createRouteHandlerClient } from '@/lib/supabase/server';
import {
  isUiProvider,
  toSupabaseProviderId,
  type SupabaseProvider,
} from '@/lib/supabase/providers';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

const FLOW_CONTEXT_COOKIE = 'jippin_oauth_provider';
const MERGE_INTENT_COOKIE = 'jippin_merge_intent';
const CALLBACK_COOKIE_MAX_AGE_SECONDS = 300;
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

async function enqueueMergeIntent(
  request: NextRequest,
  provider: SupabaseProvider,
): Promise<string> {
  const anonymousUserId =
    request.nextUrl.searchParams.get('anonymous_user_id') ??
    request.cookies.get('jippin_anonymous_user_id')?.value ??
    null;
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

function redirectToFailure(
  request: NextRequest,
  response: NextResponse,
  reason: string,
): NextResponse {
  expireCallbackCookie(response, FLOW_CONTEXT_COOKIE);
  expireCallbackCookie(response, MERGE_INTENT_COOKIE);
  const failure = new URL('/auth/failure', siteOriginFromRequest(request));
  failure.searchParams.set('reason', reason);
  response.headers.set('Location', failure.toString());
  return new NextResponse(null, { status: 302, headers: response.headers });
}

function redirectWithAccumulatedCookies(response: NextResponse, location: string): NextResponse {
  response.headers.set('Location', location);
  return new NextResponse(null, { status: 302, headers: response.headers });
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
  const response = new NextResponse(null);
  const supabase = createRouteHandlerClient({ request, response });

  setCallbackCookie(response, FLOW_CONTEXT_COOKIE, provider);

  if (intent === 'link-merge') {
    const signedToken =
      url.searchParams.get('signed_token') ?? (await enqueueMergeIntent(request, provider));
    setCallbackCookie(response, MERGE_INTENT_COOKIE, signedToken);
    await supabase.auth.signOut();
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
    console.warn('[auth/oauth/start] oauth url generation failed', {
      code: result.error?.code ?? 'oauth_init_failed',
    });
    return redirectToFailure(request, response, 'oauth_init_failed');
  }

  return redirectWithAccumulatedCookies(response, result.data.url);
}

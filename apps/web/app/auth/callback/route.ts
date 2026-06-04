import { type NextRequest, NextResponse } from 'next/server';

import { serverApiBaseUrl } from '@/lib/api-base-url';
import { verifyFlowCookie } from '@/lib/flow-cookie';
import { createRouteHandlerClient } from '@/lib/supabase/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const FLOW_CONTEXT_COOKIE = 'jippin_oauth_provider';

function safeRelativeRedirect(value: string | null): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.includes('\\')) {
    return '/';
  }

  return value;
}

function termsRedirectUrl(redirectUrl: string | null | undefined, next: string, origin: string): string {
  const url = new URL(redirectUrl ?? '/auth/terms', origin);
  if (next !== '/') {
    url.searchParams.set('next', next);
  }
  return url.toString();
}

function setCookieValues(headers: Headers): string[] {
  const withGetSetCookie = headers as Headers & { getSetCookie?: () => string[] };
  const values = withGetSetCookie.getSetCookie?.();
  if (values?.length) {
    return values;
  }
  const value = headers.get('set-cookie');
  return value ? value.split(/,(?=\s*[^,;]+=)/g) : [];
}

function copyBackendSessionCookies(source: Response, target: NextResponse): void {
  for (const cookie of setCookieValues(source.headers)) {
    target.headers.append('Set-Cookie', cookie);
  }
}

function failureRedirect(request: NextRequest, headers?: Headers): NextResponse {
  const nextHeaders = headers ? new Headers(headers) : new Headers();
  nextHeaders.set(
    'Location',
    new URL('/login?error=oauth_callback_failed', request.nextUrl.origin).toString(),
  );
  return new NextResponse(null, { status: 302, headers: nextHeaders });
}

type BackendSessionBridgeResult = {
  signup_complete?: boolean;
  missing_required_terms?: string[];
  redirect_url?: string | null;
};

type FlowIntent = 'link' | 'signin' | 'link-merge';
type UiProvider = 'google' | 'kakao' | 'naver';
type FlowContext = { intent: FlowIntent; provider: UiProvider };

function isFlowIntent(value: string | undefined): value is FlowIntent {
  return value === 'link' || value === 'signin' || value === 'link-merge';
}

function isUiProvider(value: string | undefined): value is UiProvider {
  return value === 'google' || value === 'kakao' || value === 'naver';
}

function flowContext(request: NextRequest): FlowContext | null {
  const raw = request.cookies.get(FLOW_CONTEXT_COOKIE)?.value;
  if (!raw) {
    return null;
  }
  const verified = verifyFlowCookie(raw);
  if (!verified.ok) {
    return null;
  }
  const intent = verified.payload.intent;
  const provider = verified.payload.provider;
  return isFlowIntent(intent) && isUiProvider(provider)
    ? { intent, provider }
    : null;
}

function callbackIntent(request: NextRequest): FlowIntent | null {
  const intent = request.nextUrl.searchParams.get('intent') ?? undefined;
  return isFlowIntent(intent) ? intent : null;
}

async function mintBackendSession(
  accessToken: string,
  anonymousUserId: string | null,
  requestedProvider: UiProvider | null,
  response: NextResponse,
): Promise<BackendSessionBridgeResult | null> {
  try {
    const bridge = await fetch(`${serverApiBaseUrl()}/auth/supabase/session`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        anonymous_user_id: anonymousUserId,
        requested_provider: requestedProvider,
      }),
      cache: 'no-store',
    });
    if (!bridge.ok) {
      return null;
    }
    copyBackendSessionCookies(bridge, response);
    return (await bridge.json()) as BackendSessionBridgeResult;
  } catch {
    return null;
  }
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const code = request.nextUrl.searchParams.get('code');
  const next = safeRelativeRedirect(request.nextUrl.searchParams.get('next'));
  const anonymousUserId = request.nextUrl.searchParams.get('anonymous_user_id');
  const context = flowContext(request);
  const intent = callbackIntent(request);
  const response = new NextResponse(null);

  if (code) {
    const supabase = createRouteHandlerClient({ request, response });
    const { data, error } = await supabase.auth.exchangeCodeForSession(code);
    const accessToken = data.session?.access_token;
    const isLinkCallback = intent === 'link' || context?.intent === 'link';
    if (!error && accessToken && isLinkCallback) {
      if (intent === 'link' && context?.intent === 'link') {
        response.headers.set('Location', new URL(next, request.nextUrl.origin).toString());
        return new NextResponse(null, { status: 302, headers: response.headers });
      }
      return failureRedirect(request);
    } else if (!error && accessToken) {
      const bridge = await mintBackendSession(
        accessToken,
        anonymousUserId,
        context?.provider ?? null,
        response,
      );

      if (bridge) {
        const redirectTarget = bridge.signup_complete === false
          ? termsRedirectUrl(bridge.redirect_url, next, request.nextUrl.origin)
          : new URL(next, request.nextUrl.origin).toString();
        response.headers.set('Location', redirectTarget);
        return new NextResponse(null, { status: 302, headers: response.headers });
      }
      return failureRedirect(request);
    }
  }

  return failureRedirect(request, response.headers);
}

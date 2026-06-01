import { type NextRequest, NextResponse } from 'next/server';

import { apiBaseUrl } from '@/lib/api-base-url';
import { createRouteHandlerClient } from '@/lib/supabase/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

function safeRelativeRedirect(value: string | null): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.includes('\\')) {
    return '/';
  }

  return value;
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

type BackendSessionBridgeResult = {
  signup_complete?: boolean;
  missing_required_terms?: string[];
  redirect_url?: string | null;
};

async function mintBackendSession(
  accessToken: string,
  anonymousUserId: string | null,
  response: NextResponse,
): Promise<BackendSessionBridgeResult | null> {
  try {
    const bridge = await fetch(`${apiBaseUrl()}/auth/supabase/session`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ anonymous_user_id: anonymousUserId }),
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
  const response = new NextResponse(null);

  if (code) {
    const supabase = createRouteHandlerClient({ request, response });
    const { data, error } = await supabase.auth.exchangeCodeForSession(code);
    const bridge = data.session?.access_token
      ? await mintBackendSession(data.session.access_token, anonymousUserId, response)
      : null;

    if (!error && bridge) {
      const redirectTarget = bridge.signup_complete === false
        ? (bridge.redirect_url ?? '/auth/terms')
        : next;
      response.headers.set('Location', new URL(redirectTarget, request.nextUrl.origin).toString());
      return new NextResponse(null, { status: 302, headers: response.headers });
    }
  }

  response.headers.set(
    'Location',
    new URL('/login?error=oauth_callback_failed', request.nextUrl.origin).toString(),
  );
  return new NextResponse(null, { status: 302, headers: response.headers });
}

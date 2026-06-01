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

async function mintBackendSession(accessToken: string, response: NextResponse): Promise<boolean> {
  try {
    const bridge = await fetch(`${apiBaseUrl()}/auth/supabase/session`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        Accept: 'application/json',
      },
      cache: 'no-store',
    });
    if (!bridge.ok) {
      return false;
    }
    copyBackendSessionCookies(bridge, response);
    return true;
  } catch {
    return false;
  }
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const code = request.nextUrl.searchParams.get('code');
  const next = safeRelativeRedirect(request.nextUrl.searchParams.get('next'));
  const response = new NextResponse(null);

  if (code) {
    const supabase = createRouteHandlerClient({ request, response });
    const { data, error } = await supabase.auth.exchangeCodeForSession(code);

    if (!error && data.session?.access_token && (await mintBackendSession(data.session.access_token, response))) {
      response.headers.set('Location', new URL(next, request.nextUrl.origin).toString());
      return new NextResponse(null, { status: 302, headers: response.headers });
    }
  }

  response.headers.set(
    'Location',
    new URL('/login?error=oauth_callback_failed', request.nextUrl.origin).toString(),
  );
  return new NextResponse(null, { status: 302, headers: response.headers });
}

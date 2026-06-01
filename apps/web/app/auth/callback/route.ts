import { type NextRequest, NextResponse } from 'next/server';

import { createRouteHandlerClient } from '@/lib/supabase/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

function safeRelativeRedirect(value: string | null): string {
  if (!value || !value.startsWith('/') || value.startsWith('//')) {
    return '/';
  }

  return value;
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const code = request.nextUrl.searchParams.get('code');
  const next = safeRelativeRedirect(request.nextUrl.searchParams.get('next'));
  const response = NextResponse.next();

  if (code) {
    const supabase = createRouteHandlerClient({ request, response });
    const { error } = await supabase.auth.exchangeCodeForSession(code);

    if (!error) {
      response.headers.set('Location', new URL(next, request.nextUrl.origin).toString());
      return new NextResponse(null, { status: 302, headers: response.headers });
    }
  }

  return NextResponse.redirect(new URL('/login?error=oauth_callback_failed', request.nextUrl.origin));
}

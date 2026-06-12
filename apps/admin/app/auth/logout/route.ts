import { NextResponse, type NextRequest } from 'next/server';

import { createRouteHandlerClient } from '@/lib/supabase/server';

/** 관리자 로그아웃 — Supabase 세션 쿠키를 지우고 /login 으로 보낸다 (CMP-DIRECT). */

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest): Promise<NextResponse> {
  const response = new NextResponse(null);
  const supabase = createRouteHandlerClient({ request, response });
  await supabase.auth.signOut();

  const out = NextResponse.redirect(new URL('/login', request.url), 303);
  for (const cookie of response.headers.getSetCookie?.() ?? []) {
    out.headers.append('Set-Cookie', cookie);
  }
  return out;
}

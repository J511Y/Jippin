import { NextResponse, type NextRequest } from 'next/server';

import { createRouteHandlerClient } from '@/lib/supabase/server';

/** 관리자 로그아웃 — Supabase 세션 쿠키를 지우고 /login 으로 보낸다 (CMP-DIRECT). */

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest): Promise<NextResponse> {
  const response = new NextResponse(null);
  const supabase = createRouteHandlerClient({ request, response });
  // 메인 제품과 auth 공유 — 콘솔에서 나가는 것이 같은 계정의 타 기기/메인 제품
  // 세션까지 무효화하면 안 되므로 local scope 로 제한한다 (로그인 거부 경로와 동일).
  await supabase.auth.signOut({ scope: 'local' });

  const out = NextResponse.redirect(new URL('/login', request.url), 303);
  for (const cookie of response.headers.getSetCookie?.() ?? []) {
    out.headers.append('Set-Cookie', cookie);
  }
  return out;
}

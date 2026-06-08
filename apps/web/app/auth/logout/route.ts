import { type NextRequest, NextResponse } from 'next/server';

import { createRouteHandlerClient } from '@/lib/supabase/server';

/**
 * 로그아웃 Route Handler (CMP-DIRECT).
 *
 * 웹 origin 의 세션 쿠키를 정리한다: Supabase 세션(sb-*)은 `signOut()` 으로, 백엔드
 * 세션(jippin_session)은 즉시 만료 쿠키로 덮어쓴다. 프록시 가드(`proxy.ts`)가 보는
 * 쿠키이므로 같은 origin 응답에서 지워야 한다.
 */

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const AUTH_COOKIE_NAME = process.env.AUTH_COOKIE_NAME ?? 'jippin_session';

export async function POST(request: NextRequest): Promise<NextResponse> {
  const response = NextResponse.json({ ok: true });
  const supabase = createRouteHandlerClient({ request, response });
  await supabase.auth.signOut();
  response.cookies.set(AUTH_COOKIE_NAME, '', { maxAge: 0, path: '/' });
  return response;
}

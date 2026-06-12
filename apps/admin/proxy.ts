import { NextResponse, type NextRequest } from 'next/server';

import { isAdminUser } from '@/lib/auth';
import { updateSession } from '@/lib/supabase/proxy';

/**
 * 관리자 사이트 전역 인증 게이트 (CMP-DIRECT).
 *
 * apps/web 과 달리 deny-by-default: `/login` 과 로그인 Route Handler 를 제외한
 * 모든 경로는 `app_metadata.role === 'admin'` 세션이 없으면 `/login` 으로 보낸다.
 * 판별 기준은 lib/auth.ts 의 isAdminUser 단일 SSOT.
 *
 * 일반 사용자도 main Supabase 프로젝트에 이메일 가입이 가능하므로 "세션 존재"만으로는
 * 절대 통과시키지 않는다 — role 클레임 확인이 필수다.
 */

const PUBLIC_PATHNAMES = new Set(['/login', '/auth/login']);

function withSessionCookies(target: NextResponse, source: NextResponse): NextResponse {
  for (const cookie of source.cookies.getAll()) {
    target.cookies.set(cookie);
  }
  return target;
}

export async function proxy(request: NextRequest): Promise<NextResponse> {
  const { pathname } = request.nextUrl;
  const { supabaseResponse, user } = await updateSession(request);
  const isAdmin = isAdminUser(user);

  if (!PUBLIC_PATHNAMES.has(pathname) && !isAdmin) {
    const loginUrl = new URL('/login', request.url);
    if (pathname !== '/') {
      loginUrl.searchParams.set('next', pathname);
    }
    return withSessionCookies(NextResponse.redirect(loginUrl), supabaseResponse);
  }

  if (pathname === '/login' && isAdmin) {
    return withSessionCookies(NextResponse.redirect(new URL('/', request.url)), supabaseResponse);
  }

  return supabaseResponse;
}

export const config = {
  // 정적 자산(_next/* 및 확장자 있는 public 파일 — logo.png, site.webmanifest 등)만
  // 제외하고 전부 게이트를 태운다. 비로그인 상태의 /login 페이지도 로고/파비콘을
  // 받아야 하므로 dot 포함 경로는 게이트 대상이 아니다 (앱 라우트에는 dot 이 없다).
  matcher: ['/((?!_next/static|_next/image|.*\\..*).*)']
};

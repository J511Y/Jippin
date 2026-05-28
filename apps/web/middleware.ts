import { NextResponse, type NextRequest } from 'next/server';

/**
 * 보호 경로 미인증 가드 (CMP-529).
 *
 * - `/app/*` 경로는 인증 쿠키가 없으면 `/login` 으로 리다이렉트.
 * - 인증 쿠키 이름은 백엔드 AUTH 모듈과 합의된 `jippin_session` 을 가정한다.
 *   실제 발급/검증은 백엔드(`apps/api`) 책임이며, 본 가드는 *존재 여부* 만 본다.
 *   토큰 위조 방지·만료 검증은 백엔드 호출 시점에 발생한다.
 */

const PROTECTED_PREFIX = '/app';
const COOKIE_NAME = process.env.AUTH_COOKIE_NAME ?? 'jippin_session';

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  if (!pathname.startsWith(PROTECTED_PREFIX)) {
    return NextResponse.next();
  }

  const hasSession = request.cookies.has(COOKIE_NAME);
  if (hasSession) {
    return NextResponse.next();
  }

  const loginUrl = request.nextUrl.clone();
  loginUrl.pathname = '/login';
  loginUrl.searchParams.set('next', pathname + search);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ['/app/:path*']
};

import { NextResponse, type NextRequest } from 'next/server';

/**
 * 보호 경로 미인증 가드 (CMP-529, CMP-557, CMP-564).
 *
 * CMP-557 정책 (`/CMP/issues/CMP-557` plan 문서 §2):
 *   - 비회원 사전검토 진입 경로(`/app/pre-review/...`)는 로그인 없이 접근 가능해야 한다.
 *     세션 쿠키 부재만으로 차단하면 비회원 흐름이 즉시 끊긴다.
 *   - 상담 전환 · 리드 생성 · 리포트 저장 등 "전환 시점" 경로는 쿠키 기반으로 보호한다.
 *   - 본 가드는 쿠키 존재 여부만 확인한다. 실제 검증(서명, 만료)은 백엔드(`apps/api`) 책임이며,
 *     보호 경로 진입 후 백엔드 호출이 401 을 돌려주면 클라이언트가 로그인으로 유도한다.
 *
 * 인증 쿠키 이름은 백엔드 AUTH 모듈과 합의된 `jippin_session` 을 가정한다
 * (env `AUTH_COOKIE_NAME` 으로 override 가능).
 */

const AUTH_COOKIE_NAME = process.env.AUTH_COOKIE_NAME ?? 'jippin_session';

/**
 * 쿠키 없이도 접근 가능한 `/app/*` 하위 경로 (prefix 매칭).
 * - 비회원 사전검토 흐름은 여기서만 진입한다. 전환/저장 시점은 별도 보호 경로에서 받는다.
 */
const ANONYMOUS_ALLOWED_APP_PREFIXES = ['/app/pre-review'] as const;

/**
 * 쿠키가 반드시 필요한 `/app/*` 하위 경로 (prefix 매칭).
 * - 상담 전환, 리드 생성, 리포트 저장 등 전환/저장 시점 경로만 보호한다.
 * - 화이트리스트에 없는 새 `/app/*` 경로는 기본 비보호이므로, 보호가 필요한 경로를 추가할 때
 *   본 배열에 명시적으로 등록한다 (CMP-557 §2).
 */
const PROTECTED_APP_PREFIXES = [
  '/app/consult',
  '/app/leads',
  '/app/reports'
] as const;

function isAnonymousAllowed(pathname: string): boolean {
  return ANONYMOUS_ALLOWED_APP_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

function isProtected(pathname: string): boolean {
  if (!pathname.startsWith('/app')) {
    return false;
  }
  if (isAnonymousAllowed(pathname)) {
    return false;
  }
  return PROTECTED_APP_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  if (!isProtected(pathname)) {
    return NextResponse.next();
  }

  if (request.cookies.has(AUTH_COOKIE_NAME)) {
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

import { NextResponse, type NextRequest } from 'next/server';

import { updateSession } from '@/lib/supabase/proxy';

/**
 * 보호 경로 미인증 가드 (CMP-529, CMP-557, CMP-564, CMP-571, CMP-618).
 *
 * CMP-571: Next.js 16 의 `middleware` 파일 컨벤션이 deprecated 되어 본 파일은
 * `proxy.ts` 로 이동되고 export 함수명도 `proxy` 로 변경되었다. matcher 와
 * 가드 로직 자체는 유지된다.
 *
 * CMP-557 정책 (`/CMP/issues/CMP-557` plan 문서 §2):
 *   - 비회원 사전검토 진입 경로(`/app/pre-review/...`)는 로그인 없이 접근 가능해야 한다.
 *     세션 쿠키 부재만으로 차단하면 비회원 흐름이 즉시 끊긴다.
 *   - 상담 전환 · 리드 생성 · 리포트 저장 등 "전환 시점" 경로는 쿠키 기반으로 보호한다.
 *   - 본 가드는 쿠키 존재 여부만 확인한다. 실제 검증(서명, 만료)은 백엔드(`apps/api`) 책임이며,
 *     보호 경로 진입 후 백엔드 호출이 401 을 돌려주면 클라이언트가 로그인으로 유도한다.
 *
 * CMP-618: 모바일 IA 가 `/leads`, `/leads/new` 등 root-level conversion route 를
 * 도입함에 따라 보호 prefix 범위를 root 경로까지 확장한다. AGENTS.md §4.4 의
 * conversion-only 라우트 (상담 / 리드 / 리포트) 정책상 리드 생성 진입은 OAuth
 * 전환 시점이므로 미인증 사용자는 `/login?next=...` 로 유도해야 한다.
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

/**
 * root-level 보호 prefix (CMP-618 / CMP-DIRECT 디자인 트랙 정책 조정).
 * - `/contacts`, `/contacts/:contactId`: 이미 생성된 상담의 진행/개인 데이터 조회 영역 —
 *   per-user 데이터 노출 방지 차원에서 **로그인 필수**.
 * - `/leads`, `/leads/new`(상담 신청)는 **비로그인 허용**한다. 상담 신청은 비회원 전환
 *   유입의 핵심 진입점이므로 막지 않는다(미인증 차단 시 퍼널이 끊김). 실제 비회원 리드
 *   생성 허용은 백엔드(`apps/api`) 정책과도 일치해야 한다.
 * - prefix 매칭은 정확한 경로 일치 또는 `<prefix>/` 시작만 인정해 `/contacts-foo` 같은
 *   인접 경로 오매칭을 방지한다.
 */
const PROTECTED_ROOT_PREFIXES = ['/contacts', '/mypage'] as const;

function isAnonymousAllowed(pathname: string): boolean {
  return ANONYMOUS_ALLOWED_APP_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

function matchesRootPrefix(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

function isProtected(pathname: string): boolean {
  if (PROTECTED_ROOT_PREFIXES.some((prefix) => matchesRootPrefix(pathname, prefix))) {
    return true;
  }
  if (!pathname.startsWith('/app')) {
    return false;
  }
  if (isAnonymousAllowed(pathname)) {
    return false;
  }
  return PROTECTED_APP_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

export async function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  if (!isProtected(pathname)) {
    return NextResponse.next();
  }

  if (request.cookies.has(AUTH_COOKIE_NAME)) {
    try {
      const { response } = await updateSession(request);
      return response;
    } catch {
      return NextResponse.next();
    }
  }

  const loginUrl = request.nextUrl.clone();
  loginUrl.pathname = '/login';
  loginUrl.search = '';
  loginUrl.searchParams.set('next', pathname + search);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: [
    '/app/:path*',
    '/auth/:path*',
    '/login',
    '/contacts/:path*',
    '/mypage/:path*'
  ]
};

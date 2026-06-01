import { NextResponse, type NextRequest } from 'next/server';
import { createServerClient } from '@supabase/ssr';

import { supabaseAnonKey, supabaseUrl } from '@/lib/supabase/env';

/**
 * 보호 경로 미인증 가드 (CMP-529, CMP-557, CMP-564, CMP-571).
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
 * Phase 1 Supabase 전환 후 보호 경로는 `jippin_session` legacy cookie 가 아니라
 * Supabase SSR auth cookie 를 정본으로 삼는다.
 */

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

function isAnonymousSupabaseUser(user: { is_anonymous?: boolean; app_metadata?: unknown } | null): boolean {
  if (!user) return false;
  if (user.is_anonymous === true) return true;
  const metadata = user.app_metadata;
  return (
    typeof metadata === 'object' &&
    metadata !== null &&
    'provider' in metadata &&
    metadata.provider === 'anonymous'
  );
}

export async function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  if (!isProtected(pathname)) {
    return NextResponse.next();
  }

  const response = NextResponse.next();
  const supabase = createServerClient(supabaseUrl(), supabaseAnonKey(), {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        for (const { name, value } of cookiesToSet) {
          request.cookies.set(name, value);
        }
        for (const { name, value, options } of cookiesToSet) {
          response.cookies.set(name, value, options);
        }
      },
    },
  });
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (user && !isAnonymousSupabaseUser(user)) {
    return response;
  }

  const loginUrl = request.nextUrl.clone();
  loginUrl.pathname = '/login';
  loginUrl.searchParams.set('next', pathname + search);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ['/app/:path*']
};

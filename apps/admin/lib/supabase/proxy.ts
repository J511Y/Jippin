/**
 * Proxy(미들웨어)용 세션 갱신 어댑터 (CMP-DIRECT).
 *
 * Supabase SSR 공식 미들웨어 패턴: 요청 쿠키로 세션을 복원하고, 토큰이 갱신되면
 * request/response 양쪽 쿠키에 반영한 뒤 사용자 객체를 돌려준다.
 *
 * **Invariant:** 호출자가 redirect 등 새 응답을 만들 때는 반드시
 * `supabaseResponse.cookies.getAll()` 을 새 응답에 복사해야 갱신된 세션 쿠키가
 * 유실되지 않는다.
 */

import { createServerClient, type CookieMethodsServer } from '@supabase/ssr';
import type { User } from '@supabase/supabase-js';
import { NextResponse, type NextRequest } from 'next/server';

import { supabaseAnonKey, supabaseUrl } from './env';

export interface UpdateSessionResult {
  supabaseResponse: NextResponse;
  user: User | null;
}

export async function updateSession(request: NextRequest): Promise<UpdateSessionResult> {
  let supabaseResponse = NextResponse.next({ request });

  const cookieMethods: CookieMethodsServer = {
    getAll() {
      return request.cookies.getAll().map(({ name, value }) => ({ name, value }));
    },
    setAll(cookiesToSet) {
      for (const { name, value } of cookiesToSet) {
        request.cookies.set(name, value);
      }
      supabaseResponse = NextResponse.next({ request });
      for (const { name, value, options } of cookiesToSet) {
        supabaseResponse.cookies.set({ name, value, ...options });
      }
    }
  };

  const supabase = createServerClient(supabaseUrl(), supabaseAnonKey(), {
    cookies: cookieMethods
  });

  // getUser() 는 Supabase Auth 서버에 토큰을 검증한다 — 쿠키 위조를 신뢰하지 않는다.
  const {
    data: { user }
  } = await supabase.auth.getUser();

  return { supabaseResponse, user };
}

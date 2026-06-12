/**
 * SSR Supabase client factory — apps/web `lib/supabase/server.ts` 의 축약판 (CMP-DIRECT).
 *
 * `@supabase/ssr` v0.5+ 표준 `getAll` / `setAll` 패턴만 사용한다.
 *
 *   (1) Route Handler — 단일 NextResponse accumulator 패턴:
 *       const response = new NextResponse(null);
 *       const supabase = createRouteHandlerClient({ request, response });
 *       // supabase.auth.* 호출이 setAll 을 거쳐 response 에 Set-Cookie 누적.
 *
 *   (2) Server Component / Action:
 *       const supabase = await createServerComponentClient();
 */

import { createServerClient, type CookieMethodsServer } from '@supabase/ssr';
import type { SupabaseClient } from '@supabase/supabase-js';
import { cookies } from 'next/headers';
import type { NextRequest, NextResponse } from 'next/server';

import { supabaseAnonKey, supabaseUrl } from './env';

interface RouteHandlerClientArgs {
  request: NextRequest;
  response: NextResponse;
}

export function createRouteHandlerClient({
  request,
  response
}: RouteHandlerClientArgs): SupabaseClient {
  const cookieMethods: CookieMethodsServer = {
    getAll() {
      return request.cookies.getAll().map(({ name, value }) => ({ name, value }));
    },
    setAll(cookiesToSet) {
      for (const { name, value, options } of cookiesToSet) {
        response.cookies.set({ name, value, ...options });
      }
    }
  };

  return createServerClient(supabaseUrl(), supabaseAnonKey(), { cookies: cookieMethods });
}

export async function createServerComponentClient(): Promise<SupabaseClient> {
  const cookieStore = await cookies();
  const cookieMethods: CookieMethodsServer = {
    getAll() {
      return cookieStore.getAll().map(({ name, value }) => ({ name, value }));
    },
    setAll(cookiesToSet) {
      try {
        for (const { name, value, options } of cookiesToSet) {
          cookieStore.set(name, value, options);
        }
      } catch {
        // Server Component 는 응답 쿠키를 변경할 수 없다 — proxy 가 세션을 갱신한다.
      }
    }
  };

  return createServerClient(supabaseUrl(), supabaseAnonKey(), { cookies: cookieMethods });
}

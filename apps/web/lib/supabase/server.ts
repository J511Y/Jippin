/**
 * SSR Supabase client factory — Route Handler / Server Component 용 (runbook §2.2 / §4.2.1).
 *
 * `@supabase/ssr` v0.5+ 표준 `getAll` / `setAll` 패턴 (review item R10).
 * deprecated `get` / `set` / `remove` 개별 콜백은 사용 금지 — cookie 누락 / 동시 set race 우려.
 *
 * 호출자는 두 가지 형태 중 하나로 쓴다:
 *
 *   (1) Route Handler — 단일 NextResponse accumulator 패턴 (runbook §4.2.1):
 *
 *       const response = new NextResponse(null);
 *       const supabase = createRouteHandlerClient({ request, response });
 *       // ... supabase.auth.* 호출이 SDK 의 setAll 을 거쳐 response 에 Set-Cookie 누적.
 *       return new NextResponse(null, { status: 302, headers: response.headers });
 *
 *   (2) Server Component / Action — Next.js `cookies()` 핸들과 통합:
 *
 *       const supabase = await createServerComponentClient();
 *       const { data: { user } } = await supabase.auth.getUser();
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

/**
 * Route Handler 용 Supabase client.
 *
 * **Invariant:** `response` 하나가 모든 Set-Cookie 의 owner. 호출자는 마지막 단계에서
 * `response.headers` 를 그대로 사용해 응답을 만들어야 PKCE verifier cookie (`sb-<ref>-auth-token-code-verifier`)
 * 가 단일 redirect 응답으로 브라우저까지 전달된다 (runbook §4.2.1 review item R2).
 *
 * 새 `NextResponse.redirect()` 를 또 만들어 반환하면 verifier 가 손실되어
 * callback 이 `auth/missing-code-verifier` 로 실패한다.
 */
export function createRouteHandlerClient({ request, response }: RouteHandlerClientArgs): SupabaseClient {
  const cookies: CookieMethodsServer = {
    // getAll: request 에 도착한 모든 cookie 를 그대로 반환.
    getAll() {
      return request.cookies.getAll().map(({ name, value }) => ({ name, value }));
    },
    // setAll: SDK 가 한 번에 발급한 cookie 배치를 단일 response 객체에 일괄 부착.
    // PKCE verifier · refresh token · access token 이 같은 호출에서 함께 도착하므로
    // 본 콜백이 호출되는 시점에 response 가 모든 cookie 의 owner 가 된다.
    setAll(cookiesToSet) {
      for (const { name, value, options } of cookiesToSet) {
        response.cookies.set({ name, value, ...options });
      }
    },
  };

  return createServerClient(supabaseUrl(), supabaseAnonKey(), { cookies });
}

/**
 * Server Component / Server Action 용 Supabase client.
 *
 * Next.js `cookies()` 핸들은 Server Component 에서는 쓰기 시 예외를 던질 수 있다.
 * 이 어댑터는 read-only 구현으로 낮추지 않고 `setAll()` 을 항상 제공하되, 쓰기 불가
 * 컨텍스트에서만 예외를 삼킨다. Route Handler / Server Action 처럼 쓰기 가능한
 * 컨텍스트에서는 `cookieStore.set()` 으로 PKCE/session cookie batch 를 반영한다.
 */
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
        // Server Components cannot mutate response cookies; proxy / route handlers refresh them.
      }
    },
  };

  return createServerClient(supabaseUrl(), supabaseAnonKey(), { cookies: cookieMethods });
}

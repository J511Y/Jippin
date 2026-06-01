/**
 * Edge proxy (`apps/web/proxy.ts`) 용 Supabase client factory (runbook §2.2 / §4.8 / CMP-580).
 *
 * Next.js 16 의 `proxy` 시그니처 (`(request: NextRequest) => Response | Promise<Response>`)
 * 에 맞춘 어댑터. Route Handler 어댑터와 동일한 `getAll` / `setAll` 패턴 (R10) 을 사용해
 * 일관성을 유지한다 — runbook §4.2.1 의 "lib/supabase/server.ts / proxy.ts / browser.ts 의
 * 모든 createServerClient 호출에 일관 적용" 봉인.
 *
 * 호출자 (proxy.ts) 패턴:
 *
 *     const response = NextResponse.next();
 *     const supabase = createProxyClient({ request, response });
 *     const { data: { user } } = await supabase.auth.getUser();
 *     // ... 보호 라우트 가드 분기.
 *     return response;   // ← token rotation cookies 가 함께 전달되어야 하므로 같은 객체 반환.
 *
 * 본 PR (CMP-580) 은 어댑터만 봉인하며 proxy.ts 자체의 Supabase 통합은 후속 트랙
 * (§4.8 / CMP-577 Phase 1+) 에서 수행한다 — 호출 측 변경 없이 어댑터 shape 만 검증 가능.
 */

import { createServerClient, type CookieMethodsServer } from '@supabase/ssr';
import type { SupabaseClient } from '@supabase/supabase-js';
import type { NextRequest, NextResponse } from 'next/server';

import { supabaseAnonKey, supabaseUrl } from './env';

interface ProxyClientArgs {
  request: NextRequest;
  response: NextResponse;
}

export function createProxyClient({ request, response }: ProxyClientArgs): SupabaseClient {
  const cookies: CookieMethodsServer = {
    getAll() {
      return request.cookies.getAll().map(({ name, value }) => ({ name, value }));
    },
    setAll(cookiesToSet) {
      for (const { name, value, options } of cookiesToSet) {
        // request.cookies 에도 미러링하면 같은 proxy invocation 안에서 후속 supabase.auth.*
        // 호출이 갱신된 토큰을 즉시 읽을 수 있다. (@supabase/ssr 권장 패턴.)
        request.cookies.set({ name, value, ...options });
        response.cookies.set({ name, value, ...options });
      }
    },
  };

  return createServerClient(supabaseUrl(), supabaseAnonKey(), { cookies });
}

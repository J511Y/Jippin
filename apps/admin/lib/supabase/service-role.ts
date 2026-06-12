/**
 * service_role Supabase client — 서버 전용 (CMP-DIRECT).
 *
 * RLS 를 우회하는 키이므로 클라이언트 번들에 절대 노출되면 안 된다. `server-only`
 * import 가 클라이언트 컴포넌트에서의 import 를 빌드 타임에 차단한다.
 *
 * 호출자 책임: 이 클라이언트를 쓰는 모든 Route Handler / Server Action 은 먼저
 * `requireAdminUser()`(lib/auth.ts) 게이트를 통과해야 한다. proxy 게이트만 믿지 말 것.
 */

import 'server-only';

import { createClient, type SupabaseClient } from '@supabase/supabase-js';

import { supabaseUrl } from './env';

export function createServiceRoleClient(): SupabaseClient {
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!key) {
    throw new Error(
      '[supabase/service-role] missing required env var: SUPABASE_SERVICE_ROLE_KEY. ' +
        'Server-only secret — never expose with NEXT_PUBLIC_ prefix.'
    );
  }
  return createClient(supabaseUrl(), key, {
    auth: { persistSession: false, autoRefreshToken: false }
  });
}

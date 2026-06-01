import { createServerClient as createSupabaseServerClient } from '@supabase/ssr';
import type { SupabaseClient } from '@supabase/supabase-js';
import type { NextRequest, NextResponse } from 'next/server';

import { supabaseAnonKey, supabaseUrl } from './env';

type RouteHandlerClientArgs = {
  request: NextRequest;
  response: NextResponse;
};

export function createRouteHandlerClient({
  request,
  response,
}: RouteHandlerClientArgs): SupabaseClient {
  // TODO(CMP-580): keep this aligned with the formal SSR cookie adapter.
  return createSupabaseServerClient(supabaseUrl(), supabaseAnonKey(), {
    cookies: {
      getAll() {
        return request.cookies.getAll().map(({ name, value }) => ({ name, value }));
      },
      setAll(cookiesToSet) {
        for (const { name, value, options } of cookiesToSet) {
          response.cookies.set({ name, value, ...options });
        }
      },
    },
  });
}

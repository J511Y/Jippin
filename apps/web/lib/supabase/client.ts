import { createBrowserClient } from '@supabase/ssr';
import type { SupabaseClient } from '@supabase/supabase-js';

let browserClient: SupabaseClient | null = null;

function browserSupabaseUrl(): string {
  const value = process.env.NEXT_PUBLIC_SUPABASE_URL;
  if (!value) {
    throw new Error('[supabase/client] missing required env var: NEXT_PUBLIC_SUPABASE_URL');
  }
  return value;
}

function browserSupabaseAnonKey(): string {
  const value = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!value) {
    throw new Error('[supabase/client] missing required env var: NEXT_PUBLIC_SUPABASE_ANON_KEY');
  }
  return value;
}

export function createClient(): SupabaseClient {
  if (!browserClient) {
    browserClient = createBrowserClient(browserSupabaseUrl(), browserSupabaseAnonKey());
  }

  return browserClient;
}

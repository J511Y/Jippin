'use client';

import { createBrowserClient } from '@supabase/ssr';
import type { SupabaseClient } from '@supabase/supabase-js';

import { supabaseAnonKey, supabaseUrl } from './env';

let client: SupabaseClient | null = null;

export function createBrowserSupabaseClient(): SupabaseClient {
  client ??= createBrowserClient(supabaseUrl(), supabaseAnonKey());
  return client;
}

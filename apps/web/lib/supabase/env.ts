/**
 * Supabase env readers (runbook §2.2 / §3 / CMP-580).
 *
 * 단일 SSOT: `lib/supabase/*` 만이 `@supabase/ssr` / `@supabase/supabase-js` 를 import 한다.
 * 환경변수 미설정 시 fail loud — fallback 금지 (runbook §3 마지막 노트).
 */

type RequiredEnvKey = 'NEXT_PUBLIC_SUPABASE_URL' | 'NEXT_PUBLIC_SUPABASE_ANON_KEY';

function readRequiredEnv(key: RequiredEnvKey): string {
  const value = process.env[key];
  if (!value) {
    throw new Error(
      `[supabase/env] missing required env var: ${key}. ` +
        `Set it in apps/web/.env.local for local dev, or in the runtime secret manager for preview/prod (runbook §3).`,
    );
  }
  return value;
}

export const supabaseUrl = (): string => readRequiredEnv('NEXT_PUBLIC_SUPABASE_URL');
export const supabaseAnonKey = (): string => readRequiredEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY');

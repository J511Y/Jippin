const NEXT_PUBLIC_SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const NEXT_PUBLIC_SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

function readRequiredPublicEnv(name: string, value: string | undefined): string {
  if (!value) {
    throw new Error(`${name} is required for Supabase auth.`);
  }
  return value;
}

export function supabaseUrl(): string {
  return readRequiredPublicEnv('NEXT_PUBLIC_SUPABASE_URL', NEXT_PUBLIC_SUPABASE_URL);
}

export function supabaseAnonKey(): string {
  return readRequiredPublicEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY', NEXT_PUBLIC_SUPABASE_ANON_KEY);
}

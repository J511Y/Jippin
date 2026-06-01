function readRequiredPublicEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} is required for Supabase auth.`);
  }
  return value;
}

export function supabaseUrl(): string {
  return readRequiredPublicEnv('NEXT_PUBLIC_SUPABASE_URL');
}

export function supabaseAnonKey(): string {
  return readRequiredPublicEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY');
}

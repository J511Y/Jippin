// SSOT for next / OAuth handoff URL validation (CMP-577 runbook §4.6 / §4.7.2).
//
// Two guards live here so every hop (login → start BFF → /auth/redirect → callback → callback-done)
// can reach for the same validator and reject open-redirect payloads identically.
//   - isSafeNext: relative path destinations (the `?next=` param threaded through the OAuth chain).
//   - isSafeOAuthHandoff: the `?to=` URL handed to /auth/redirect right before navigating to the
//     Supabase OAuth start URL. Bound by exact origin match against NEXT_PUBLIC_SUPABASE_URL.

export const DEFAULT_NEXT = '/';

function hasUnsafeChar(value: string): boolean {
  for (let i = 0; i < value.length; i += 1) {
    const code = value.charCodeAt(i);
    // ASCII control chars (NUL..US + DEL) + space — open to response-splitting / spoofing.
    if (code <= 32 || code === 127) return true;
  }
  return false;
}

export function isSafeNext(value: unknown): value is string {
  if (typeof value !== 'string' || value.length === 0) return false;
  if (!value.startsWith('/')) return false;
  // schema-relative (//host) and backslash variants — open redirect vectors.
  if (value.startsWith('//') || value.startsWith('/\\') || value.startsWith('\\')) return false;
  if (hasUnsafeChar(value)) return false;
  return true;
}

export function resolveSafeNext(value: unknown, fallback: string = DEFAULT_NEXT): string {
  return isSafeNext(value) ? value : fallback;
}

// Validates the `?to=<oauth_url>` handed to /auth/redirect. The URL must be an absolute URL
// whose origin matches the configured Supabase project (scheme + host + port) exactly.
// Any other origin — including schema-relative tricks, javascript:/data: schemes, or a sibling
// host — must be rejected before window.location.assign fires.
export function isSafeOAuthHandoff(value: unknown, supabaseUrl: string | undefined): value is string {
  if (typeof value !== 'string' || value.length === 0) return false;
  if (!supabaseUrl) return false;

  let target: URL;
  let allowed: URL;
  try {
    target = new URL(value);
    allowed = new URL(supabaseUrl);
  } catch {
    return false;
  }

  if (target.protocol !== allowed.protocol) return false;
  if (target.protocol !== 'https:' && target.protocol !== 'http:') return false;
  if (target.origin !== allowed.origin) return false;
  return true;
}

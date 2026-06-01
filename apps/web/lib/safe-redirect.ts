// SSOT for OAuth next / redirect target validation (CMP-582 / CMP-586).
//
// Every hop in the OAuth chain re-validates the value it receives:
//   - `next` is an in-app relative path only.
//   - `/auth/redirect?to=` is an absolute OAuth URL whose origin is explicitly allowed.

export const DEFAULT_SAFE_NEXT = '/';
export const DEFAULT_NEXT = DEFAULT_SAFE_NEXT;

function hasUnsafeChar(value: string): boolean {
  for (let i = 0; i < value.length; i += 1) {
    const code = value.charCodeAt(i);
    // ASCII controls + space: block response splitting and browser URL spoofing edge cases.
    if (code <= 32 || code === 127) return true;
  }
  return false;
}

function isHttpProtocol(protocol: string): boolean {
  return protocol === 'https:' || protocol === 'http:';
}

function parseOrigin(value: string | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return isHttpProtocol(url.protocol) ? url.origin : null;
  } catch {
    return null;
  }
}

export function isSafeNext(value: unknown): value is string {
  if (typeof value !== 'string' || value.length === 0) return false;
  if (!value.startsWith('/')) return false;
  // Schema-relative and backslash variants can be interpreted as host redirects.
  if (value.startsWith('//') || value.startsWith('/\\') || value.startsWith('\\')) {
    return false;
  }
  if (hasUnsafeChar(value)) return false;
  return true;
}

export function resolveSafeNext(
  value: unknown,
  fallback: string = DEFAULT_SAFE_NEXT,
): string {
  return isSafeNext(value) ? value : fallback;
}

export function safeSameOriginPath(
  value: string | null | undefined,
  requestOrigin: string,
  fallback: string = DEFAULT_SAFE_NEXT,
): string {
  if (!value) return fallback;
  if (isSafeNext(value)) return value;

  try {
    const url = new URL(value);
    if (url.origin !== requestOrigin) return fallback;
    return resolveSafeNext(`${url.pathname}${url.search}${url.hash}`, fallback);
  } catch {
    return fallback;
  }
}

export function isAllowedRedirectTarget(
  value: unknown,
  allowedOrigins: readonly (string | undefined)[],
): value is string {
  if (typeof value !== 'string' || value.length === 0) return false;

  let target: URL;
  try {
    target = new URL(value);
  } catch {
    return false;
  }

  if (!isHttpProtocol(target.protocol)) return false;
  const allowed = new Set(
    allowedOrigins
      .map((origin) => parseOrigin(origin))
      .filter((origin): origin is string => origin !== null),
  );
  return allowed.has(target.origin);
}

export function isSafeOAuthHandoff(
  value: unknown,
  supabaseUrl: string | undefined,
  appOrigin?: string,
): value is string {
  return isAllowedRedirectTarget(value, [appOrigin, supabaseUrl]);
}

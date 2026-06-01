import { isSupabaseProvider, type SupabaseProvider } from './providers';

export const FLOW_CONTEXT_MAX_AGE_MS = 5 * 60 * 1000;
const MAX_CLOCK_SKEW_MS = 60 * 1000;

export type OAuthFlowContext = {
  provider: SupabaseProvider;
  createdAt: number;
};

function decodeCookieValue(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

export function encodeOAuthFlowContext(
  provider: SupabaseProvider,
  createdAt: number = Date.now(),
): string {
  return `${provider}|${createdAt}`;
}

export function parseOAuthFlowContext(value: string | null): OAuthFlowContext | null {
  if (!value) return null;
  const [provider, createdAtRaw] = decodeCookieValue(value).split('|');
  const createdAt = Number(createdAtRaw);
  if (!isSupabaseProvider(provider) || !Number.isFinite(createdAt)) {
    return null;
  }
  return { provider, createdAt };
}

export function isOAuthFlowContextStale(
  value: string | null,
  now: number = Date.now(),
): boolean {
  if (!value) return false;
  const context = parseOAuthFlowContext(value);
  if (!context) return true;
  if (context.createdAt > now + MAX_CLOCK_SKEW_MS) return true;
  return now - context.createdAt > FLOW_CONTEXT_MAX_AGE_MS;
}

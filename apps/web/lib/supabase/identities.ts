import type { User, UserIdentity } from '@supabase/supabase-js';

import { isSupabaseProvider, type SupabaseProvider } from './providers';
import { parseOAuthFlowContext } from './flow-context';

const NEW_IDENTITY_WINDOW_MS = 10 * 60 * 1000;
const CLOCK_SKEW_MS = 60 * 1000;

function parseIntendedProvider(value: string | null): SupabaseProvider | null {
  const context = parseOAuthFlowContext(value);
  if (context) return context.provider;
  const candidate = value?.split('|', 1)[0] ?? null;
  return isSupabaseProvider(candidate) ? candidate : null;
}

function parseIdentityCreatedAt(identity: UserIdentity): number {
  const raw = identity.created_at ?? null;
  return raw ? Date.parse(raw) || 0 : 0;
}

function identityTimestamp(identity: UserIdentity): number {
  const raw = identity.last_sign_in_at ?? identity.updated_at ?? identity.created_at ?? null;
  return raw ? Date.parse(raw) || 0 : 0;
}

function isProviderIdentity(
  identity: UserIdentity,
  provider: SupabaseProvider | null | undefined,
): boolean {
  return Boolean(provider) && identity.provider === provider;
}

function pickLastLinkedIdentity(identities: readonly UserIdentity[]): UserIdentity | null {
  let latest: UserIdentity | null = null;
  for (const identity of identities) {
    if (!latest || identityTimestamp(identity) >= identityTimestamp(latest)) {
      latest = identity;
    }
  }
  return latest;
}

export function detectNewlyLinkedProvider(
  user: User,
  intendedProviderCookie: string | null,
  flowCreatedAt?: number | null,
): SupabaseProvider | null {
  const intended = parseIntendedProvider(intendedProviderCookie);
  if (intended && hasNewlyLinkedIdentity(user, intended, flowCreatedAt)) {
    return intended;
  }

  const identities = user.identities ?? [];
  const observedRaw = pickLastLinkedIdentity(identities)?.provider ?? null;
  const observed = isSupabaseProvider(observedRaw) ? observedRaw : null;
  return hasNewlyLinkedIdentity(user, observed, flowCreatedAt) ? observed : null;
}

export function hasNewlyLinkedIdentity(
  user: User,
  provider: SupabaseProvider | null,
  flowCreatedAt: number | null | undefined,
): boolean {
  if (!provider) return false;
  const referenceTime = Number.isFinite(flowCreatedAt) ? Number(flowCreatedAt) : Date.now();
  const earliestAllowed = referenceTime - NEW_IDENTITY_WINDOW_MS - CLOCK_SKEW_MS;
  const latestAllowed = Date.now() + CLOCK_SKEW_MS;

  return (user.identities ?? []).some((identity) => {
    if (!isProviderIdentity(identity, provider)) return false;
    const createdAt = parseIdentityCreatedAt(identity);
    return createdAt >= earliestAllowed && createdAt <= latestAllowed;
  });
}

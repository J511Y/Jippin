import type { User, UserIdentity } from '@supabase/supabase-js';

import { isSupabaseProvider, type SupabaseProvider } from './providers';
import { parseOAuthFlowContext } from './flow-context';

function parseIntendedProvider(value: string | null): SupabaseProvider | null {
  const context = parseOAuthFlowContext(value);
  if (context) return context.provider;
  const candidate = value?.split('|', 1)[0] ?? null;
  return isSupabaseProvider(candidate) ? candidate : null;
}

function identityTimestamp(identity: UserIdentity): number {
  const raw =
    identity.last_sign_in_at ??
    identity.updated_at ??
    identity.created_at ??
    null;
  return raw ? Date.parse(raw) || 0 : 0;
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
): SupabaseProvider | null {
  const intended = parseIntendedProvider(intendedProviderCookie);
  const observedRaw = pickLastLinkedIdentity(user.identities ?? [])?.provider ?? null;
  const observed = isSupabaseProvider(observedRaw) ? observedRaw : null;

  if (intended && observed && intended !== observed) return null;
  return intended ?? observed;
}

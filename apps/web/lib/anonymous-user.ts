/**
 * Legacy anonymous user ID helper.
 *
 * CMP-604 removed the public `anonymous_users` table and
 * `localStorage.jippin_anonymous_user_id` issuance path. Supabase Anonymous
 * Sign-In is the identity SSOT. The read helper remains only for one-way
 * cleanup/backfill code that needs to inspect stale browser storage.
 */

export const ANONYMOUS_USER_ID_STORAGE_KEY = 'jippin_anonymous_user_id';

function assertBrowser(): void {
  if (typeof window === 'undefined') {
    throw new Error('anonymous-user helper must be called in the browser.');
  }
}

export function readStoredAnonymousUserId(): string | null {
  assertBrowser();
  try {
    return window.localStorage.getItem(ANONYMOUS_USER_ID_STORAGE_KEY);
  } catch {
    return null;
  }
}

export async function getOrCreateAnonymousUserId(): Promise<string> {
  assertBrowser();
  throw new Error(
    'legacy anonymous-user issuance was removed; use Supabase anonymous sign-in.'
  );
}

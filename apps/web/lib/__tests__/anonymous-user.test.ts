/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ANONYMOUS_USER_ID_STORAGE_KEY,
  getOrCreateAnonymousUserId,
  readStoredAnonymousUserId,
} from '@/lib/anonymous-user';

describe('legacy anonymous-user helper', () => {
  const fetchSpy = vi.fn();

  beforeEach(() => {
    window.localStorage.clear();
    fetchSpy.mockReset();
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('can read stale localStorage for cleanup/backfill code', () => {
    window.localStorage.setItem(
      ANONYMOUS_USER_ID_STORAGE_KEY,
      '33333333-3333-3333-3333-333333333333'
    );

    expect(readStoredAnonymousUserId()).toBe(
      '33333333-3333-3333-3333-333333333333'
    );
  });

  it('does not issue legacy anonymous users or call the BFF', async () => {
    await expect(getOrCreateAnonymousUserId()).rejects.toThrow(
      /legacy anonymous-user issuance was removed/
    );
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

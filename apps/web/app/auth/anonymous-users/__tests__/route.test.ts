import { describe, expect, it } from 'vitest';

import { POST } from '../route';

describe('POST /auth/anonymous-users — removed legacy BFF', () => {
  it('returns 410 instead of proxying legacy anonymous issuance', async () => {
    const res = await POST();

    expect(res.status).toBe(410);
    expect(await res.json()).toEqual({
      error: {
        code: 'AUTH_LEGACY_FLOW_REMOVED',
        message:
          'Legacy anonymous user issuance was removed; use Supabase anonymous sign-in.',
      },
    });
  });
});

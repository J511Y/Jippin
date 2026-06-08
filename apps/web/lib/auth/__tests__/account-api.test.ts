import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api-base-url', () => ({
  apiBaseUrl: () => 'http://api.test'
}));

vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } })
    }
  })
}));

import {
  AccountApiError,
  deleteAccount,
  sendPhoneCode,
  verifyPhoneCode
} from '../account-api';

afterEach(() => {
  vi.restoreAllMocks();
});

function mockFetch(status: number, body: unknown) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' }
    })
  );
}

describe('account-api', () => {
  it('sends phone code to the API base URL', async () => {
    const fetchSpy = mockFetch(200, { expires_in_seconds: 180 });
    const res = await sendPhoneCode('010-1234-5678');
    expect(res.expires_in_seconds).toBe(180);
    const [url, init] = fetchSpy.mock.calls[0]!;
    expect(url).toBe('http://api.test/auth/phone/send-code');
    expect(init?.method).toBe('POST');
  });

  it('throws AccountApiError carrying the backend error code', async () => {
    mockFetch(400, { error: { code: 'PHONE_OTP_MISMATCH', message: '인증번호가 일치하지 않습니다.' } });
    await expect(verifyPhoneCode('010-1234-5678', '000000')).rejects.toMatchObject({
      name: 'AccountApiError',
      code: 'PHONE_OTP_MISMATCH'
    });
  });

  it('requires a session for authed calls (deleteAccount)', async () => {
    await expect(deleteAccount()).rejects.toBeInstanceOf(AccountApiError);
  });
});

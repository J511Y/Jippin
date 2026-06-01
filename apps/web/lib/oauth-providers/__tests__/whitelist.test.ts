import { describe, expect, it } from 'vitest';

import {
  ALLOWED_PROVIDERS,
  assertAllowedProvider,
  isAllowedProvider
} from '../index';

describe('ALLOWED_PROVIDERS SSOT', () => {
  it('is the exact tuple google/kakao/naver (no email/passwordless/etc)', () => {
    expect([...ALLOWED_PROVIDERS]).toEqual(['google', 'kakao', 'naver']);
  });

  it.each(['google', 'kakao', 'naver'])('accepts allowed provider %s', (id) => {
    expect(isAllowedProvider(id)).toBe(true);
    expect(assertAllowedProvider(id)).toBe(id);
  });

  it.each([
    'facebook',
    'apple',
    'github',
    'email',
    'magic_link',
    'magiclink',
    'otp',
    'sms',
    'password',
    '',
    'GOOGLE',
    null,
    undefined,
    {},
    42
  ])('rejects non-whitelisted value %p', (value) => {
    expect(isAllowedProvider(value)).toBe(false);
    expect(() => assertAllowedProvider(value)).toThrow(/provider_not_allowed/);
  });
});

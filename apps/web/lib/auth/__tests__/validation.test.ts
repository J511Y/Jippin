import { describe, expect, it } from 'vitest';

import {
  changePasswordSchema,
  koreanMobileSchema,
  passwordSchema,
  signupSchema
} from '../validation';

const validSignup = {
  name: '홍길동',
  email: 'hong@example.com',
  phone: '010-1234-5678',
  phoneToken: 'tok',
  password: 'abc123',
  confirm: 'abc123',
  agreed: true
};

describe('auth zod schemas', () => {
  it('passwordSchema rejects weak and accepts policy-compliant', () => {
    expect(passwordSchema.safeParse('abcde').success).toBe(false); // 6자 미만
    expect(passwordSchema.safeParse('abcdef').success).toBe(false); // 숫자 없음
    expect(passwordSchema.safeParse('123456').success).toBe(false); // 영문 없음
    expect(passwordSchema.safeParse('abc123').success).toBe(true);
  });

  it('koreanMobileSchema accepts mobile, rejects landline/garbage', () => {
    expect(koreanMobileSchema.safeParse('01012345678').success).toBe(true);
    expect(koreanMobileSchema.safeParse('010-1234-5678').success).toBe(true);
    expect(koreanMobileSchema.safeParse('021234567').success).toBe(false); // 지역번호(문자 불가)
    expect(koreanMobileSchema.safeParse('abc').success).toBe(false);
  });

  it('signupSchema accepts a valid payload', () => {
    expect(signupSchema.safeParse(validSignup).success).toBe(true);
  });

  it('signupSchema requires terms agreement', () => {
    const res = signupSchema.safeParse({ ...validSignup, agreed: false });
    expect(res.success).toBe(false);
    if (!res.success) {
      expect(res.error.issues.some((i) => i.path[0] === 'agreed')).toBe(true);
    }
  });

  it('signupSchema requires a phone verification token', () => {
    const res = signupSchema.safeParse({ ...validSignup, phoneToken: '' });
    expect(res.success).toBe(false);
  });

  it('signupSchema flags mismatched password confirmation on confirm path', () => {
    const res = signupSchema.safeParse({ ...validSignup, confirm: 'different1' });
    expect(res.success).toBe(false);
    if (!res.success) {
      expect(res.error.issues.some((i) => i.path[0] === 'confirm')).toBe(true);
    }
  });

  it('changePasswordSchema enforces new-password policy and match', () => {
    expect(
      changePasswordSchema.safeParse({
        current: 'old1',
        password: 'new123',
        confirm: 'new123'
      }).success
    ).toBe(true);
    expect(
      changePasswordSchema.safeParse({
        current: 'old1',
        password: 'new123',
        confirm: 'nope123'
      }).success
    ).toBe(false);
  });
});

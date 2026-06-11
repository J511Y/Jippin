import { zodResolver } from '@hookform/resolvers/zod';
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
  agreed: true,
  over14: true,
  marketing: false
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

  it('signupSchema requires the age-over-14 attestation (만 14세 이상)', () => {
    const res = signupSchema.safeParse({ ...validSignup, over14: false });
    expect(res.success).toBe(false);
    if (!res.success) {
      expect(res.error.issues.some((i) => i.path[0] === 'over14')).toBe(true);
    }
  });

  it('signupSchema accepts both marketing consent choices (선택 동의)', () => {
    expect(signupSchema.safeParse({ ...validSignup, marketing: true }).success).toBe(true);
    expect(signupSchema.safeParse({ ...validSignup, marketing: false }).success).toBe(true);
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

  it('zodResolver(@hookform/resolvers v5) maps zod 4 errors to RHF field errors', async () => {
    // 리뷰어 우려 검증: resolver 가 zod 4 ZodError 를 RHF field error 로 변환하는지.
    const resolver = zodResolver(signupSchema);
    const result = await resolver(
      { ...validSignup, password: 'weak', confirm: 'nope', agreed: false },
      undefined,
      { fields: {}, shouldUseNativeValidation: false }
    );
    expect(Object.keys(result.values)).toHaveLength(0);
    expect(result.errors.password?.message).toContain('비밀번호');
    expect(result.errors.agreed).toBeDefined();
    expect(result.errors.confirm).toBeDefined();
  });

  it('zodResolver returns parsed values when input is valid', async () => {
    const resolver = zodResolver(signupSchema);
    const result = await resolver(validSignup, undefined, {
      fields: {},
      shouldUseNativeValidation: false
    });
    expect(result.errors).toEqual({});
    expect((result.values as { email: string }).email).toBe('hong@example.com');
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

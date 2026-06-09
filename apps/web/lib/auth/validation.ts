/**
 * 인증 폼 zod 스키마 (CMP-DIRECT).
 *
 * react-hook-form + @hookform/resolvers/zod 로 폼 단위 검증을 표준화한다. 백엔드
 * (`apps/api/src/schemas/account.py`)의 규칙과 동일하게 유지한다 — 서버가 최종 권위.
 * 휴대폰 정규화는 `lib/leads/validation` SSOT 를 재사용한다.
 */

import { z } from 'zod';

import { normalizeKoreanPhone } from '@/lib/leads/validation';

export const MIN_PASSWORD_LENGTH = 6;
const MAX_PASSWORD_LENGTH = 72;

export const passwordSchema = z
  .string()
  .min(MIN_PASSWORD_LENGTH, `비밀번호는 최소 ${MIN_PASSWORD_LENGTH}자 이상이어야 합니다.`)
  .max(MAX_PASSWORD_LENGTH, `비밀번호는 최대 ${MAX_PASSWORD_LENGTH}자까지 가능합니다.`)
  .refine(
    (v) => /[A-Za-z]/.test(v) && /\d/.test(v),
    '비밀번호는 영문과 숫자를 모두 포함해야 합니다.'
  );

export const emailSchema = z
  .string()
  .min(1, '이메일을 입력해 주세요.')
  .email('이메일 형식이 올바르지 않습니다.');

export const nameSchema = z
  .string()
  .trim()
  .min(1, '이름을 입력해 주세요.')
  .max(100, '이름이 너무 깁니다.');

/** 한국 휴대폰(01x)만 — 문자 수신이 가능한 번호여야 한다. */
export const koreanMobileSchema = z
  .string()
  .min(1, '휴대폰 번호를 입력해 주세요.')
  .refine((v) => {
    const normalized = normalizeKoreanPhone(v);
    return normalized !== null && normalized.startsWith('01');
  }, '휴대폰 번호 형식이 올바르지 않습니다. 예: 010-1234-5678');

export const phoneTokenSchema = z.string().min(1, '휴대폰 인증을 완료해 주세요.');

const passwordsMatch = (
  data: { password: string; confirm: string },
  message = '비밀번호가 일치하지 않습니다.'
) => data.password === data.confirm || message;

export const loginSchema = z.object({
  email: emailSchema,
  password: z.string().min(1, '비밀번호를 입력해 주세요.')
});
export type LoginValues = z.infer<typeof loginSchema>;

export const signupSchema = z
  .object({
    name: nameSchema,
    email: emailSchema,
    phone: koreanMobileSchema,
    phoneToken: phoneTokenSchema,
    password: passwordSchema,
    confirm: z.string().min(1, '비밀번호 확인을 입력해 주세요.'),
    agreed: z.boolean()
  })
  .refine((d) => d.agreed, {
    path: ['agreed'],
    message: '이용약관 및 개인정보처리방침에 동의해 주세요.'
  })
  .refine((d) => passwordsMatch(d) === true, {
    path: ['confirm'],
    message: '비밀번호가 일치하지 않습니다.'
  });
export type SignupValues = z.infer<typeof signupSchema>;

export const findEmailSchema = z.object({
  phone: koreanMobileSchema,
  phoneToken: phoneTokenSchema
});
export type FindEmailValues = z.infer<typeof findEmailSchema>;

export const findPasswordSchema = z
  .object({
    email: emailSchema,
    phone: koreanMobileSchema,
    phoneToken: phoneTokenSchema,
    password: passwordSchema,
    confirm: z.string().min(1, '비밀번호 확인을 입력해 주세요.')
  })
  .refine((d) => d.password === d.confirm, {
    path: ['confirm'],
    message: '비밀번호가 일치하지 않습니다.'
  });
export type FindPasswordValues = z.infer<typeof findPasswordSchema>;

export const changePasswordSchema = z
  .object({
    current: z.string().min(1, '현재 비밀번호를 입력해 주세요.'),
    password: passwordSchema,
    confirm: z.string().min(1, '비밀번호 확인을 입력해 주세요.')
  })
  .refine((d) => d.password === d.confirm, {
    path: ['confirm'],
    message: '새 비밀번호가 일치하지 않습니다.'
  });
export type ChangePasswordValues = z.infer<typeof changePasswordSchema>;

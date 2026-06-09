/**
 * 상담 리드 폼 클라이언트 검증 (CMP-DIRECT).
 *
 * 연락처 정규화/검증 규칙은 백엔드 `apps/api/src/schemas/leads.py` 의
 * `normalize_korean_phone` 과 동일하게 유지한다 (서버가 최종 권위).
 */

import { z } from 'zod';

const NON_DIGIT_RE = /[^\d]/g;
const MOBILE_RE = /^01[016789]\d{7,8}$/;
const GENERAL_PHONE_RE = /^0\d{8,10}$/;

/** 유효하면 정규화된 연락처, 아니면 null. */
export function normalizeKoreanPhone(raw: string): string | null {
  const digits = (raw ?? '').replace(NON_DIGIT_RE, '');
  if (MOBILE_RE.test(digits)) {
    return digits.length === 11
      ? `${digits.slice(0, 3)}-${digits.slice(3, 7)}-${digits.slice(7)}`
      : `${digits.slice(0, 3)}-${digits.slice(3, 6)}-${digits.slice(6)}`;
  }
  if (GENERAL_PHONE_RE.test(digits)) {
    return digits;
  }
  return null;
}

/** @mantine/form validate 용 — 에러 메시지 또는 null. */
export function validateKoreanPhone(raw: string): string | null {
  if (!raw || !raw.trim()) {
    return '연락처를 입력해 주세요.';
  }
  return normalizeKoreanPhone(raw) === null
    ? '연락처 형식이 올바르지 않습니다. 예: 010-1234-5678'
    : null;
}

/** @mantine/form validate 용 — 비어 있지 않은 필수 텍스트. */
export function validateRequiredText(message: string) {
  return (value: string): string | null =>
    value && value.trim().length > 0 ? null : message;
}

// ---------------------------------------------------------------------------
// react-hook-form + zod 스키마 (lib/auth/validation 과 동일 패턴). 빠른 상담(메인
// 페이지) 폼이 사용한다. 휴대폰/일반전화 모두 normalizeKoreanPhone SSOT 로 검증한다.
// ---------------------------------------------------------------------------

export const applicantKindSchema = z.enum(['individual', 'company']);

export const applicantNameSchema = z
  .string()
  .trim()
  .min(1, '이름을 입력해 주세요.')
  .max(100, '이름이 너무 깁니다.');

/** 한국 휴대폰 또는 일반전화 — 정규화 가능한 형식이면 통과. */
export const koreanPhoneSchema = z
  .string()
  .min(1, '연락처를 입력해 주세요.')
  .refine(
    (v) => normalizeKoreanPhone(v) !== null,
    '연락처 형식이 올바르지 않습니다. 예: 010-1234-5678'
  );

export const quickConsultSchema = z.object({
  applicant_kind: applicantKindSchema,
  applicant_name: applicantNameSchema,
  applicant_phone: koreanPhoneSchema,
  message: z.string().max(5000, '상담 내용은 5000자 이내로 입력해 주세요.')
});
export type QuickConsultValues = z.infer<typeof quickConsultSchema>;

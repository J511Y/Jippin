/**
 * 상담 리드 폼 클라이언트 검증 (CMP-DIRECT).
 *
 * 연락처 정규화/검증 규칙은 백엔드 `apps/api/src/schemas/leads.py` 의
 * `normalize_korean_phone` 과 동일하게 유지한다 (서버가 최종 권위).
 */

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

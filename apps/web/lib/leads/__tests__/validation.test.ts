import { describe, expect, it } from 'vitest';
import { normalizeKoreanPhone, validateKoreanPhone } from '@/lib/leads/validation';

describe('normalizeKoreanPhone', () => {
  it('normalizes mobile numbers to hyphenated form', () => {
    expect(normalizeKoreanPhone('01012345678')).toBe('010-1234-5678');
    expect(normalizeKoreanPhone('010-1234-5678')).toBe('010-1234-5678');
    expect(normalizeKoreanPhone('010 1234 5678')).toBe('010-1234-5678');
    expect(normalizeKoreanPhone('011-345-6789')).toBe('011-345-6789');
  });

  it('keeps general/landline digits', () => {
    expect(normalizeKoreanPhone('0212345678')).toBe('0212345678');
  });

  it('returns null for invalid input', () => {
    expect(normalizeKoreanPhone('123')).toBeNull();
    expect(normalizeKoreanPhone('abcd')).toBeNull();
    expect(normalizeKoreanPhone('')).toBeNull();
    expect(normalizeKoreanPhone('999-9999-9999')).toBeNull();
  });
});

describe('validateKoreanPhone', () => {
  it('returns null for valid numbers', () => {
    expect(validateKoreanPhone('010-1234-5678')).toBeNull();
  });

  it('returns an error message for empty or invalid input', () => {
    expect(validateKoreanPhone('')).toMatch(/입력/);
    expect(validateKoreanPhone('123')).toMatch(/형식/);
  });
});

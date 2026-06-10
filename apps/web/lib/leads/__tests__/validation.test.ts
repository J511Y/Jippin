import { describe, expect, it } from 'vitest';
import {
  formatKoreanPhone,
  normalizeKoreanPhone,
  validateKoreanPhone
} from '@/lib/leads/validation';

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

describe('formatKoreanPhone', () => {
  it('hyphenates a full mobile number typed without separators', () => {
    expect(formatKoreanPhone('01012345678')).toBe('010-1234-5678');
  });

  it('formats progressively while typing', () => {
    expect(formatKoreanPhone('010')).toBe('010');
    expect(formatKoreanPhone('0101234')).toBe('010-1234');
    expect(formatKoreanPhone('010123456')).toBe('010-123-456');
    expect(formatKoreanPhone('0101234567')).toBe('010-123-4567');
  });

  it('keeps an already-hyphenated mobile number stable', () => {
    expect(formatKoreanPhone('010-1234-5678')).toBe('010-1234-5678');
  });

  it('handles 10-digit mobile prefixes as 3-3-4', () => {
    expect(formatKoreanPhone('0113456789')).toBe('011-345-6789');
  });

  it('formats Seoul 02 landline numbers', () => {
    expect(formatKoreanPhone('0212345678')).toBe('02-1234-5678');
    expect(formatKoreanPhone('021234567')).toBe('02-123-4567');
  });

  it('strips non-digits and caps at 11 digits', () => {
    expect(formatKoreanPhone('010 1234 5678')).toBe('010-1234-5678');
    expect(formatKoreanPhone('010-1234-5678-9')).toBe('010-1234-5678');
  });

  it('returns empty string for empty/garbage input', () => {
    expect(formatKoreanPhone('')).toBe('');
    expect(formatKoreanPhone('abc')).toBe('');
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

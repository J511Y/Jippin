'use client';

import { TextInput, type TextInputProps } from '@mantine/core';

import { formatKoreanPhone } from '@/lib/leads/validation';

/**
 * 한국 전화번호 전용 입력 (CMP-DIRECT).
 *
 * 입력값을 `formatKoreanPhone` 으로 실시간 정규화해 `010-1234-5678` 형태로 보여준다.
 * `01012345678` 처럼 하이픈 없이 입력하거나 붙여넣어도 자동으로 하이픈이 끼워진다.
 * 최종 검증/정규화는 폼 레벨의 `validateKoreanPhone`/`normalizeKoreanPhone`(SSOT)이 맡는다.
 *
 * 값 계약은 `value: string` + `onChange(value: string)` 으로, @mantine/form 의
 * `getInputProps` 스프레드와 react-hook-form 의 `<Controller>` 양쪽에 그대로 연결된다.
 */

type PhoneInputProps = Omit<TextInputProps, 'value' | 'onChange'> & {
  value?: string;
  onChange?: (value: string) => void;
};

export function PhoneInput({ value, onChange, ...props }: PhoneInputProps) {
  return (
    <TextInput
      inputMode="tel"
      autoComplete="tel"
      placeholder="010-0000-0000"
      maxLength={13}
      {...props}
      value={value ?? ''}
      onChange={(event) => onChange?.(formatKoreanPhone(event.currentTarget.value))}
    />
  );
}

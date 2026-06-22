'use client';

import { Button, Group, TextInput } from '@mantine/core';
import { IconSend } from '@tabler/icons-react';
import { useState, type FormEvent } from 'react';

type Props = {
  onSubmit: (text: string) => void | Promise<void>;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
  /** 서버측 상한과 맞추는 입력 글자수 cap(초과 입력·과대 LLM 호출 방지). */
  maxLength?: number;
};

export function MessageInput({
  onSubmit,
  disabled,
  placeholder = '메시지를 입력하세요...',
  className,
  maxLength
}: Props) {
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || busy || disabled) return;
    if (maxLength !== undefined && trimmed.length > maxLength) return;
    setBusy(true);
    try {
      await onSubmit(trimmed);
      setValue('');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      data-testid="a2ui-message-input"
      className={className}
    >
      <Group align="flex-end" gap="sm" wrap="nowrap">
        <TextInput
          aria-label="메시지 입력"
          autoComplete="off"
          disabled={disabled || busy}
          maxLength={maxLength}
          onChange={(event) => setValue(event.currentTarget.value)}
          placeholder={placeholder}
          radius="md"
          style={{ flex: 1 }}
          value={value}
        />
        <Button
          color="jippin"
          disabled={disabled || busy || value.trim().length === 0}
          leftSection={<IconSend size={16} aria-hidden />}
          loading={busy}
          type="submit"
        >
          보내기
        </Button>
      </Group>
    </form>
  );
}

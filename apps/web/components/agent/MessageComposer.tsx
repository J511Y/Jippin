'use client';

/**
 * 채팅 입력 컴포저 (CMP-DIRECT 채팅 UX 재설계).
 *
 * ChatGPT/Gemini 식 단일 입력창. compose 모드(중앙 인사말 + 예시 칩)와 dock 모드(하단
 * sticky)를 같은 컴포넌트로 지원한다. Textarea 자동 높이, Enter=전송 / Shift+Enter=줄바꿈,
 * 전송 즉시 입력 비우기, 스트리밍 중 비활성, 빈 입력 시 전송 비활성, maxLength 8000.
 */

import { ActionIcon, Box, Group, Stack, Textarea, UnstyledButton } from '@mantine/core';
import { IconArrowUp } from '@tabler/icons-react';
import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react';

export const AGENT_MESSAGE_MAX_CHARS = 8000;

export type ComposerVariant = 'compose' | 'dock';

type Props = {
  onSend: (text: string) => void | Promise<void>;
  /** 스트리밍 중이면 입력/전송 비활성 + 로딩 표시. */
  busy?: boolean;
  disabled?: boolean;
  variant?: ComposerVariant;
  placeholder?: string;
  /** compose 모드에서 입력창 위에 노출할 예시 질문 칩. */
  examples?: string[];
  /** 예시 칩 클릭 시 콜백(없으면 onSend 로 바로 전송). */
  onExample?: (text: string) => void;
};

export function MessageComposer({
  onSend,
  busy = false,
  disabled = false,
  variant = 'dock',
  placeholder = '메시지를 입력하세요',
  examples,
  onExample
}: Props) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // 자동 높이: scrollHeight 에 맞춰 늘리되 상한(약 8줄)에서 스크롤로 전환.
  const autosize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, []);

  useEffect(() => {
    autosize();
  }, [value, autosize]);

  const canSend = value.trim().length > 0 && !busy && !disabled;

  const submit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || busy || disabled) return;
    if (trimmed.length > AGENT_MESSAGE_MAX_CHARS) return;
    // 전송 즉시 입력을 비운다(스트리밍 끝까지 텍스트가 남아 혼란하던 문제 해소).
    setValue('');
    void onSend(trimmed);
  }, [value, busy, disabled, onSend]);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLTextAreaElement>) => {
      // Enter=전송, Shift+Enter=줄바꿈. IME 조합 중 Enter 는 무시(한글 입력 보호).
      if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
        event.preventDefault();
        submit();
      }
    },
    [submit]
  );

  const handleExample = useCallback(
    (text: string) => {
      if (busy || disabled) return;
      if (onExample) onExample(text);
      else void onSend(text);
    },
    [busy, disabled, onExample, onSend]
  );

  const field = (
    <Box
      style={{
        display: 'flex',
        alignItems: 'flex-end',
        gap: 8,
        padding: '8px 8px 8px 16px',
        background: 'var(--jippin-brand-surface-alt, #FFFFFF)',
        border: '1px solid var(--jippin-brand-border)',
        borderRadius: 24,
        boxShadow: '0 1px 3px rgba(13, 27, 42, 0.06)'
      }}
    >
      <Textarea
        ref={textareaRef}
        aria-label="메시지 입력"
        autosize={false}
        disabled={disabled}
        maxLength={AGENT_MESSAGE_MAX_CHARS}
        minRows={1}
        onChange={(event) => setValue(event.currentTarget.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        rows={1}
        value={value}
        variant="unstyled"
        styles={{
          root: { flex: 1 },
          input: {
            padding: 0,
            paddingTop: 6,
            paddingBottom: 6,
            lineHeight: 1.5,
            resize: 'none',
            maxHeight: 200,
            color: 'var(--jippin-brand-ink)'
          }
        }}
      />
      <ActionIcon
        aria-label="메시지 보내기"
        color="jippin"
        disabled={!canSend}
        loading={busy}
        onClick={submit}
        radius="xl"
        size={38}
        variant="filled"
      >
        <IconArrowUp size={20} aria-hidden />
      </ActionIcon>
    </Box>
  );

  if (variant === 'compose') {
    return (
      <Stack gap="md">
        {field}
        {examples && examples.length > 0 ? (
          <Group gap="xs" justify="center" wrap="wrap">
            {examples.map((example) => (
              <UnstyledButton
                key={example}
                onClick={() => handleExample(example)}
                disabled={busy || disabled}
                style={{
                  padding: '8px 14px',
                  borderRadius: 999,
                  border: '1px solid var(--jippin-brand-border)',
                  background: 'var(--jippin-brand-surface-alt, #FFFFFF)',
                  color: 'var(--jippin-brand-copy)',
                  fontSize: 'var(--mantine-font-size-sm)',
                  lineHeight: 1.4,
                  cursor: busy || disabled ? 'not-allowed' : 'pointer',
                  opacity: busy || disabled ? 0.6 : 1,
                  wordBreak: 'keep-all'
                }}
              >
                {example}
              </UnstyledButton>
            ))}
          </Group>
        ) : null}
      </Stack>
    );
  }

  return field;
}

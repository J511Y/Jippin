'use client';

/**
 * 채팅 입력 컴포저 (CMP-DIRECT 채팅 UX 재설계).
 *
 * ChatGPT/Gemini 식 단일 입력창. compose 모드(중앙 인사말 + 예시 칩)와 dock 모드(하단
 * sticky)를 같은 컴포넌트로 지원한다. Textarea 자동 높이, 전송 즉시 입력 비우기,
 * 스트리밍 중 비활성, 빈 입력 시 전송 비활성, maxLength 8000.
 *
 * Enter 정책: 데스크톱은 Enter=전송 / Shift+Enter=줄바꿈. 터치 기기(hover:none 또는
 * pointer:coarse)는 Enter=줄바꿈이고 전송은 버튼으로만 한다 — 모바일 소프트 키보드의
 * Enter 오전송(줄바꿈 의도)을 막는다.
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

  // 터치 기기 감지(hover:none / pointer:coarse) — Enter=줄바꿈으로 바꾸는 기준.
  // SSR 에서는 false(데스크톱 동작)로 시작하고 마운트 후 미디어쿼리로 확정한다.
  const [touchInput, setTouchInput] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia('(hover: none), (pointer: coarse)');
    const update = () => setTouchInput(mq.matches);
    update();
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, []);

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
      // 터치 기기: Enter=줄바꿈(기본 동작), 전송은 버튼으로만 — 인터셉트하지 않는다.
      if (touchInput) return;
      // 데스크톱: Enter=전송, Shift+Enter=줄바꿈. IME 조합 중 Enter 는 무시(한글 입력 보호).
      if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
        event.preventDefault();
        submit();
      }
    },
    [submit, touchInput]
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
      {/* 전송 버튼 — 터치 타깃 44px(터치 기기에서 유일한 전송 수단이라 특히 중요). */}
      <ActionIcon
        aria-label="메시지 보내기"
        color="jippin"
        disabled={!canSend}
        loading={busy}
        onClick={submit}
        radius="xl"
        size={44}
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
          <>
            {/* hover/focus-visible 은 인라인 스타일로 표현할 수 없어 컴포넌트 스코프
                <style> 로 제공한다 — globals.css `.hc-chip` 사양과 동일 수준(전역 CSS
                수정 없이 채팅 예시 칩에만 적용). */}
            <style>{`
              .chat-example-chip:hover:not(:disabled) {
                border-color: var(--jippin-brand-primary);
              }
              .chat-example-chip:focus-visible {
                outline: 2px solid var(--jippin-brand-primary);
                outline-offset: 2px;
              }
            `}</style>
            <Group gap="xs" justify="center" wrap="wrap">
              {examples.map((example) => (
                <UnstyledButton
                  key={example}
                  className="chat-example-chip"
                  onClick={() => handleExample(example)}
                  disabled={busy || disabled}
                  style={{
                    // 터치 타깃 ≥44px(.hc-chip 과 같은 46px) — 칩만 radius 999 허용.
                    display: 'inline-flex',
                    alignItems: 'center',
                    minHeight: 46,
                    padding: '11px 18px',
                    borderRadius: 999,
                    border: '1.5px solid var(--jippin-brand-border)',
                    background: 'var(--jippin-brand-surface-alt, #FFFFFF)',
                    color: 'var(--jippin-brand-copy)',
                    fontSize: 'var(--mantine-font-size-sm)',
                    lineHeight: 1.4,
                    cursor: busy || disabled ? 'not-allowed' : 'pointer',
                    opacity: busy || disabled ? 0.6 : 1,
                    wordBreak: 'keep-all',
                    transition: 'border-color 130ms ease'
                  }}
                >
                  {example}
                </UnstyledButton>
              ))}
            </Group>
          </>
        ) : null}
      </Stack>
    );
  }

  return field;
}

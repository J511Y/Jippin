'use client';

/**
 * 채팅 메시지 스레드 (CMP-DIRECT 채팅 UX 재설계).
 *
 * 확정 메시지 + 스트리밍 임시 버블 + 도구 활동 타임라인 + 에러를 렌더한다. 어시스턴트
 * 버블은 마크다운(ChatMarkdown)·브랜드 마크 아바타, 사용자 버블은 평문·우측 정렬.
 * 새 콘텐츠가 생기면 하단으로 자동 스크롤한다.
 */

import { Alert, Box, Group, Loader, Stack, Text } from '@mantine/core';
import { IconCheck, IconHome } from '@tabler/icons-react';
import { useEffect, useRef } from 'react';

import { DynamicComponent, type ChatMessage } from '@/components/a2ui';
import type { ToolActivityStep } from '@/lib/agent/useAgentStream';

import { ChatMarkdown } from './ChatMarkdown';

function Avatar() {
  return (
    <Box
      aria-hidden
      style={{
        flex: '0 0 auto',
        width: 30,
        height: 30,
        borderRadius: 999,
        display: 'grid',
        placeItems: 'center',
        background: 'var(--jippin-brand-primary)',
        color: 'var(--jippin-brand-primary-fg)',
        boxShadow: '0 1px 2px rgba(13, 27, 42, 0.12)'
      }}
    >
      <IconHome size={17} />
    </Box>
  );
}

function AssistantBubble({ message }: { message: ChatMessage }) {
  const dynamics = message.dynamics ?? (message.dynamic ? [message.dynamic] : []);
  return (
    <Group align="flex-start" gap="sm" wrap="nowrap" style={{ alignSelf: 'stretch' }}>
      <Avatar />
      <Box style={{ minWidth: 0, flex: 1 }}>
        <Box
          style={{
            display: 'inline-block',
            maxWidth: '100%',
            padding: '10px 14px',
            borderRadius: 16,
            borderTopLeftRadius: 4,
            background: 'var(--jippin-brand-surface-alt, #FFFFFF)',
            border: '1px solid var(--jippin-brand-border)',
            color: 'var(--jippin-brand-ink)',
            boxShadow: '0 1px 2px rgba(13, 27, 42, 0.04)',
            overflowWrap: 'break-word',
            wordBreak: 'break-word'
          }}
        >
          {message.content ? (
            <ChatMarkdown content={message.content} />
          ) : (
            <Text size="sm" c="dimmed">
              …
            </Text>
          )}
        </Box>
        {dynamics.length > 0 ? (
          <Stack gap="xs" mt="xs">
            {dynamics.map((spec, index) => (
              <DynamicComponent key={`${message.id}-dyn-${index}`} spec={spec} />
            ))}
          </Stack>
        ) : null}
      </Box>
    </Group>
  );
}

function UserBubble({ message }: { message: ChatMessage }) {
  return (
    <Box style={{ alignSelf: 'flex-end', maxWidth: '85%' }}>
      <Box
        style={{
          padding: '10px 14px',
          borderRadius: 16,
          borderTopRightRadius: 4,
          background: 'var(--jippin-brand-primary)',
          color: 'var(--jippin-brand-primary-fg)',
          boxShadow: '0 1px 2px rgba(13, 27, 42, 0.10)'
        }}
      >
        <Text
          size="sm"
          style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', overflowWrap: 'break-word' }}
        >
          {message.content}
        </Text>
      </Box>
    </Box>
  );
}

/** 도구 활동 타임라인 — 진행 중은 스피너, 완료는 체크, 실패는 빨간 점. */
function ActivityTimeline({ activity }: { activity: ToolActivityStep[] }) {
  if (activity.length === 0) return null;
  return (
    <Group align="flex-start" gap="sm" wrap="nowrap" style={{ alignSelf: 'stretch' }}>
      <Avatar />
      <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
        {activity.map((step) => (
          <Group key={step.id} gap={8} wrap="nowrap" align="center">
            {step.status === 'started' ? (
              <Loader size={14} color="jippin" />
            ) : step.status === 'succeeded' ? (
              <IconCheck size={15} color="var(--jippin-brand-primary)" aria-hidden />
            ) : (
              <Box
                aria-hidden
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: 999,
                  background: 'var(--mantine-color-danger-6)'
                }}
              />
            )}
            <Text
              size="xs"
              c={step.status === 'failed' ? 'danger.7' : 'dimmed'}
              style={{ wordBreak: 'keep-all' }}
            >
              {step.text}
            </Text>
          </Group>
        ))}
      </Stack>
    </Group>
  );
}

/** 타이핑 인디케이터(스트리밍 텍스트가 아직 없을 때). */
function TypingIndicator() {
  return (
    <Group align="center" gap="sm" wrap="nowrap" style={{ alignSelf: 'stretch' }}>
      <Avatar />
      <Group gap={5} className="chat-typing" aria-label="응답 생성 중">
        <span className="chat-typing-dot" />
        <span className="chat-typing-dot" />
        <span className="chat-typing-dot" />
      </Group>
    </Group>
  );
}

type Props = {
  messages: ChatMessage[];
  streamingText: string;
  activity: ToolActivityStep[];
  streaming: boolean;
  error: string | null;
};

export function MessageThread({ messages, streamingText, activity, streaming, error }: Props) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, streamingText, activity, streaming, error]);

  // 응답 대기 중이지만 아직 토큰도 활동도 없을 때만 타이핑 인디케이터를 보여 준다.
  const showTyping = streaming && !streamingText && activity.length === 0;

  return (
    <Stack gap="md" style={{ width: '100%' }}>
      {messages.map((message) =>
        message.role === 'user' ? (
          <UserBubble key={message.id} message={message} />
        ) : (
          <AssistantBubble key={message.id} message={message} />
        )
      )}

      {activity.length > 0 ? <ActivityTimeline activity={activity} /> : null}

      {streamingText ? (
        <AssistantBubble
          message={{
            id: '__streaming__',
            role: 'assistant',
            content: streamingText,
            createdAt: new Date().toISOString()
          }}
        />
      ) : null}

      {showTyping ? <TypingIndicator /> : null}

      {error ? (
        <Alert color="danger" variant="light" radius="md">
          {error}
        </Alert>
      ) : null}

      <div ref={endRef} />
    </Stack>
  );
}

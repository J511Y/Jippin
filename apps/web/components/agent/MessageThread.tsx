'use client';

/**
 * 채팅 메시지 스레드 (CMP-DIRECT 채팅 UX 재설계).
 *
 * 한 어시스턴트 턴 = **하나의 아바타** 아래 [도구 활동 → 본문] 순서로 렌더한다(도구가
 * 본문보다 먼저 실행되므로 활동이 위). 활동은 그 턴의 메시지에 귀속되어(useAgentStream
 * 이 message 커밋 시 attach) 완료 후에도 본문 위에 남는다. 진행 중 턴(스트리밍)도 같은
 * 한-아바타 블록으로 임시 활동 + 스트리밍 텍스트/타이핑을 보여 준다.
 */

import { Alert, Box, Group, Loader, Stack, Text } from '@mantine/core';
import { IconAlertTriangle, IconCheck } from '@tabler/icons-react';
import Image from 'next/image';
import { useEffect, useRef } from 'react';

import {
  A2uiSurface,
  type A2uiComponent,
  type ChatActivityStep,
  type ChatMessage
} from '@/components/a2ui';
import type { ToolActivityStep } from '@/lib/agent/useAgentStream';

import { ChatMarkdown } from './ChatMarkdown';

function Avatar() {
  return (
    <Box
      aria-hidden
      visibleFrom="sm"
      style={{
        flex: '0 0 auto',
        width: 30,
        height: 30,
        borderRadius: 999,
        display: 'grid',
        placeItems: 'center',
        background: 'var(--jippin-brand-surface-alt, #FFFFFF)',
        border: '1px solid var(--jippin-brand-border)',
        boxShadow: '0 1px 2px rgba(13, 27, 42, 0.10)',
        overflow: 'hidden'
      }}
    >
      <Image src="/logo.png" alt="" width={18} height={18} style={{ display: 'block' }} />
    </Box>
  );
}

/** 도구 활동 단계 목록(아바타 없음 — AssistantTurn 이 감싼다). */
function ActivitySteps({ steps }: { steps: ChatActivityStep[] }) {
  return (
    <Stack gap={6} style={{ minWidth: 0 }}>
      {steps.map((step) => (
        <Group key={step.id} gap={8} wrap="nowrap" align="center">
          {step.status === 'started' ? (
            <Loader size={14} color="jippin" />
          ) : step.status === 'succeeded' ? (
            <IconCheck size={15} color="var(--jippin-brand-primary)" aria-hidden />
          ) : (
            <IconAlertTriangle size={14} color="var(--mantine-color-danger-6)" aria-hidden />
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
  );
}

/** 타이핑 인디케이터(아직 토큰도 활동도 없을 때). */
function TypingDots() {
  return (
    <Group gap={5} className="chat-typing" aria-label="응답 생성 중">
      <span className="chat-typing-dot" />
      <span className="chat-typing-dot" />
      <span className="chat-typing-dot" />
    </Group>
  );
}

/**
 * 어시스턴트 한 턴 — 아바타 1개 + [활동 → 본문(마크다운 버블 + A2UI) / 타이핑].
 * 확정 메시지와 진행 중 스트리밍 모두 이 컴포넌트로 렌더해 아바타가 턴마다 1개만 나온다.
 */
function AssistantTurn({
  activity,
  content,
  dynamics,
  typing,
  bubbleKey
}: {
  activity?: ChatActivityStep[];
  content?: string;
  dynamics?: A2uiComponent[];
  typing?: boolean;
  bubbleKey: string;
}) {
  const hasActivity = activity != null && activity.length > 0;
  const hasContent = content != null && content.length > 0;
  const hasDynamics = dynamics != null && dynamics.length > 0;
  return (
    <Group align="flex-start" gap="sm" wrap="nowrap" style={{ alignSelf: 'stretch' }}>
      <Avatar />
      <Stack gap="xs" style={{ minWidth: 0, flex: 1 }}>
        {hasActivity ? <ActivitySteps steps={activity!} /> : null}
        {/* 마크다운은 버블 크롬 없이 본문에 직접 렌더한다(영역 확보·카드 UI 축소). */}
        {hasContent ? <ChatMarkdown content={content!} /> : null}
        {/* A2UI 카드(오버레이 등)는 본문 유무와 무관하게 렌더한다 — UI-only 메시지(빈 본문 +
            카드)가 새로고침 시 사라지던 문제 해소(#ui-only-render). */}
        {hasDynamics ? (
          <Stack gap="xs" mt={2}>
            {dynamics!.map((component, index) => (
              <A2uiSurface key={`${bubbleKey}-dyn-${index}`} component={component} />
            ))}
          </Stack>
        ) : null}
        {!hasContent && !hasDynamics && typing ? <TypingDots /> : null}
      </Stack>
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

type Props = {
  messages: ChatMessage[];
  streamingText: string;
  /** 진행 중 턴의 임시 활동(아직 메시지에 귀속되기 전). */
  activity: ToolActivityStep[];
  streaming: boolean;
  error: string | null;
};

export function MessageThread({ messages, streamingText, activity, streaming, error }: Props) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, streamingText, activity, streaming, error]);

  // 진행 중(스트리밍) 턴을 보여 줄지: 임시 활동이 있거나 스트리밍 텍스트가 있거나,
  // 아직 둘 다 없지만 응답 대기 중일 때. 메시지가 커밋되면 활동은 메시지로 귀속되고
  // 임시 활동/스트리밍 텍스트가 비워져 이 블록은 사라진다(아바타 중복 방지).
  const showTyping = streaming && !streamingText && activity.length === 0;
  const showInProgress = streamingText.length > 0 || activity.length > 0 || showTyping;

  return (
    <Stack gap="md" style={{ width: '100%' }}>
      {messages.map((message) =>
        message.role === 'user' ? (
          <UserBubble key={message.id} message={message} />
        ) : (
          <AssistantTurn
            key={message.id}
            bubbleKey={message.id}
            activity={message.activity}
            content={message.content}
            dynamics={message.dynamics ?? (message.dynamic ? [message.dynamic] : [])}
          />
        )
      )}

      {showInProgress ? (
        <AssistantTurn
          bubbleKey="__streaming__"
          activity={activity}
          content={streamingText || undefined}
          typing={showTyping}
        />
      ) : null}

      {error ? (
        <Alert color="danger" variant="light" radius="md">
          {error}
        </Alert>
      ) : null}

      <div ref={endRef} />
    </Stack>
  );
}

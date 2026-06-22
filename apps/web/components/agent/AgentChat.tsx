'use client';

/**
 * 에이전트 채팅 UI (CMP-DIRECT).
 *
 * a2ui MessageList/MessageInput 를 useAgentStream 훅(SSE)과 연결한다. 스트리밍 중인
 * 토큰은 임시 assistant 버블로 보여 주고, message 이벤트가 도착하면 확정 메시지로
 * 대체한다. 도구 진행상황/오류는 보조 UI 로 노출한다.
 */

import { Alert, Group, Loader, Stack, Text } from '@mantine/core';

import { type ChatMessage, MessageInput, MessageList } from '@/components/a2ui';
import { useAgentStream } from '@/lib/agent/useAgentStream';

// 서버측 AgentUserMessage.content max_length(8000)와 일치시키는 클라이언트 입력 cap.
const AGENT_MESSAGE_MAX_CHARS = 8000;

export function AgentChat({ sessionId }: { sessionId: string }) {
  const { messages, streamingText, toolActivity, status, error, send } =
    useAgentStream(sessionId);

  const rendered: ChatMessage[] = streamingText
    ? [
        ...messages,
        {
          id: '__streaming__',
          role: 'assistant',
          content: streamingText,
          createdAt: new Date().toISOString(),
        },
      ]
    : messages;

  return (
    <Stack gap="sm">
      {rendered.length === 0 ? (
        <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
          우리집 구조에 대해 무엇이든 물어보세요. 예: “우리집 거실 벽 철거 가능한지
          확인해줘”.
        </Text>
      ) : (
        <MessageList messages={rendered} />
      )}

      {toolActivity && (
        <Group gap={6} align="center">
          <Loader size="xs" color="jippin" />
          <Text size="xs" c="dimmed">
            {toolActivity} 처리 중…
          </Text>
        </Group>
      )}

      {error && (
        <Alert color="red" variant="light" radius="md">
          {error}
        </Alert>
      )}

      <MessageInput
        onSubmit={send}
        disabled={status === 'streaming'}
        maxLength={AGENT_MESSAGE_MAX_CHARS}
        placeholder="메시지를 입력하세요 (예: 우리집 내력벽 확인해줘)"
      />
    </Stack>
  );
}

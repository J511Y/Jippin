'use client';

import { Paper, Stack, Text } from '@mantine/core';
import type { CSSProperties } from 'react';
import type { ChatMessage } from '@/components/a2ui/types';
import { DynamicComponent } from '@/components/a2ui/DynamicComponent';

type Props = {
  messages: ChatMessage[];
  className?: string;
  style?: CSSProperties;
};

export function MessageList({ messages, className, style }: Props) {
  if (messages.length === 0) {
    return (
      <Stack align="center" className={className} justify="center" mih="100%" style={style}>
        <Text c="dimmed" size="sm">
          대화를 시작해 주세요.
        </Text>
      </Stack>
    );
  }

  return (
    <Stack component="ol" data-testid="a2ui-message-list" gap="sm" className={className} style={style}>
      {messages.map((message) => (
        <Paper
          component="li"
          key={message.id}
          maw="82%"
          p="sm"
          radius="lg"
          shadow="xs"
          style={{
            alignSelf: message.role === 'user' ? 'flex-end' : 'flex-start',
            background:
              message.role === 'user'
                ? 'var(--jippin-brand-primary)'
                : 'var(--mantine-color-gray-0)',
            color:
              message.role === 'user'
                ? 'var(--jippin-brand-primary-fg)'
                : 'var(--jippin-brand-ink)'
          }}
        >
          <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
            {message.content}
          </Text>
          {message.dynamic ? (
            <Stack mt="xs">
              <DynamicComponent spec={message.dynamic} />
            </Stack>
          ) : null}
        </Paper>
      ))}
    </Stack>
  );
}

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
      {messages.map((message) => {
        const isUser = message.role === 'user';
        // 디자인 QA (2026-06-05): 에이전트 메시지에도 명확한 버블 경계가 필요하다.
        // 이전엔 배경이 거의 투명해서 user 버블과 시각 무게가 비대칭이었다.
        // 1pt border + 약간 더 진한 surface 톤으로 구간 인식을 살린다.
        return (
          <Paper
            component="li"
            key={message.id}
            maw="82%"
            p="sm"
            radius="lg"
            shadow="xs"
            style={{
              alignSelf: isUser ? 'flex-end' : 'flex-start',
              background: isUser
                ? 'var(--jippin-brand-primary)'
                : 'var(--jippin-brand-surface-alt, #FFFFFF)',
              border: isUser ? 'none' : '1px solid var(--jippin-brand-border)',
              color: isUser ? 'var(--jippin-brand-primary-fg)' : 'var(--jippin-brand-ink)'
            }}
          >
            <Text size="sm" style={{ whiteSpace: 'pre-wrap', wordBreak: 'keep-all', overflowWrap: 'break-word' }}>
              {message.content}
            </Text>
            {message.dynamic ? (
              <Stack mt="xs">
                <DynamicComponent spec={message.dynamic} />
              </Stack>
            ) : null}
          </Paper>
        );
      })}
    </Stack>
  );
}

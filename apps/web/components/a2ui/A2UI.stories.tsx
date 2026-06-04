import { useState } from 'react';
import { Paper, Stack } from '@mantine/core';
import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { MessageInput } from '@/components/a2ui/MessageInput';
import { MessageList } from '@/components/a2ui/MessageList';
import type { ChatMessage } from '@/components/a2ui/types';

const initialMessages: ChatMessage[] = [
  {
    id: 'm1',
    role: 'assistant',
    content: '주소와 도면을 알려 주세요. 사전검토를 시작하겠습니다.',
    createdAt: '2026-06-04T09:00:00.000Z'
  },
  {
    id: 'm2',
    role: 'user',
    content: '거실과 발코니 사이 벽을 철거해도 되는지 알고 싶습니다.',
    createdAt: '2026-06-04T09:01:00.000Z'
  },
  {
    id: 'm3',
    role: 'assistant',
    content: '평면도에서 후보 영역을 표시했습니다. 색칠된 부분을 눌러 자세히 보세요.',
    createdAt: '2026-06-04T09:02:00.000Z',
    dynamic: {
      kind: 'floorplan-confirm',
      payload: {
        selectedRegionId: 'region-12',
        confidence: 0.82
      }
    }
  }
];

function ChatSurface() {
  const [messages, setMessages] = useState(initialMessages);

  return (
    <Paper h={520} p="md" radius="md" shadow="sm" withBorder w={640}>
      <Stack h="100%">
        <MessageList messages={messages} style={{ flex: 1, overflowY: 'auto' }} />
        <MessageInput
          onSubmit={(content) => {
            setMessages((current) => [
              ...current,
              {
                id: `m${current.length + 1}`,
                role: 'user',
                content,
                createdAt: new Date().toISOString()
              }
            ]);
          }}
          placeholder="도면이나 철거 위치를 설명해 주세요."
        />
      </Stack>
    </Paper>
  );
}

const meta = {
  title: 'A2UI/ChatSurface',
  parameters: {
    layout: 'centered'
  },
  tags: ['autodocs']
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const Basic: Story = {
  render: () => <ChatSurface />
};

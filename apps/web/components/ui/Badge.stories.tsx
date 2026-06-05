import { Badge, Group, Stack, Text } from '@mantine/core';
import {
  IconAlertTriangle,
  IconCircleCheck,
  IconFileReport,
  IconHelpCircle,
  IconInfoCircle,
  IconX
} from '@tabler/icons-react';
import type { Meta, StoryObj } from '@storybook/nextjs-vite';

const meta = {
  title: 'UI/Badge',
  component: Badge,
  parameters: {
    layout: 'centered'
  },
  tags: ['autodocs'],
  args: {
    children: '추가 확인 필요',
    color: 'warning',
    variant: 'light'
  }
} satisfies Meta<typeof Badge>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Playground: Story = {};

export const ResultStates: Story = {
  render: () => (
    <Stack gap="sm">
      <Text c="dimmed" size="sm">색 + 라벨 + 아이콘 세 가지로 동시에 의미를 전달합니다 (COLOR_SYSTEM §4.1).</Text>
      <Group>
        <Badge color="success" leftSection={<IconCircleCheck size={12} aria-hidden />} variant="light">
          가능성 있음
        </Badge>
        <Badge color="danger" leftSection={<IconX size={12} aria-hidden />} variant="light">
          제한 확인
        </Badge>
        <Badge color="warning" leftSection={<IconAlertTriangle size={12} aria-hidden />} variant="light">
          추가 확인 필요
        </Badge>
        <Badge color="info" leftSection={<IconInfoCircle size={12} aria-hidden />} variant="light">
          참고 안내
        </Badge>
        <Badge color="gray" leftSection={<IconHelpCircle size={12} aria-hidden />} variant="light">
          검토 대기
        </Badge>
      </Group>
    </Stack>
  )
};

export const SolidStates: Story = {
  render: () => (
    <Stack gap="sm">
      <Text c="dimmed" size="sm">
        filled variant 는 더 강한 신호가 필요할 때 사용합니다. warning 색은 머스타드 톤이라 색만으로
        &lsquo;주의&rsquo; 신호가 약할 수 있으므로 아이콘을 함께 노출합니다.
      </Text>
      <Group>
        <Badge color="success" leftSection={<IconCircleCheck size={12} aria-hidden />} variant="filled">
          가능
        </Badge>
        <Badge color="danger" leftSection={<IconX size={12} aria-hidden />} variant="filled">
          불가
        </Badge>
        <Badge color="warning" leftSection={<IconAlertTriangle size={12} aria-hidden />} variant="filled">
          보류
        </Badge>
        <Badge color="blueprint" leftSection={<IconFileReport size={12} aria-hidden />} variant="filled">
          전문 검토
        </Badge>
      </Group>
    </Stack>
  )
};

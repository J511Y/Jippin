import { Badge, Group, Stack, Text } from '@mantine/core';
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
      <Text c="dimmed" size="sm">색만으로 의미를 전달하지 않고 라벨을 함께 노출합니다.</Text>
      <Group>
        <Badge color="success" variant="light">가능성 있음</Badge>
        <Badge color="danger" variant="light">제한 확인</Badge>
        <Badge color="warning" variant="light">추가 확인 필요</Badge>
        <Badge color="info" variant="light">참고 안내</Badge>
        <Badge color="gray" variant="light">검토 대기</Badge>
      </Group>
    </Stack>
  )
};

export const SolidStates: Story = {
  render: () => (
    <Group>
      <Badge color="success" variant="filled">가능</Badge>
      <Badge color="danger" variant="filled">불가</Badge>
      <Badge color="warning" variant="filled">보류</Badge>
      <Badge color="blueprint" variant="filled">전문 검토</Badge>
    </Group>
  )
};

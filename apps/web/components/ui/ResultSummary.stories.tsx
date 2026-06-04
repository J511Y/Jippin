import { Alert, Badge, Button, Card, Group, List, Stack, Text, Title } from '@mantine/core';
import { IconAlertTriangle, IconCircleCheck, IconFileReport, IconX } from '@tabler/icons-react';
import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { LegalNotice } from '@/components/LegalNotice';

const meta = {
  title: 'UI/ResultSummary',
  parameters: {
    layout: 'centered'
  },
  tags: ['autodocs']
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const Pending: Story = {
  render: () => (
    <Card p="lg" radius="md" shadow="sm" withBorder w={620}>
      <Stack>
        <Group justify="space-between">
          <Title order={2}>지금 정보만으로는 판단이 어렵습니다.</Title>
          <Badge color="warning" leftSection={<IconAlertTriangle size={14} aria-hidden />} variant="light">
            추가 확인 필요
          </Badge>
        </Group>
        <Text c="dimmed">
          도면 후보는 확인됐지만 관할 행정기관 제출 전 추가 확인이 필요합니다.
        </Text>
        <List size="sm" spacing="xs">
          <List.Item>평면도에서 비내력벽 후보가 확인됩니다.</List.Item>
          <List.Item>행위허가 검토에 필요한 추가 도면이 아직 없습니다.</List.Item>
        </List>
        <Alert color="info" icon={<IconFileReport size={18} aria-hidden />} variant="light">
          근거 법령과 도면 후보 영역을 함께 확인해 주세요.
        </Alert>
        <LegalNotice variant="inline" />
      </Stack>
    </Card>
  )
};

export const PossibleWithCta: Story = {
  render: () => (
    <Card p="lg" radius="md" shadow="sm" withBorder w={620}>
      <Stack>
        <Group justify="space-between">
          <Title order={2}>지금 정보 기준으로는 가능성이 있습니다.</Title>
          <Badge color="success" leftSection={<IconCircleCheck size={14} aria-hidden />} variant="light">
            가능성 있음
          </Badge>
        </Group>
        <Text c="dimmed">
          사전검토 기준으로 가능성이 있습니다. 제출 전 근거와 예외 조건을 확인해 주세요.
        </Text>
        <List size="sm" spacing="xs">
          <List.Item>비내력벽 후보 위치와 사용자가 선택한 철거 영역이 일치합니다.</List.Item>
          <List.Item>견적 비교를 위해 현장 확인이 필요합니다.</List.Item>
        </List>
        <Button color="coral" c="var(--jippin-brand-cta-fg)">상담 신청</Button>
        <LegalNotice variant="inline" />
      </Stack>
    </Card>
  )
};

export const Blocked: Story = {
  render: () => (
    <Card p="lg" radius="md" shadow="sm" withBorder w={620}>
      <Stack>
        <Group justify="space-between">
          <Title order={2}>제출하신 정보로는 어렵습니다.</Title>
          <Badge color="danger" leftSection={<IconX size={14} aria-hidden />} variant="light">
            제한 확인
          </Badge>
        </Group>
        <Text c="dimmed">제출하신 정보로는 어렵습니다. 사유는 다음과 같습니다.</Text>
        <List size="sm" spacing="xs">
          <List.Item>선택한 철거 영역이 구조 안전 검토 대상에 해당합니다.</List.Item>
          <List.Item>관할 행정기관 또는 전문가 확인 없이 진행하기 어렵습니다.</List.Item>
        </List>
        <LegalNotice variant="inline" />
      </Stack>
    </Card>
  )
};

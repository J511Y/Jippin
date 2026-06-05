import {
  Anchor,
  Badge,
  Button,
  Card,
  Group,
  Stack,
  Text,
  Title
} from '@mantine/core';
import { IconChevronRight } from '@tabler/icons-react';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '상담 진행'
};

const mockContacts = [
  {
    id: 'demo-c1',
    title: '강남구 ○○로 12 비내력벽',
    status: '담당자 배정 완료',
    color: 'jippin' as const,
    updatedAt: '2026-06-05'
  },
  {
    id: 'demo-c2',
    title: '성남시 분당구 ○○로 4 거실 확장',
    status: '현장 방문 예정',
    color: 'success' as const,
    updatedAt: '2026-06-03'
  }
];

export default function ContactsPage() {
  return (
    <Stack gap="lg">
      <Stack gap="xs">
        <Title order={1}>상담 진행</Title>
        <Text c="dimmed" size="sm" style={{ wordBreak: 'keep-all' }}>
          신청한 상담의 진행 상태와 메모, 첨부를 확인할 수 있어요. 새 상담을
          신청하려면{' '}
          <Anchor href="/leads" c="var(--jippin-brand-primary)">
            상담 신청
          </Anchor>{' '}
          으로 이동하세요.
        </Text>
      </Stack>

      <Stack gap="sm">
        {mockContacts.map((contact) => (
          <Card
            key={contact.id}
            component="a"
            href={`/contacts/${contact.id}`}
            withBorder
            radius="md"
            padding="md"
            style={{ textDecoration: 'none', color: 'inherit' }}
          >
            <Group justify="space-between" align="flex-start" wrap="nowrap">
              <Stack gap={4}>
                <Text fw={600} style={{ wordBreak: 'keep-all' }}>
                  {contact.title}
                </Text>
                <Group gap="xs">
                  <Badge color={contact.color} variant="light" radius="sm">
                    {contact.status}
                  </Badge>
                  <Text size="xs" c="dimmed">
                    {contact.updatedAt}
                  </Text>
                </Group>
              </Stack>
              <IconChevronRight size={18} aria-hidden />
            </Group>
          </Card>
        ))}
      </Stack>

      <Button
        component="a"
        href="/leads/new"
        size="md"
        color="coral"
        variant="light"
        radius="md"
        fullWidth
      >
        새 상담 신청하기
      </Button>

      <Card withBorder radius="md" padding="md" bg="var(--jippin-brand-surface)">
        <Text size="sm" c="dimmed">
          이 목록은 placeholder 입니다. 실제 상담 목록 API 는 후속 이슈에서 연결됩니다.
        </Text>
      </Card>
    </Stack>
  );
}

import {
  Anchor,
  Badge,
  Button,
  Card,
  Group,
  Stack,
  Text,
  ThemeIcon,
  Title
} from '@mantine/core';
import { IconChevronRight, IconInbox } from '@tabler/icons-react';
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
  const hasContacts = mockContacts.length > 0;

  return (
    <Stack gap="xl">
      <Group justify="space-between" align="flex-end" wrap="nowrap">
        <Stack gap="xs">
          <Title order={1} fz="h1">
            상담 진행
          </Title>
          <Text c="dimmed" size="sm" style={{ wordBreak: 'keep-all' }}>
            신청한 상담의 진행 상태와 메모, 첨부를 확인할 수 있어요.
          </Text>
        </Stack>
        <Button
          component="a"
          href="/leads/new"
          color="coral"
          radius="md"
          visibleFrom="xs"
        >
          새 상담
        </Button>
      </Group>

      {hasContacts ? (
        <Stack gap="sm">
          {mockContacts.map((contact) => (
            <Card
              key={contact.id}
              component="a"
              href={`/contacts/${contact.id}`}
              withBorder
              radius="lg"
              padding="lg"
              style={{ textDecoration: 'none', color: 'inherit' }}
            >
              <Group justify="space-between" align="center" wrap="nowrap">
                <Stack gap={6}>
                  <Text fw={600} style={{ wordBreak: 'keep-all' }}>
                    {contact.title}
                  </Text>
                  <Group gap="xs">
                    <Badge color={contact.color} variant="light" radius="sm">
                      {contact.status}
                    </Badge>
                    <Text size="xs" c="dimmed">
                      {contact.updatedAt} 업데이트
                    </Text>
                  </Group>
                </Stack>
                <ThemeIcon variant="subtle" color="gray" size="md">
                  <IconChevronRight size={18} aria-hidden />
                </ThemeIcon>
              </Group>
            </Card>
          ))}
        </Stack>
      ) : (
        <Card withBorder radius="lg" padding="xl">
          <Stack align="center" gap="sm" ta="center" py="lg">
            <ThemeIcon size={52} radius="xl" variant="light" color="gray">
              <IconInbox size={26} />
            </ThemeIcon>
            <Text fw={600}>아직 신청한 상담이 없어요</Text>
            <Text size="sm" c="dimmed">
              전문가 상담을 신청하면 여기에서 진행 상태를 추적할 수 있어요.
            </Text>
            <Button component="a" href="/leads/new" color="coral" radius="md" mt="xs">
              상담 신청하기
            </Button>
          </Stack>
        </Card>
      )}

      <Text size="xs" c="dimmed" ta="center">
        이 목록은 미리보기 데이터입니다.{' '}
        <Anchor href="/leads" size="xs" c="var(--jippin-brand-primary)">
          상담 신청 안내
        </Anchor>
      </Text>
    </Stack>
  );
}

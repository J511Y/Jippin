import { Badge, Button, Card, Group, Stack, Text, Title } from '@mantine/core';
import { IconChevronRight } from '@tabler/icons-react';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '사전검토 세션'
};

const mockSessions = [
  {
    id: 'demo-1',
    address: '서울 강남구 ○○로 12',
    updatedAt: '2026-06-05 14:21',
    status: '리포트 준비 중'
  },
  {
    id: 'demo-2',
    address: '경기 성남시 분당구 ○○로 4',
    updatedAt: '2026-06-04 19:02',
    status: '도면 분석 완료'
  }
];

export default function SessionsPage() {
  return (
    <Stack gap="lg">
      <Stack gap="xs">
        <Title order={1}>사전검토 세션</Title>
        <Text c="dimmed" size="sm" style={{ wordBreak: 'keep-all' }}>
          진행 중인 사전검토 세션을 확인하거나 새로 시작할 수 있어요. 익명으로 시작한
          세션은 이 기기에서만 보입니다.
        </Text>
      </Stack>

      <Button
        component="a"
        href="/sessions/new"
        size="lg"
        color="jippin"
        radius="md"
        fullWidth
      >
        새 검토 만들기
      </Button>

      <Stack gap="sm">
        {mockSessions.map((session) => (
          <Card
            key={session.id}
            component="a"
            href={`/sessions/${session.id}`}
            withBorder
            radius="md"
            padding="md"
            style={{ textDecoration: 'none', color: 'inherit' }}
          >
            <Group justify="space-between" align="flex-start" wrap="nowrap">
              <Stack gap={4}>
                <Text fw={600} style={{ wordBreak: 'keep-all' }}>
                  {session.address}
                </Text>
                <Group gap="xs">
                  <Badge color="jippin" variant="light" radius="sm">
                    {session.status}
                  </Badge>
                  <Text size="xs" c="dimmed">
                    {session.updatedAt}
                  </Text>
                </Group>
              </Stack>
              <IconChevronRight size={18} aria-hidden />
            </Group>
          </Card>
        ))}
      </Stack>

      <Card withBorder radius="md" padding="md" bg="var(--jippin-brand-surface)">
        <Stack gap="xs">
          <Text size="sm" c="dimmed">
            이 목록은 placeholder 입니다. 실제 세션 목록 API 는 후속 이슈에서 연결됩니다.
          </Text>
        </Stack>
      </Card>
    </Stack>
  );
}

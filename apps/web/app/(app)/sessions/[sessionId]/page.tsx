import { Badge, Button, Card, Group, Stack, Text, Title } from '@mantine/core';
import type { Metadata } from 'next';

import { AgentChat } from '@/components/agent/AgentChat';

type SessionPageProps = {
  params: Promise<{ sessionId: string }>;
};

export const metadata: Metadata = {
  title: '사전검토 진행',
  robots: { index: false, follow: false }
};

export default async function SessionDetailPage({ params }: SessionPageProps) {
  const { sessionId } = await params;

  return (
    <Stack gap="lg">
      <Stack gap="xs">
        <Badge color="jippin" variant="light" radius="sm" w="fit-content">
          세션 ID · {sessionId}
        </Badge>
        <Title order={1}>사전검토 진행 중</Title>
        <Text c="dimmed" size="sm" style={{ wordBreak: 'keep-all' }}>
          도면을 분석하고 행위허가 가능성을 판단하고 있어요. 완료되면 리포트로
          이동할 수 있습니다.
        </Text>
      </Stack>

      <Card withBorder radius="md" padding="md">
        <Stack gap="sm">
          <Group justify="space-between">
            <Text fw={600}>도면 업로드</Text>
            <Badge color="success" variant="light">
              완료
            </Badge>
          </Group>
          <Group justify="space-between">
            <Text fw={600}>도면 분석</Text>
            <Badge color="jippin" variant="light">
              진행 중
            </Badge>
          </Group>
          <Group justify="space-between">
            <Text fw={600}>AI 판단</Text>
            <Badge color="gray" variant="light">
              대기
            </Badge>
          </Group>
          <Group justify="space-between">
            <Text fw={600}>리포트 생성</Text>
            <Badge color="gray" variant="light">
              대기
            </Badge>
          </Group>
        </Stack>
      </Card>

      <Card withBorder radius="md" padding="md">
        <Stack gap="sm">
          <Text fw={600}>AI 도우미와 대화</Text>
          <AgentChat sessionId={sessionId} />
        </Stack>
      </Card>

      <Button
        component="a"
        href={`/sessions/${sessionId}/report`}
        size="lg"
        color="jippin"
        radius="md"
        fullWidth
      >
        리포트 미리 보기
      </Button>
    </Stack>
  );
}

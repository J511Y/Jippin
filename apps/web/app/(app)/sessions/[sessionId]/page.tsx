'use client';

import { Alert, Badge, Button, Card, Group, Loader, Stack, Text, Title } from '@mantine/core';
import { IconCheck } from '@tabler/icons-react';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';

import { AgentChat } from '@/components/agent/AgentChat';
import { parseApiError } from '@/lib/api/error';
import { getSession, syncExistingToken, type SessionResponse } from '@/lib/sessions/api';

const AGENT_ENABLED = process.env.NEXT_PUBLIC_AGENT_ENABLED === 'true';

function steps(session: SessionResponse): { label: string; done: boolean }[] {
  const reportReady =
    session.status === 'report_ready' || session.completion_decision != null;
  return [
    { label: '주소 확정', done: session.address_id != null },
    { label: '도면 업로드', done: session.selected_floorplan_asset_id != null },
    {
      label: 'AI 분석',
      done: ['analyzing', 'collecting_info', 'ready_for_rule', 'report_ready'].includes(
        session.status
      )
    },
    { label: '리포트', done: reportReady }
  ];
}

export default function SessionDetailPage() {
  const params = useParams<{ sessionId: string }>();
  const sessionId = params.sessionId;
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;
    void (async () => {
      try {
        await syncExistingToken();
        const row = await getSession(sessionId);
        if (!ignore) setSession(row);
      } catch (err) {
        if (!ignore) setError(parseApiError(err).message);
      }
    })();
    return () => {
      ignore = true;
    };
  }, [sessionId]);

  return (
    <Stack gap="lg">
      <Stack gap="xs">
        <Title order={1}>사전검토 진행 중</Title>
        <Text c="dimmed" size="sm" style={{ wordBreak: 'keep-all' }}>
          AI 도우미와 대화하며 도면을 분석하고 행위허가 가능성을 판단해요. 분석이
          끝나면 리포트에서 결과를 확인할 수 있습니다.
        </Text>
      </Stack>

      {error && (
        <Alert color="red" variant="light" radius="md">
          {error}
        </Alert>
      )}

      <Card withBorder radius="md" padding="md">
        {session === null && !error ? (
          <Group justify="center" py="sm">
            <Loader size="sm" color="jippin" />
          </Group>
        ) : session !== null ? (
          <Stack gap="sm">
            {steps(session).map((step) => (
              <Group key={step.label} justify="space-between">
                <Text fw={600}>{step.label}</Text>
                {step.done ? (
                  <Badge
                    color="success"
                    variant="light"
                    leftSection={<IconCheck size={12} aria-hidden />}
                  >
                    완료
                  </Badge>
                ) : (
                  <Badge color="gray" variant="light">
                    대기
                  </Badge>
                )}
              </Group>
            ))}
          </Stack>
        ) : null}
      </Card>

      <Card withBorder radius="md" padding="md">
        {AGENT_ENABLED ? (
          <Stack gap="sm">
            <Text fw={600}>AI 도우미와 대화</Text>
            {/* key=sessionId: 세션 변경 시 remount 해 채팅 상태를 깨끗이 리셋한다. */}
            <AgentChat key={sessionId} sessionId={sessionId} />
          </Stack>
        ) : (
          <Text size="sm" c="dimmed">
            AI 도우미 채팅은 곧 제공됩니다. (현재 비활성화)
          </Text>
        )}
      </Card>

      <Button
        component="a"
        href={`/sessions/${sessionId}/report`}
        size="lg"
        color="jippin"
        radius="md"
        fullWidth
      >
        리포트 보기
      </Button>
    </Stack>
  );
}

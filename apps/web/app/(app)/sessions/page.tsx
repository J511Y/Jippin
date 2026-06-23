'use client';

import { Alert, Badge, Button, Card, Group, Loader, Stack, Text, Title } from '@mantine/core';
import { IconChevronRight } from '@tabler/icons-react';
import { useEffect, useState } from 'react';

import { parseApiError } from '@/lib/api/error';
import {
  listSessions,
  syncExistingToken,
  type SessionResponse,
  type SessionStatus
} from '@/lib/sessions/api';

const STATUS_LABEL: Record<SessionStatus, string> = {
  draft: '작성 중',
  address_ready: '주소 확인됨',
  floorplan_selected: '도면 선택됨',
  analyzing: '분석 중',
  awaiting_overlay: '도면 검토 대기',
  collecting_info: '정보 수집 중',
  ready_for_rule: '판정 준비됨',
  report_ready: '리포트 준비됨',
  handoff: '전문가 연결',
  expired: '만료됨',
  deleted: '삭제됨'
};

function formatWhen(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString('ko-KR');
}

export default function SessionsPage() {
  const [sessions, setSessions] = useState<SessionResponse[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;
    void (async () => {
      // 세션 토큰이 없으면(신규 방문) 보여줄 세션도 없다 — 빈 목록으로 처리.
      const hasToken = await syncExistingToken();
      if (!hasToken) {
        if (!ignore) setSessions([]);
        return;
      }
      try {
        const rows = await listSessions();
        if (!ignore) setSessions(rows);
      } catch (err) {
        const parsed = parseApiError(err);
        if (ignore) return;
        // 401 등 인증 부재는 빈 목록으로(에러 배너 대신).
        if (parsed.status === 401) setSessions([]);
        else setError(parsed.message);
      }
    })();
    return () => {
      ignore = true;
    };
  }, []);

  return (
    <Stack gap="lg">
      <Stack gap="xs">
        <Title order={1}>사전검토 세션</Title>
        <Text c="dimmed" size="sm" style={{ wordBreak: 'keep-all' }}>
          진행 중인 사전검토 세션을 확인하거나 새로 시작할 수 있어요. 익명으로 시작한
          세션은 이 기기의 세션에서만 보입니다.
        </Text>
      </Stack>

      <Button component="a" href="/sessions/new" size="lg" color="jippin" radius="md" fullWidth>
        새 검토 만들기
      </Button>

      {error && (
        <Alert color="red" variant="light" radius="md">
          {error}
        </Alert>
      )}

      {sessions === null && !error && (
        <Group justify="center" py="lg">
          <Loader size="sm" color="jippin" />
        </Group>
      )}

      {sessions !== null && sessions.length === 0 && (
        <Card withBorder radius="md" padding="lg">
          <Text size="sm" c="dimmed" ta="center" style={{ wordBreak: 'keep-all' }}>
            아직 시작한 사전검토가 없어요. 위 버튼으로 첫 검토를 시작해 보세요.
          </Text>
        </Card>
      )}

      <Stack gap="sm">
        {(sessions ?? []).map((session) => (
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
                  사전검토 세션
                </Text>
                <Group gap="xs">
                  <Badge color="jippin" variant="light" radius="sm">
                    {STATUS_LABEL[session.status] ?? session.status}
                  </Badge>
                  <Text size="xs" c="dimmed">
                    {formatWhen(session.last_activity_at)}
                  </Text>
                </Group>
              </Stack>
              <IconChevronRight size={18} aria-hidden />
            </Group>
          </Card>
        ))}
      </Stack>
    </Stack>
  );
}

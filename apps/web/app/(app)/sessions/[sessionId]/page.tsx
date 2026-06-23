'use client';

import {
  Alert,
  Badge,
  Button,
  Card,
  FileInput,
  Group,
  Loader,
  Stack,
  Text,
  Title
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconCheck, IconUpload } from '@tabler/icons-react';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';

import { AgentChat } from '@/components/agent/AgentChat';
import { parseApiError } from '@/lib/api/error';
import { ensureAnonymousSession } from '@/lib/leads/ensure-anonymous-session';
import {
  createFloorplanAsset,
  getSession,
  syncExistingToken,
  type SessionResponse
} from '@/lib/sessions/api';
import { deleteSessionFloorplan, uploadSessionFloorplan } from '@/lib/sessions/upload';

const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

const AGENT_ENABLED = process.env.NEXT_PUBLIC_AGENT_ENABLED === 'true';

function steps(session: SessionResponse): { label: string; done: boolean }[] {
  return [
    { label: '주소 확정', done: session.address_id != null },
    { label: '도면 업로드', done: session.selected_floorplan_asset_id != null },
    {
      label: 'AI 분석',
      // 분석은 verdict 가 나왔으면(has_report) 완료. completion_decision 은 ASK_MORE
      // 등 비-리포트 상태에도 채워지므로 단계 표시에 쓰지 않는다.
      done: session.has_report
    },
    // 리포트 준비 여부는 verdict 영속 여부로만 판정(#report-readiness).
    { label: '리포트', done: session.has_report }
  ];
}

export default function SessionDetailPage() {
  const params = useParams<{ sessionId: string }>();
  const sessionId = params.sessionId;
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [floorplan, setFloorplan] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);

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

  async function attachFloorplan() {
    if (!floorplan) return;
    if (floorplan.size > MAX_UPLOAD_BYTES) {
      notifications.show({
        color: 'red',
        title: '도면 파일이 너무 큽니다',
        message: '최대 50MB 까지 업로드할 수 있어요.'
      });
      return;
    }
    setUploading(true);
    try {
      // 첨부는 명시적 사용자 액션이므로 익명 세션 생성 허용(읽기 경로와 달리).
      await ensureAnonymousSession();
      const uploaded = await uploadSessionFloorplan(sessionId, floorplan);
      try {
        await createFloorplanAsset(sessionId, uploaded);
      } catch (assetError) {
        await deleteSessionFloorplan(uploaded.object_key);
        throw assetError;
      }
      setFloorplan(null);
      setSession(await getSession(sessionId));
      notifications.show({ color: 'green', title: '도면을 첨부했어요', message: '이제 AI 분석을 진행할 수 있어요.' });
    } catch (err) {
      notifications.show({
        color: 'red',
        title: '도면 첨부에 실패했어요',
        message: parseApiError(err).message
      });
    } finally {
      setUploading(false);
    }
  }

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

      {session !== null && (
        <Card withBorder radius="md" padding="md">
          <Stack gap="sm">
            <Group justify="space-between">
              <Text fw={600}>도면</Text>
              {session.selected_floorplan_asset_id != null && (
                <Badge color="success" variant="light">
                  첨부됨
                </Badge>
              )}
            </Group>
            <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
              {session.selected_floorplan_asset_id != null
                ? '도면이 첨부되어 있어요. 다른 도면으로 교체하려면 새로 올리세요.'
                : 'AI 분석에는 도면 이미지가 필요해요. 지금 첨부할 수 있어요.'}
            </Text>
            <FileInput
              placeholder="도면 이미지를 선택하세요 (JPG/PNG 등, PDF 미지원)"
              accept="image/*"
              leftSection={<IconUpload size={16} aria-hidden />}
              clearable
              value={floorplan}
              onChange={setFloorplan}
            />
            <Button
              color="jippin"
              radius="md"
              disabled={floorplan == null}
              loading={uploading}
              onClick={attachFloorplan}
              w="fit-content"
            >
              도면 첨부
            </Button>
          </Stack>
        </Card>
      )}

      {AGENT_ENABLED && (
        <Card withBorder radius="md" padding="md">
          {/* 소유권이 확인된 뒤(session 로드 + 에러 없음)에만 AgentChat 을 마운트한다.
              useAgentStream 이 마운트 시 익명 세션을 발급하고 에이전트 이력을 조회하므로,
              로딩 중/401·404 상태에서 마운트하면 stale·공유 URL 로 익명 유저를 만들고
              남의 세션을 탐침할 수 있다(#chat-after-ownership). */}
          {session !== null && !error ? (
            <Stack gap="sm">
              <Text fw={600}>AI 도우미와 대화</Text>
              {/* key=sessionId: 세션 변경 시 remount 해 채팅 상태를 깨끗이 리셋한다. */}
              <AgentChat key={sessionId} sessionId={sessionId} />
            </Stack>
          ) : (
            <Group justify="center" py="sm">
              <Loader size="sm" color="jippin" />
            </Group>
          )}
        </Card>
      )}

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

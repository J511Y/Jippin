'use client';

/**
 * 사전검토 세션 상세 (CMP-DIRECT 대화형 UX 재설계).
 *
 * 진행 단계 카드·상시 도면 업로드 카드·큰 리포트 버튼을 제거하고 화면을 거의 채팅
 * 자체로 만든다. 도면 입력은 에이전트가 대화 중 A2UI 카드로 유도한다. 리포트 링크는
 * SessionChat 내부에서 has_report 일 때 작은 텍스트 링크로만 노출한다.
 *
 * 소유권 가드(#chat-after-ownership): SessionChat 을 마운트하기 전에 getSession 으로
 * 세션 접근을 1회 확인한다 — 로딩/401·404 상태에서 채팅을 마운트하면 stale·공유 URL 로
 * 익명 유저를 만들고 남의 세션을 탐침할 수 있어 이를 막는다.
 */

import { Alert, Button, Group, Loader, Stack, Text } from '@mantine/core';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { SessionChat } from '@/components/agent/SessionChat';
import { parseApiError } from '@/lib/api/error';
import { getSession, syncExistingToken } from '@/lib/sessions/api';

// 에러를 사용자에게 노출할 의미 단위로 분류한다. 백엔드 원문 메시지("Supabase bearer
// token is required." 등)는 내부 구현(Supabase)을 드러내고 영어라 그대로 노출하지
// 않는다(#no-raw-error-leak). 소유권 가드상 404 는 "없음/권한없음"을 구분하지 않는다
// (백엔드가 열거 누수 방지로 둘 다 404 로 합침).
type ErrorKind = 'auth' | 'not_found' | 'generic';

type LoadState =
  | { id: string; state: 'ready' }
  | { id: string; state: 'error'; kind: ErrorKind };

function classifyError(err: unknown): ErrorKind {
  const status = parseApiError(err).status;
  if (status === 401) return 'auth';
  if (status === 403 || status === 404) return 'not_found';
  return 'generic';
}

export default function SessionDetailPage() {
  const params = useParams<{ sessionId: string }>();
  const sessionId = params.sessionId;
  const router = useRouter();
  // sessionId 별 로드 결과를 한 상태로 들고 있어, 동기 setState 리셋 없이도 세션이
  // 바뀌면 (load.id !== sessionId) 자동으로 로딩 상태로 떨어진다.
  const [load, setLoad] = useState<LoadState | null>(null);

  useEffect(() => {
    let ignore = false;
    void (async () => {
      try {
        await syncExistingToken();
        await getSession(sessionId);
        if (!ignore) setLoad({ id: sessionId, state: 'ready' });
      } catch (err) {
        if (!ignore) {
          setLoad({ id: sessionId, state: 'error', kind: classifyError(err) });
        }
      }
    })();
    return () => {
      ignore = true;
    };
  }, [sessionId]);

  // 현재 sessionId 의 결과만 인정한다(이전 세션 결과 무시 = 세션 전환 시 로더).
  const current = load?.id === sessionId ? load : null;

  if (current?.state === 'error') {
    if (current.kind === 'auth') {
      // 로그인 후 같은 세션으로 복귀(next= 현재 경로). 경로는 상대 path 라 open-redirect
      // 위험이 없다.
      const next = encodeURIComponent(`/sessions/${sessionId}`);
      return (
        <Stack align="center" py="xl" gap="md" maw={420} mx="auto">
          <Text fw={700} fz="lg" ta="center" style={{ wordBreak: 'keep-all' }}>
            로그인이 필요해요
          </Text>
          <Text size="sm" c="dimmed" ta="center" style={{ wordBreak: 'keep-all' }}>
            이 사전검토는 본인 계정으로 로그인해야 볼 수 있어요.
          </Text>
          <Button color="jippin" radius="md" onClick={() => router.push(`/login?next=${next}`)}>
            로그인하기
          </Button>
        </Stack>
      );
    }

    const message =
      current.kind === 'not_found'
        ? '세션을 찾을 수 없거나 접근 권한이 없어요.'
        : '세션을 불러오지 못했어요. 잠시 후 다시 시도해 주세요.';
    return (
      <Alert color="danger" variant="light" radius="md">
        {message}
      </Alert>
    );
  }

  if (current?.state !== 'ready') {
    return (
      <Group justify="center" py="xl">
        <Loader size="sm" color="jippin" />
      </Group>
    );
  }

  // key=sessionId: 세션 변경 시 remount 해 채팅 상태를 깨끗이 리셋한다.
  return <SessionChat key={sessionId} sessionId={sessionId} />;
}

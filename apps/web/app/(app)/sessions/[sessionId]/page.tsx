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

import { Alert, Group, Loader } from '@mantine/core';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';

import { SessionChat } from '@/components/agent/SessionChat';
import { parseApiError } from '@/lib/api/error';
import { getSession, syncExistingToken } from '@/lib/sessions/api';

type LoadState =
  | { id: string; state: 'ready' }
  | { id: string; state: 'error'; message: string };

export default function SessionDetailPage() {
  const params = useParams<{ sessionId: string }>();
  const sessionId = params.sessionId;
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
          setLoad({ id: sessionId, state: 'error', message: parseApiError(err).message });
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
    return (
      <Alert color="danger" variant="light" radius="md">
        {current.message}
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

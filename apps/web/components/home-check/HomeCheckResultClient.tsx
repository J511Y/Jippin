'use client';

import { Alert, Button, Card, Group, Loader, Stack, Text } from '@mantine/core';
import { IconAlertCircle } from '@tabler/icons-react';
import { useCallback, useEffect, useRef, useState } from 'react';

import { parseApiError } from '@/lib/api/error';
import { getHomeCheck, type HomeCheckJob } from '@/lib/home-check/api';
import { ensureAnonymousSession } from '@/lib/leads/ensure-anonymous-session';
import { HomeCheckNeedsInput } from './HomeCheckNeedsInput';
import { HomeCheckReportView } from './HomeCheckReportView';

/** 폴링 간격(ms). 조회는 수십초 걸릴 수 있어 과한 폴링은 피한다. */
const POLL_INTERVAL_MS = 2000;

/** 폴링을 멈춰야 하는(터미널/대기 입력) 상태. */
function isTerminal(status: HomeCheckJob['status']): boolean {
  return status === 'completed' || status === 'failed' || status === 'needs_input';
}

/**
 * 우리집 체크 결과 폴링 화면 (CMP-DIRECT, ADR-0008).
 *
 * 마운트 시 GET 으로 잡을 받아오고, pending|querying 이면 2s 간격으로 폴링한다.
 * completed → 리포트, failed → 에러, needs_input → 폴백 폼(폴링 중단)으로 분기한다.
 * 익명 세션을 보장해 apiClient 가 Bearer 를 부착하게 한다(잡 소유자 검증).
 */
export function HomeCheckResultClient({ checkId }: { checkId: string }) {
  const [job, setJob] = useState<HomeCheckJob | null>(null);
  const [fatalError, setFatalError] = useState<string | null>(null);
  // 최신 상태를 effect 내부 루프에서 읽기 위한 ref(폴링 중단 판정).
  const stoppedRef = useRef(false);

  const poll = useCallback(async () => {
    try {
      await ensureAnonymousSession();
    } catch (error) {
      setFatalError(parseApiError(error).message);
      return;
    }

    while (!stoppedRef.current) {
      try {
        const next = await getHomeCheck(checkId);
        if (stoppedRef.current) return;
        setJob(next);
        if (isTerminal(next.status)) {
          stoppedRef.current = true;
          return;
        }
      } catch (error) {
        if (stoppedRef.current) return;
        setFatalError(parseApiError(error).message);
        stoppedRef.current = true;
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    }
  }, [checkId]);

  useEffect(() => {
    stoppedRef.current = false;
    // poll 은 외부 시스템(백엔드 잡)을 구독하는 비동기 루프다 — setState 는 await 경계 너머
    // (응답 도착 시점)에서만 일어나므로 effect 바디의 동기 setState 가 아니다. 룰의 정적
    // 분석이 async 경계를 넘지 못해 오탐하므로 의도적으로 비활성화한다.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void poll();
    return () => {
      stoppedRef.current = true;
    };
  }, [poll]);

  // needs_input 폴백 제출 성공 → 갱신 잡 반영 후 비터미널이면 다시 폴링 재개.
  const handleResumed = useCallback(
    (next: HomeCheckJob) => {
      setJob(next);
      if (!isTerminal(next.status)) {
        stoppedRef.current = false;
        void poll();
      }
    },
    [poll]
  );

  if (fatalError) {
    return (
      <Alert color="red" variant="light" radius="md" icon={<IconAlertCircle size={18} />} title="조회에 실패했어요">
        <Stack gap="sm">
          <Text size="sm" style={{ wordBreak: 'keep-all' }}>
            {fatalError}
          </Text>
          <Button component="a" href="/home-check/new" variant="light" color="jippin" radius="md" w="fit-content">
            다시 시도하기
          </Button>
        </Stack>
      </Alert>
    );
  }

  // completed
  if (job?.status === 'completed' && job.report) {
    return <HomeCheckReportView report={job.report} checkId={checkId} />;
  }

  // failed
  if (job?.status === 'failed') {
    return (
      <Alert color="red" variant="light" radius="md" icon={<IconAlertCircle size={18} />} title="조회에 실패했어요">
        <Stack gap="sm">
          <Text size="sm" style={{ wordBreak: 'keep-all' }}>
            {job.error?.message ?? '건축물대장을 조회하지 못했습니다. 주소·동·호를 확인하고 다시 시도해 주세요.'}
          </Text>
          <Button component="a" href="/home-check/new" variant="light" color="jippin" radius="md" w="fit-content">
            다시 시도하기
          </Button>
        </Stack>
      </Alert>
    );
  }

  // needs_input
  if (job?.status === 'needs_input' && job.needs_input) {
    return (
      <HomeCheckNeedsInput
        checkId={checkId}
        needsInput={job.needs_input}
        onResumed={handleResumed}
      />
    );
  }

  // pending | querying | (초기 로딩)
  return (
    <Card withBorder radius="lg" padding="xl">
      <Stack align="center" gap="md" py="lg" ta="center">
        <Loader color="jippin" />
        <Group gap="xs" justify="center">
          <Text fw={600}>건축물대장을 조회하고 있어요</Text>
        </Group>
        <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
          외부 시스템(세움터) 조회는 수십 초가 걸릴 수 있어요. 화면을 닫지 말고 잠시만
          기다려 주세요. 조회가 끝나면 결과가 자동으로 표시됩니다.
        </Text>
      </Stack>
    </Card>
  );
}

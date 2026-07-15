'use client';

import { Alert, Button, Stack, Text } from '@mantine/core';
import { IconAlertCircle } from '@tabler/icons-react';
import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';

import { parseApiError } from '@/lib/api/error';
import { getHomeCheck, type HomeCheckJob } from '@/lib/home-check/api';
import { ensureAnonymousSession } from '@/lib/leads/ensure-anonymous-session';
import type { QuizItem } from '@/lib/quiz';
import { HomeCheckNeedsInput } from './HomeCheckNeedsInput';
import { HomeCheckReportView } from './HomeCheckReportView';
import { HomeCheckWaiting } from './waiting/HomeCheckWaiting';

/** 폴링 간격(ms). 조회는 보통 2~3분 걸려 과한 폴링은 피한다. */
const POLL_INTERVAL_MS = 2000;

/** 완료 비트(전 스텝 체크 + "끝났어요") 노출 시간 — 리포트 스왑 전 마무리 프레임. */
const COMPLETION_BEAT_MS = 1400;

/** 폴링을 멈춰야 하는(터미널/대기 입력) 상태. */
function isTerminal(status: HomeCheckJob['status']): boolean {
  return status === 'completed' || status === 'failed' || status === 'needs_input';
}

/**
 * 우리집 체크 결과 폴링 화면 (CMP-DIRECT, ADR-0008).
 *
 * 마운트 시 GET 으로 잡을 받아오고, pending|querying 이면 2s 간격으로 폴링한다.
 * completed → 리포트, failed → 에러, needs_input → 폴백 폼(폴링 중단)으로 분기한다.
 * 대기 중에는 실제 phase(1.3.0) 연동 스테퍼 + 집 상식 퀴즈(HomeCheckWaiting)를 보여
 * 이탈을 막는다. 익명 세션을 보장해 apiClient 가 Bearer 를 부착하게 한다(잡 소유자 검증).
 */
export function HomeCheckResultClient({
  checkId,
  quizzes = []
}: {
  checkId: string;
  /** 대기 화면 퀴즈(서버 컴포넌트가 fetchQuizzes 로 주입 — 실패 시 폴백 포함). */
  quizzes?: QuizItem[];
}) {
  const [job, setJob] = useState<HomeCheckJob | null>(null);
  const [fatalError, setFatalError] = useState<string | null>(null);
  // 최신 상태를 effect 내부 루프에서 읽기 위한 ref(폴링 중단 판정).
  const stoppedRef = useRef(false);
  // 대기 화면을 실제로 본(서버가 진행 중이라고 응답한) 세션에서만 완료 비트를 튼다 —
  // 이미 완료된 잡 재방문은 즉시 리포트.
  const [sawWaiting, setSawWaiting] = useState(false);
  const [beatDone, setBeatDone] = useState(false);

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
        // 진행 중 응답을 한 번이라도 받았으면 기록 — 완료 비트 노출 조건
        // (이미 완료된 잡 재방문은 즉시 리포트).
        if (next.status === 'pending' || next.status === 'querying') {
          setSawWaiting(true);
        }
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
        setSawWaiting(true);
        stoppedRef.current = false;
        void poll();
      }
    },
    [poll]
  );

  // 대기 화면을 보다가 완료로 전환되면 짧은 완료 비트 후 리포트로 스왑한다 —
  // 사용자 엄지 아래의 퀴즈 버튼이 순간 리포트 링크로 바뀌는 오탭을 막고,
  // 스테퍼에 마무리 프레임(전 스텝 체크)을 준다.
  useEffect(() => {
    if (job?.status === 'completed' && sawWaiting && !beatDone) {
      const timer = setTimeout(() => setBeatDone(true), COMPLETION_BEAT_MS);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [job?.status, sawWaiting, beatDone]);

  if (fatalError) {
    return (
      // 실패 알림은 Mantine 기본 red 가 아니라 정본 status 토큰(danger 팔레트)을 쓴다.
      <Alert color="danger" variant="light" radius="md" icon={<IconAlertCircle size={18} />} title="조회에 실패했어요">
        <Stack gap="sm">
          <Text size="sm" style={{ wordBreak: 'keep-all' }}>
            {fatalError}
          </Text>
          <Button component={Link} href="/home-check/new" variant="light" color="jippin" radius="md" w="fit-content">
            다시 시도하기
          </Button>
        </Stack>
      </Alert>
    );
  }

  // completed — 대기 화면을 본 세션은 짧은 완료 비트(전 스텝 체크)를 거쳐 리포트로.
  if (job?.status === 'completed' && job.report) {
    if (sawWaiting && !beatDone) {
      return (
        <HomeCheckWaiting
          done
          phase={job.phase}
          createdAt={job.created_at}
          quizItems={quizzes}
        />
      );
    }
    return <HomeCheckReportView report={job.report} checkId={checkId} />;
  }

  // failed
  if (job?.status === 'failed') {
    return (
      <Alert color="danger" variant="light" radius="md" icon={<IconAlertCircle size={18} />} title="조회에 실패했어요">
        <Stack gap="sm">
          <Text size="sm" style={{ wordBreak: 'keep-all' }}>
            {job.error?.message ?? '건축물대장을 조회하지 못했습니다. 주소·동·호를 확인하고 다시 시도해 주세요.'}
          </Text>
          <Button component={Link} href="/home-check/new" variant="light" color="jippin" radius="md" w="fit-content">
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

  // pending | querying | (초기 로딩) — 실제 phase 연동 스테퍼 + 퀴즈.
  return (
    <HomeCheckWaiting
      phase={job?.phase}
      createdAt={job?.created_at}
      quizItems={quizzes}
    />
  );
}

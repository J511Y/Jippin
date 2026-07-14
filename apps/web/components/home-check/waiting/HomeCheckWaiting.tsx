'use client';

import { Card, Stack, Text, VisuallyHidden } from '@mantine/core';
import { useEffect, useRef, useState } from 'react';

import type { QuizItem } from '@/lib/quiz';
import {
  estimateIndexFromElapsed,
  phaseToIndex,
  reassuranceCopy,
  WAIT_STEPS
} from './phases';
import { ProgressStepper } from './ProgressStepper';
import { QuizCard } from './QuizCard';

export interface HomeCheckWaitingProps {
  /** 백엔드 phase(contracts 1.3.0). 구 잡/미지 값이면 시간 추정으로 폴백한다. */
  phase?: string | null;
  /** job.created_at (ISO) — 경과 시간 앵커(새로고침 내성). 없으면 마운트 시각. */
  createdAt?: string | null;
  /** 완료 비트: 전 스텝 체크 + 완료 카피(~1.4s 후 리포트로 스왑). */
  done?: boolean;
  /** 대기 중 보여줄 퀴즈. 비어 있으면 퀴즈 카드 없이 스테퍼만. */
  quizItems?: QuizItem[];
}

/**
 * 우리집 체크 대기 화면 — 진행 스테퍼(실제 phase 연동) + 집 상식 퀴즈(삼쩜삼식 대기
 * 컨텐츠). 폴링은 호출측(HomeCheckResultClient)이 소유하고, 이 컴포넌트는 표시만 한다.
 */
export function HomeCheckWaiting({
  phase,
  createdAt,
  done = false,
  quizItems = []
}: HomeCheckWaitingProps) {
  const mountedAtRef = useRef(Date.now());
  const [now, setNow] = useState(() => Date.now());
  // 단조 가드 — 시간 추정이 앞서간 뒤 늦게 도착한 실제 phase 가 뒤라도 스테퍼를
  // 되돌리지 않는다(역행은 버그로 읽힌다). 이후 실제 phase 가 앞서면 그걸 따른다.
  const maxIndexRef = useRef(0);

  useEffect(() => {
    if (done) return;
    // 안심 문구 티어/시간 추정 갱신용 5s tick — 초 단위 정밀도가 필요 없다.
    const timer = setInterval(() => setNow(Date.now()), 5000);
    return () => clearInterval(timer);
  }, [done]);

  const startedAt = createdAt ? Date.parse(createdAt) : Number.NaN;
  // 서버-클라이언트 시계 오차로 음수가 나올 수 있어 0 으로 클램프한다.
  const elapsedMs = Math.max(
    0,
    now - (Number.isFinite(startedAt) ? startedAt : mountedAtRef.current)
  );
  const effectiveIndex = phaseToIndex(phase) ?? estimateIndexFromElapsed(elapsedMs);
  const renderedIndex = Math.min(
    Math.max(effectiveIndex, maxIndexRef.current),
    WAIT_STEPS.length - 1
  );
  maxIndexRef.current = renderedIndex;

  const currentStep = WAIT_STEPS[renderedIndex] ?? WAIT_STEPS[0]!;

  return (
    <Stack gap="md">
      <Card withBorder radius="lg" padding="xl">
        <Stack gap="md">
          <div>
            <Text component="h2" fw={700} fz="lg" m={0} style={{ wordBreak: 'keep-all' }}>
              {done ? '조회가 끝났어요!' : '건축물대장을 확인하고 있어요'}
            </Text>
            <Text size="sm" c="dimmed" mt={6} style={{ wordBreak: 'keep-all' }}>
              {done ? '리포트를 바로 보여드릴게요.' : reassuranceCopy(elapsedMs)}
            </Text>
          </div>
          <ProgressStepper steps={WAIT_STEPS} currentIndex={renderedIndex} done={done} />
          {/* 스텝 전환 공지(SR 전용) — 퍼널의 진행 공지 패턴과 동일하게 polite. */}
          <VisuallyHidden aria-live="polite">
            {done ? '조회가 완료됐어요' : `${renderedIndex + 1}단계 · ${currentStep.label}`}
          </VisuallyHidden>
        </Stack>
      </Card>

      {quizItems.length > 0 && <QuizCard items={quizItems} />}
    </Stack>
  );
}

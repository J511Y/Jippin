'use client';

import { IconCheck } from '@tabler/icons-react';

import type { WaitStep } from './phases';

/**
 * 대기 화면 세로 진행 스테퍼 — 표시 전용(타이머·상태 없음, resolved index 만 받는다).
 * 스타일은 globals.css 의 `.hc-wait-*` 블록(브랜드 토큰·reduced-motion 게이트).
 */
export function ProgressStepper({
  steps,
  currentIndex,
  done = false
}: {
  steps: readonly WaitStep[];
  /** 0-base 현재 스텝. 호출측(HomeCheckWaiting)이 단조 가드를 적용해 넘긴다. */
  currentIndex: number;
  /** true 면 전 스텝 체크(완료 비트). */
  done?: boolean;
}) {
  return (
    <ol className="hc-wait-stepper" aria-label="조회 진행 단계">
      {steps.map((step, i) => {
        const state = done || i < currentIndex ? 'done' : i === currentIndex ? 'current' : 'todo';
        return (
          <li
            key={step.key}
            className="hc-wait-step"
            data-state={state}
            aria-current={!done && i === currentIndex ? 'step' : undefined}
          >
            <span className="hc-wait-step__bullet" aria-hidden="true">
              {state === 'done' ? <IconCheck size={15} stroke={3} /> : i + 1}
            </span>
            <span className="hc-wait-step__text">
              <span className="hc-wait-step__label">{step.label}</span>
              <span className="hc-wait-step__desc">{step.description}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

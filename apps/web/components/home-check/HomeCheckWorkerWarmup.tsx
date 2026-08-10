'use client';

import { useEffect } from 'react';

import { warmHomeCheckWorker } from '@/lib/home-check/api';

/**
 * 화면에는 아무것도 그리지 않고 우리집 체크 worker를 best-effort로 준비한다.
 * 랜딩에서 시작해 사용자가 안내를 읽고 주소를 입력하는 동안 cold-start+로그인을 숨긴다.
 */
export function HomeCheckWorkerWarmup({ disabled = false }: { disabled?: boolean }) {
  useEffect(() => {
    if (disabled) return;

    void warmHomeCheckWorker().catch(() => {
      // UX 최적화 경로다. 실패해도 실제 제출 직전 API readiness 가 다시 준비를 시도한다.
    });
  }, [disabled]);

  return null;
}

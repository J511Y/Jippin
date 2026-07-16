'use client';

import { useEffect } from 'react';

/**
 * 격자 캔버스 패럴랙스 (DESIGN.md §4.9) — 제도 격자가 콘텐츠보다 약하게(≈1/5 속도)
 * 스크롤을 따라 움직여 2.5D 깊이감을 준다. 완전 고정(0×)은 콘텐츠와 유리되어
 * 어색하고, 1:1 동기는 벽지처럼 밋밋하다는 피드백의 절충.
 *
 * documentElement 의 CSS 변수(--jippin-grid-scroll)만 갱신하고, 실제 이동은
 * globals.css 의 body::before background-position 이 소비한다 — 마이너 격자는
 * 1.0×, 메이저 격자는 0.5× 배율로 서로 다른 평면처럼 움직인다(격자 2겹 깊이).
 *
 * - rAF 스로틀 + passive 리스너로 스크롤 성능 영향 최소화.
 * - prefers-reduced-motion 사용자는 효과 없음(고정 유지).
 * - 채팅처럼 내부 컨테이너가 스크롤하는 화면은 window 스크롤이 없어 자연히 정지.
 */
const SPEED = 0.22;

export function GridParallax() {
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      return undefined;
    }

    const root = document.documentElement;
    let raf = 0;

    const update = () => {
      raf = 0;
      root.style.setProperty(
        '--jippin-grid-scroll',
        `${-(window.scrollY * SPEED)}px`
      );
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(update);
    };

    update();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', onScroll);
      if (raf) cancelAnimationFrame(raf);
      root.style.removeProperty('--jippin-grid-scroll');
    };
  }, []);

  return null;
}

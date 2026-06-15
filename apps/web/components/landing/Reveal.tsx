'use client';

import { useIsomorphicEffect } from '@mantine/hooks';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { useRef, type CSSProperties, type ReactNode } from 'react';

if (typeof window !== 'undefined') {
  gsap.registerPlugin(ScrollTrigger);
}

type RevealProps = {
  children: ReactNode;
  /**
   * 마운트 즉시 재생. 어보브 더 폴드(히어로)용. 미지정 시 뷰포트 진입 시 1회 재생.
   */
  immediate?: boolean;
  /** stagger 대상 셀렉터. 매칭이 없으면 래퍼 직계 자식을 대상으로 한다. */
  itemSelector?: string;
  /** 진입 시 아래에서 올라오는 거리(px). */
  y?: number;
  stagger?: number;
  delay?: number;
  style?: CSSProperties;
};

/**
 * 서버 컴포넌트가 렌더한 children 을 그대로 받아, 클라이언트에서 DOM 노드만 진입 모션으로
 * 드러내는 래퍼. 마크업에 초기 opacity 를 박지 않으므로 JS·모션이 없어도 콘텐츠는 항상 보인다
 * (점진적 향상). `prefers-reduced-motion: reduce` 사용자는 모션을 전부 건너뛴다.
 */
export function Reveal({
  children,
  immediate = false,
  itemSelector = '[data-reveal]',
  y = 24,
  stagger = 0.12,
  delay = 0,
  style
}: RevealProps) {
  const scope = useRef<HTMLDivElement>(null);

  useIsomorphicEffect(() => {
    const root = scope.current;
    if (!root) return;

    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      return; // 모션 최소화 사용자: 콘텐츠는 기본 상태(보임)로 둔다.
    }

    const matched = root.querySelectorAll(itemSelector);
    const targets = matched.length ? Array.from(matched) : Array.from(root.children);
    if (!targets.length) return;

    const ctx = gsap.context(() => {
      // 레이아웃 이펙트(페인트 전)에서 숨겨 깜빡임을 막는다.
      gsap.set(targets, { opacity: 0, y });
      gsap.to(targets, {
        opacity: 1,
        y: 0,
        duration: 0.7,
        ease: 'power2.out',
        stagger,
        delay,
        ...(immediate
          ? {}
          : { scrollTrigger: { trigger: root, start: 'top 82%', once: true } })
      });
    }, scope);

    return () => ctx.revert();
  }, [immediate, itemSelector, y, stagger, delay]);

  return (
    <div ref={scope} className="reveal-scope" style={style}>
      {children}
    </div>
  );
}

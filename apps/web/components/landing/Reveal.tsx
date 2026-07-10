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
      if (immediate) {
        // 어보브 더 폴드(히어로): 레이아웃 이펙트(페인트 전)에서 숨긴 뒤 즉시 재생.
        gsap.set(targets, { opacity: 0, y });
        gsap.to(targets, {
          opacity: 1,
          y: 0,
          duration: 0.55,
          ease: 'power2.out',
          stagger,
          delay
        });
        return;
      }

      // 새로고침·중간 진입으로 이미 뷰포트에 들어와 있는 요소는 숨기지 않고 즉시
      // 보여준다 — 스크롤 중 콘텐츠가 반투명으로 걸려 보이는 FOUC(실화면 확인) 방지.
      // (globals.css 가 paint 전에 [data-reveal] 을 opacity 0 으로 숨겨 두므로,
      //  인라인 opacity 1 로 되돌려야 한다.)
      const viewportBottom = window.innerHeight * 0.92;
      const inView = targets.filter(
        (el) => el.getBoundingClientRect().top < viewportBottom
      );
      const pending = targets.filter((el) => !inView.includes(el));

      if (inView.length) gsap.set(inView, { opacity: 1, y: 0 });
      if (!pending.length) return;

      gsap.set(pending, { opacity: 0, y });
      gsap.to(pending, {
        opacity: 1,
        y: 0,
        duration: 0.55,
        ease: 'power2.out',
        stagger,
        delay,
        // 첫 미노출 요소 기준으로 시작점을 이르게(top 88%) 잡아, 보이는 위치에서
        // 뒤늦게 올라오는 느낌을 줄인다.
        scrollTrigger: { trigger: pending[0] as Element, start: 'top 88%', once: true }
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

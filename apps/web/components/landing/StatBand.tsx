'use client';

import { Box, SimpleGrid, Stack, Text } from '@mantine/core';
import { useIsomorphicEffect } from '@mantine/hooks';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { useRef } from 'react';

if (typeof window !== 'undefined') {
  gsap.registerPlugin(ScrollTrigger);
}

type Stat = { value: string; label: string };

const STATS: Stat[] = [
  { value: '20년+', label: '업력 (2007~)' },
  { value: '25,000+', label: '누적 건수' },
  { value: '1분', label: 'AI 사전검토 완료' }
];

/** '25,000+' → { num: 25000, suffix: '+' }. 숫자가 없으면 num: null. */
function parseStat(value: string): { num: number | null; suffix: string } {
  const match = value.match(/^([\d,]+)(.*)$/);
  if (!match) return { num: null, suffix: value };
  return { num: Number(match[1]!.replace(/,/g, '')), suffix: match[2] ?? '' };
}

/**
 * 신뢰 앵커 스탯 밴드. 뷰포트에 들어오면 숫자를 0 → 목표값으로 카운트업한다.
 * 목적이 분명한 모션 한 곳만 — `prefers-reduced-motion` 사용자에겐 최종값을 즉시 보여준다.
 */
export function StatBand() {
  const scope = useRef<HTMLDivElement>(null);

  useIsomorphicEffect(() => {
    const root = scope.current;
    if (!root) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const nodes = root.querySelectorAll<HTMLElement>('[data-counter]');

    const ctx = gsap.context(() => {
      nodes.forEach((node) => {
        const num = Number(node.dataset.num);
        const suffix = node.dataset.suffix ?? '';
        if (!Number.isFinite(num)) return;

        const state = { value: 0 };
        gsap.to(state, {
          value: num,
          duration: 1.4,
          ease: 'power2.out',
          scrollTrigger: { trigger: root, start: 'top 80%', once: true },
          onUpdate: () => {
            node.textContent = `${Math.round(state.value).toLocaleString('ko-KR')}${suffix}`;
          }
        });
      });
    }, scope);

    return () => ctx.revert();
  }, []);

  return (
    <Box
      ref={scope}
      mb="xl"
      p="xl"
      style={{
        borderRadius: 'var(--mantine-radius-lg)',
        background:
          'linear-gradient(135deg, #0F5F59 0%, #147A73 60%, #2D8F87 100%)'
      }}
    >
      <SimpleGrid cols={3} spacing="md">
        {STATS.map((s) => {
          const { num, suffix } = parseStat(s.value);
          return (
            <Stack key={s.label} gap={2} align="center" ta="center">
              <Text
                fw={800}
                c="#FFFFFF"
                {...(num !== null
                  ? { 'data-counter': true, 'data-num': num, 'data-suffix': suffix }
                  : {})}
                style={{
                  fontSize: 'clamp(1.5rem, 4.5vw, 2.5rem)',
                  lineHeight: 1.1,
                  letterSpacing: '-0.02em',
                  fontVariantNumeric: 'tabular-nums'
                }}
              >
                {s.value}
              </Text>
              <Text
                size="sm"
                style={{ color: 'rgba(255,255,255,0.85)', wordBreak: 'keep-all' }}
              >
                {s.label}
              </Text>
            </Stack>
          );
        })}
      </SimpleGrid>
    </Box>
  );
}

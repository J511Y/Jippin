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
        // 단색 딥 틸 — COLOR_SYSTEM 은 그라데이션을 금지한다. 흰 캔버스 위에서
        // 확실한 구획이 되는 신뢰 앵커 밴드.
        background: 'var(--mantine-color-jippin-7)'
      }}
    >
      {/* 모바일(48em 미만)은 1열 스택 — 3열 고정 시 숫자가 접혀 읽기 어렵다. */}
      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md" verticalSpacing="lg">
        {STATS.map((s) => {
          const { num, suffix } = parseStat(s.value);
          return (
            <Stack key={s.label} gap={2} align="center" ta="center">
              <Text
                fw={700}
                c="var(--jippin-brand-primary-fg)"
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

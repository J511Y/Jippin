import { Stack, Text, Title } from '@mantine/core';
import type { ReactNode } from 'react';

/**
 * 페이지 헤더 표준 블록 — 타이틀(h1) + 부제의 크기·간격 SSOT.
 *
 * 페이지마다 타이틀 크기(20/22/24/28px)와 헤더 리듬(gap 4~xs)이 갈라지던 것을
 * 이 블록으로 수렴한다. 크기는 theme headings h1 토큰을 그대로 쓴다 — 개별
 * 페이지에서 fz 오버라이드 금지 (TYPOGRAPHY.md §2).
 */
export function PageHeader({
  title,
  subtitle,
  actions
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  /** 타이틀 우측 정렬 액션(선택) — 목록 페이지의 보조 버튼 등 */
  actions?: ReactNode;
}) {
  return (
    <Stack gap={6} mb="xl">
      {actions ? (
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: 16,
            flexWrap: 'wrap'
          }}
        >
          <Title order={1}>{title}</Title>
          {actions}
        </div>
      ) : (
        <Title order={1}>{title}</Title>
      )}
      {subtitle ? (
        <Text c="dimmed" maw={640} style={{ wordBreak: 'keep-all' }}>
          {subtitle}
        </Text>
      ) : null}
    </Stack>
  );
}

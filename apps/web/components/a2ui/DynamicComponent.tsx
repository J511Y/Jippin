'use client';

import { Code, Paper, Stack, Text } from '@mantine/core';
import type { DynamicComponentSpec } from '@/components/a2ui/types';

/**
 * A2UI 동적 컴포넌트 렌더러 (placeholder).
 *
 * - 현재는 미등록 컴포넌트와 동일하게 spec을 그대로 보여주는 fallback만 구현.
 * - 본 컴포넌트의 정본 책임은 `kind` 키를 클라이언트 컴포넌트 레지스트리로 매핑하여
 *   서버(LLM)가 결정한 위젯(예: `floorplan-confirm`, `rule-conflict`, `estimate-card`)
 *   을 안전하게 렌더하는 것이다.
 * - 레지스트리·런타임 검증은 SDD §6.2 / 후속 CHAT 이슈에서 확정.
 */

type Props = {
  spec: DynamicComponentSpec;
};

export function DynamicComponent({ spec }: Props) {
  return (
    <Paper
      role="figure"
      aria-label={`동적 컴포넌트: ${spec.kind}`}
      bg="white"
      p="sm"
      radius="md"
      style={{
        border: '1px dashed var(--jippin-brand-border)'
      }}
    >
      <Stack gap={4}>
        <Text c="var(--jippin-brand-copy)" fw={600} size="xs">
          [A2UI:{spec.kind}]
        </Text>
        <Code block c="dimmed" fz="xs">
          {JSON.stringify(spec.payload, null, 2)}
        </Code>
      </Stack>
    </Paper>
  );
}

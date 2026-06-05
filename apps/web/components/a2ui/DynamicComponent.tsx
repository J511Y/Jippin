'use client';

import { Badge, Code, Group, Paper, Stack, Text } from '@mantine/core';
import { IconLayoutDashboard } from '@tabler/icons-react';
import type { ReactNode } from 'react';
import type { DynamicComponentSpec } from '@/components/a2ui/types';

/**
 * A2UI 동적 컴포넌트 렌더러 (placeholder).
 *
 * - 본 컴포넌트의 정본 책임은 `kind` 키를 클라이언트 컴포넌트 레지스트리로 매핑하여
 *   서버(LLM)가 결정한 위젯(예: `floorplan-confirm`, `rule-conflict`, `estimate-card`)
 *   을 안전하게 렌더하는 것이다.
 * - 디자인 QA (2026-06-05): 사람이 읽는 화면에 raw JSON 을 그대로 노출하지 않는다.
 *   `kind` 별 친화적 view 를 우선 렌더하고, 미등록 `kind` 만 JSON fallback 으로 떨어뜨린다.
 * - 레지스트리·런타임 검증은 SDD §6.2 / 후속 CHAT 이슈에서 확정.
 */

type Props = {
  spec: DynamicComponentSpec;
};

type FloorplanConfirmPayload = {
  selectedRegionId?: string;
  confidence?: number;
};

function formatConfidence(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/**
 * Codex P2 (2026-06-05): payload 가 LLM/서버에서 오므로 런타임 형태가 임의일 수 있다.
 * `selectedRegionId` 가 객체·배열·null 일 때 React 가 throw 하지 않도록 type guard 로 검증한다.
 * 검증 실패 시 registry 가 `null` 을 반환하고, 호출 측에서 JSON fallback 으로 떨어뜨린다.
 */
function isFloorplanConfirmPayload(payload: Record<string, unknown>): payload is FloorplanConfirmPayload {
  const idOk = payload.selectedRegionId === undefined || typeof payload.selectedRegionId === 'string';
  const confidenceOk = payload.confidence === undefined || typeof payload.confidence === 'number';
  return idOk && confidenceOk;
}

function FloorplanConfirmCard({ payload }: { payload: FloorplanConfirmPayload }) {
  return (
    <Stack gap={6}>
      <Group gap="xs">
        <IconLayoutDashboard size={16} aria-hidden style={{ color: 'var(--jippin-brand-professional)' }} />
        <Text fw={600} size="sm">도면 후보 영역 확인</Text>
      </Group>
      {payload.selectedRegionId ? (
        <Text c="var(--jippin-brand-copy)" size="sm">
          선택 영역: <Text component="span" fw={600}>{payload.selectedRegionId}</Text>
        </Text>
      ) : null}
      {typeof payload.confidence === 'number' ? (
        <Group gap="xs">
          <Text c="var(--jippin-brand-copy)" size="sm">분석 신뢰도</Text>
          <Badge color="blueprint" variant="light">{formatConfidence(payload.confidence)}</Badge>
        </Group>
      ) : null}
    </Stack>
  );
}

/**
 * 동적 컴포넌트 레지스트리. `kind` 별 친화적 view 를 매핑한다.
 * 미등록 키 또는 payload 형태가 어긋난 경우 `null` 을 반환하고, 호출 측이 JSON fallback 으로 떨어뜨려
 * 디버깅 가시성을 유지하면서도 잘못된 입력으로 화면이 죽지 않도록 한다.
 */
const registry: Record<string, (payload: Record<string, unknown>) => ReactNode | null> = {
  'floorplan-confirm': (payload) =>
    isFloorplanConfirmPayload(payload) ? <FloorplanConfirmCard payload={payload} /> : null
};

function FallbackJson({ spec }: { spec: DynamicComponentSpec }) {
  return (
    <Stack gap={4}>
      <Text c="var(--jippin-brand-copy)" fw={600} size="xs">
        [A2UI:{spec.kind}]
      </Text>
      <Code block c="dimmed" fz="xs">
        {JSON.stringify(spec.payload, null, 2)}
      </Code>
    </Stack>
  );
}

export function DynamicComponent({ spec }: Props) {
  const renderer = registry[spec.kind];
  // renderer 가 null 을 반환하면 (payload 형태 mismatch) JSON fallback 으로 떨어진다.
  const rendered = renderer ? renderer(spec.payload) : null;

  return (
    <Paper
      role="figure"
      aria-label={`동적 컴포넌트: ${spec.kind}`}
      bg="var(--jippin-brand-surface-alt, #FFFFFF)"
      p="sm"
      radius="md"
      style={{
        border: '1px solid var(--jippin-brand-border)'
      }}
    >
      {rendered ?? <FallbackJson spec={spec} />}
    </Paper>
  );
}

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
  /**
   * 0~1 사이 신뢰도. 백엔드 `floorplans.py` 스키마가 `Decimal` 이라 JSON 직렬화 시
   * 문자열("0.91") 로도 전달될 수 있어 number | string 둘 다 허용한다.
   */
  confidence?: number | string;
};

/**
 * `confidence` 는 0~1 사이 확률값. 범위를 벗어나면 (예: 91 또는 1.2) `9100%`/`120%` 같은
 * 의미없는 값이 화면에 노출되므로 reject 한다. 검증 실패는 null 로 반환해 JSON fallback
 * 으로 떨어뜨려 디버깅 가시성을 유지한다.
 */
function coerceConfidence(value: unknown): number | null {
  let n: number | null = null;
  if (typeof value === 'number') {
    n = value;
  } else if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      n = parsed;
    }
  }
  if (n === null || !Number.isFinite(n) || n < 0 || n > 1) {
    return null;
  }
  return n;
}

function formatConfidence(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/**
 * Codex P2 (2026-06-05): payload 가 LLM/서버에서 오므로 런타임 형태가 임의일 수 있다.
 * - `payload` 자체가 null·undefined·array·primitive 일 수 있으니 *object* 인지 먼저 좁힌다.
 * - 그 다음 각 필드 (`selectedRegionId` / `confidence`) 의 타입을 개별 검증한다.
 * - `confidence` 는 백엔드 Decimal 직렬화로 문자열도 올 수 있어 숫자형 문자열은
 *   유효한 값으로 인정한다 (apps/api/src/schemas/floorplans.py 참고).
 * 검증 실패 시 registry 가 `null` 을 반환하고, 호출 측에서 JSON fallback 으로 떨어뜨린다.
 */
function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isFloorplanConfirmPayload(payload: unknown): payload is FloorplanConfirmPayload {
  if (!isPlainObject(payload)) {
    return false;
  }
  const hasId = typeof payload.selectedRegionId === 'string' && payload.selectedRegionId.length > 0;
  const hasConfidence = payload.confidence !== undefined && coerceConfidence(payload.confidence) !== null;
  // 두 필드 모두 optional 이지만, *유효한 필드가 하나도 없다면* 친화적 카드가 보여줄
  // 내용이 없다. 이런 경우 JSON fallback 으로 떨어뜨려 디버깅 가시성을 유지한다.
  if (!hasId && !hasConfidence) {
    return false;
  }
  // 존재하는 필드는 각각 형태 검증.
  const idOk = payload.selectedRegionId === undefined || typeof payload.selectedRegionId === 'string';
  const confidenceOk = payload.confidence === undefined || coerceConfidence(payload.confidence) !== null;
  return idOk && confidenceOk;
}

function FloorplanConfirmCard({ payload }: { payload: FloorplanConfirmPayload }) {
  const confidence = coerceConfidence(payload.confidence);
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
      {confidence !== null ? (
        <Group gap="xs">
          <Text c="var(--jippin-brand-copy)" size="sm">분석 신뢰도</Text>
          <Badge color="blueprint" variant="light">{formatConfidence(confidence)}</Badge>
        </Group>
      ) : null}
    </Stack>
  );
}

/**
 * 동적 컴포넌트 레지스트리. `kind` 별 친화적 view 를 매핑한다.
 * 미등록 키 또는 payload 형태가 어긋난 경우 `null` 을 반환하고, 호출 측이 JSON fallback 으로 떨어뜨려
 * 디버깅 가시성을 유지하면서도 잘못된 입력으로 화면이 죽지 않도록 한다.
 *
 * Codex P2 (2026-06-05): 일반 `Record` 는 prototype chain 을 통해 `__proto__`,
 * `constructor` 등이 truthy 로 잡혀 prototype pollution 으로 임의 함수가 호출될
 * 수 있다. null-prototype object 로 정의해 own property 만 lookup 되도록 한다.
 */
type Renderer = (payload: unknown) => ReactNode | null;
const registry: Record<string, Renderer> = Object.assign(Object.create(null) as Record<string, Renderer>, {
  'floorplan-confirm': (payload: unknown) =>
    isFloorplanConfirmPayload(payload) ? <FloorplanConfirmCard payload={payload} /> : null
});

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
  // Codex P2: `Object.hasOwn` 으로 own-property 만 인정한다. registry 는 null-prototype 이라
  // 이중 보호이지만, 후속 코드에서 prototype 객체로 바뀌어도 안전하도록 hasOwn 도 함께 둔다.
  const renderer = Object.hasOwn(registry, spec.kind) ? registry[spec.kind] : undefined;
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

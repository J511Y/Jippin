'use client';

/**
 * A2UI `FloorplanConfirm` 카드 — 도면 세그멘테이션 후보 영역 + 분석 신뢰도.
 *
 * json-render 카탈로그의 렌더러로 쓰인다(props 는 카탈로그 Zod 로 1차 검증됨). 백엔드
 * `floorplans.py` 가 confidence 를 Decimal 로 직렬화해 문자열("0.91")로도 올 수 있어
 * number|string 둘 다 허용하고 0~1 범위만 신뢰도로 인정한다.
 */

import { Badge, Group, Progress, Stack, Text } from '@mantine/core';
import { IconLayoutDashboard } from '@tabler/icons-react';

export type FloorplanConfirmPayload = {
  selectedRegionId?: string;
  confidence?: number | string;
};

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** 0~1 범위 확률만 인정. 범위 밖(예: 91, 1.2)이면 null → 신뢰도 미표시. */
export function coerceConfidence(value: unknown): number | null {
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

/** 신뢰도 구간별 상태색 — 높음(success)/중간(warning)/낮음(danger). */
function confidenceColor(value: number): string {
  if (value >= 0.75) return 'success';
  if (value >= 0.5) return 'warning';
  return 'danger';
}

export function isFloorplanConfirmPayload(payload: unknown): payload is FloorplanConfirmPayload {
  if (!isPlainObject(payload)) return false;
  const hasId =
    typeof payload.selectedRegionId === 'string' && payload.selectedRegionId.length > 0;
  const hasConfidence =
    payload.confidence !== undefined && coerceConfidence(payload.confidence) !== null;
  if (!hasId && !hasConfidence) return false;
  const idOk =
    payload.selectedRegionId === undefined || typeof payload.selectedRegionId === 'string';
  const confidenceOk =
    payload.confidence === undefined || coerceConfidence(payload.confidence) !== null;
  return idOk && confidenceOk;
}

export function FloorplanConfirmCard({ payload }: { payload: FloorplanConfirmPayload }) {
  const confidence = coerceConfidence(payload.confidence);
  const color = confidence !== null ? confidenceColor(confidence) : 'blueprint';
  return (
    <Stack gap="xs">
      <Group gap="xs" wrap="nowrap">
        <IconLayoutDashboard
          size={18}
          aria-hidden
          style={{ color: 'var(--jippin-brand-professional)', flexShrink: 0 }}
        />
        <Text fw={600} size="sm" c="var(--jippin-brand-ink)">
          도면 후보 영역 확인
        </Text>
      </Group>
      {payload.selectedRegionId ? (
        <Text c="var(--jippin-brand-copy)" size="sm">
          선택 영역:{' '}
          <Text component="span" fw={600} c="var(--jippin-brand-ink)">
            {payload.selectedRegionId}
          </Text>
        </Text>
      ) : null}
      {confidence !== null ? (
        <Stack gap={4}>
          <Group gap="xs" justify="space-between">
            <Text c="var(--jippin-brand-copy)" size="sm">
              분석 신뢰도
            </Text>
            <Badge color={color} variant="light">
              {formatConfidence(confidence)}
            </Badge>
          </Group>
          <Progress
            value={Math.round(confidence * 100)}
            color={color}
            radius="xl"
            size="sm"
            aria-label="분석 신뢰도"
          />
        </Stack>
      ) : null}
    </Stack>
  );
}

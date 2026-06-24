'use client';

/**
 * A2UI `FloorplanConfirm` 카드 — 도면 세그멘테이션 후보 영역 + 분석 신뢰도.
 *
 * json-render 카탈로그의 렌더러로 쓰인다(props 는 카탈로그 Zod 로 1차 검증됨). 백엔드
 * `floorplans.py` 가 confidence 를 Decimal 로 직렬화해 문자열("0.91")로도 올 수 있어
 * number|string 둘 다 허용하고 0~1 범위만 신뢰도로 인정한다.
 */

import { Group, Progress, Stack, Text } from '@mantine/core';
import { IconLayoutDashboard } from '@tabler/icons-react';
import { useId } from 'react';

import { type CardAccent, CardHeader, CardRule, CardShell } from './CardShell';

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
function confidenceColor(value: number): 'success' | 'warning' | 'danger' {
  if (value >= 0.75) return 'success';
  if (value >= 0.5) return 'warning';
  return 'danger';
}

/** 신뢰도 구간별 한 줄 해설 — 숫자만 던지지 않고 의미를 생활어로 보탠다. */
function confidenceLabel(value: number): string {
  if (value >= 0.75) return '높음 · 후보 영역이 비교적 또렷합니다';
  if (value >= 0.5) return '보통 · 추가 확인이 도움이 됩니다';
  return '낮음 · 도면을 한 장 더 올리면 정확해집니다';
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
  const color: CardAccent =
    confidence !== null ? confidenceColor(confidence) : 'blueprint';
  const titleId = useId();
  return (
    <CardShell accent={color} labelledBy={titleId}>
      <CardHeader
        icon={<IconLayoutDashboard size={17} aria-hidden />}
        eyebrow="도면 분석"
        title="후보 영역을 확인했어요"
        titleId={titleId}
      />

      <CardRule />

      {payload.selectedRegionId ? (
        <Group gap={8} wrap="nowrap" align="center" mb={confidence !== null ? 'sm' : 0}>
          <Text className="a2ui-meta">선택 영역</Text>
          <Text
            size="sm"
            fw={600}
            c="var(--jippin-brand-ink)"
            style={{ fontVariantNumeric: 'tabular-nums' }}
          >
            {payload.selectedRegionId}
          </Text>
        </Group>
      ) : null}

      {confidence !== null ? (
        <Stack gap={6}>
          <Group gap="xs" justify="space-between" align="baseline" wrap="nowrap">
            <Text size="sm" c="var(--jippin-brand-copy)">
              분석 신뢰도
            </Text>
            <Text
              size="md"
              fw={700}
              c={`var(--mantine-color-${color}-7)`}
              style={{ fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}
            >
              {formatConfidence(confidence)}
            </Text>
          </Group>
          <Progress
            value={Math.round(confidence * 100)}
            color={color}
            radius="xl"
            size="md"
            aria-label={`분석 신뢰도 ${formatConfidence(confidence)}`}
          />
          <Text className="a2ui-meta">{confidenceLabel(confidence)}</Text>
        </Stack>
      ) : null}
    </CardShell>
  );
}

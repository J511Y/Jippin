'use client';

/**
 * A2UI `judgment-summary` 카드 — 최종 판단 결과 (CMP-DIRECT).
 *
 * 에이전트가 최종 판단을 정리해 보여 줄 때 방출한다. decision 별 상태색/아이콘으로
 * 결론 배지를 두고 title·summary·risks 를 신뢰감 있게 렌더한다.
 *
 * payload: { decision: 'possible'|'conditional'|'not_possible'|'needs_expert';
 *            title: string; summary: string; risks?: string[] }
 *
 * 법적 단정 톤 회피: 결론 라벨은 "가능/조건부/어려움/전문가 확인 권장" 등 보조적
 * 안내 느낌으로 둔다. 알 수 없는 decision 은 'needs_expert' 로 안전 폴백.
 *
 * 보안/검증: payload 가 객체이고 decision/title/summary 가 string 인지 검증한다.
 * risks 는 string 배열일 때만 채택. 형태가 어긋나면 null 반환 → JSON fallback.
 */

import { Alert, Badge, Group, List, Stack, Text } from '@mantine/core';
import {
  IconAlertTriangle,
  IconCircleCheck,
  IconCircleX,
  IconInfoCircle,
  IconUserSearch
} from '@tabler/icons-react';
import type { ReactNode } from 'react';

export type JudgmentDecision =
  | 'possible'
  | 'conditional'
  | 'not_possible'
  | 'needs_expert';

export type JudgmentSummaryPayload = {
  decision: JudgmentDecision;
  title: string;
  summary: string;
  risks?: string[];
};

const KNOWN_DECISIONS: readonly JudgmentDecision[] = [
  'possible',
  'conditional',
  'not_possible',
  'needs_expert'
];

type DecisionStyle = {
  /** Mantine color name (브랜드 토큰 기반 팔레트). */
  color: string;
  label: string;
  icon: ReactNode;
};

const DECISION_STYLES: Record<JudgmentDecision, DecisionStyle> = {
  possible: {
    color: 'success',
    label: '가능',
    icon: <IconCircleCheck size={16} />
  },
  conditional: {
    color: 'warning',
    label: '조건부 가능',
    icon: <IconInfoCircle size={16} />
  },
  not_possible: {
    color: 'danger',
    label: '어려움',
    icon: <IconCircleX size={16} />
  },
  needs_expert: {
    color: 'blueprint',
    label: '전문가 확인 권장',
    icon: <IconUserSearch size={16} />
  }
};

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function isJudgmentSummaryPayload(
  payload: unknown
): payload is JudgmentSummaryPayload {
  if (!isPlainObject(payload)) {
    return false;
  }
  if (typeof payload.decision !== 'string') {
    return false;
  }
  if (typeof payload.title !== 'string' || payload.title.length === 0) {
    return false;
  }
  if (typeof payload.summary !== 'string' || payload.summary.length === 0) {
    return false;
  }
  if (
    payload.risks !== undefined &&
    !(
      Array.isArray(payload.risks) &&
      payload.risks.every((r) => typeof r === 'string')
    )
  ) {
    return false;
  }
  return true;
}

/** 알 수 없는 decision 은 안전하게 needs_expert 로 폴백한다. */
function normalizeDecision(value: string): JudgmentDecision {
  return (KNOWN_DECISIONS as readonly string[]).includes(value)
    ? (value as JudgmentDecision)
    : 'needs_expert';
}

export function JudgmentSummaryCard({
  payload
}: {
  payload: JudgmentSummaryPayload;
}) {
  const decision = normalizeDecision(payload.decision);
  const style = DECISION_STYLES[decision];
  const risks = (payload.risks ?? []).filter((r) => r.trim().length > 0);

  return (
    <Stack gap="sm">
      <Group gap="xs" wrap="nowrap">
        <Badge
          color={style.color}
          variant="light"
          size="lg"
          leftSection={style.icon}
        >
          {style.label}
        </Badge>
      </Group>

      <Text fw={700} size="md" c="var(--jippin-brand-ink)">
        {payload.title}
      </Text>

      <Text size="sm" c="var(--jippin-brand-copy)" style={{ lineHeight: 1.6 }}>
        {payload.summary}
      </Text>

      {risks.length > 0 ? (
        <Alert
          color="warning"
          variant="light"
          icon={<IconAlertTriangle size={16} />}
          title="확인이 필요한 점"
          p="sm"
        >
          <List size="sm" spacing={4} c="var(--jippin-brand-copy)">
            {risks.map((risk, index) => (
              <List.Item key={index}>{risk}</List.Item>
            ))}
          </List>
        </Alert>
      ) : null}

      <Text size="xs" c="var(--jippin-notice-legal)" style={{ lineHeight: 1.5 }}>
        본 결과는 첨부 자료를 바탕으로 한 참고용 안내이며, 법적 판단을 대체하지
        않습니다. 정확한 확인은 전문가와 상담해 주세요.
      </Text>
    </Stack>
  );
}

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

import { Stack, Text } from '@mantine/core';
import {
  IconCircleCheck,
  IconCircleX,
  IconInfoCircle,
  IconScale,
  IconUserSearch
} from '@tabler/icons-react';
import { useId, type CSSProperties, type ReactNode } from 'react';

import { type CardAccent, CardHeader, CardRule, CardShell } from './CardShell';

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
  /** 카드 강조색 축(CardShell accent) — 좌측 레일·헤더 아이콘 칩 색. */
  accent: CardAccent;
  /** 결론 라벨(생활어·보조적 안내 톤). */
  label: string;
  icon: ReactNode;
  /** verdict 배너 색 — globals.css `.a2ui-verdict` 가 읽는 CSS 변수. 전부 토큰. */
  verdictVars: VerdictVars;
};

type VerdictVars = CSSProperties & {
  '--a2ui-verdict-surface': string;
  '--a2ui-verdict-border': string;
  '--a2ui-verdict-fg': string;
};

/** 상태별 verdict 배너 색 묶음 — surface(옅은 면)/border/foreground(라벨·아이콘). */
function verdictVars(tone: 'success' | 'warning' | 'danger' | 'blueprint'): VerdictVars {
  return {
    '--a2ui-verdict-surface': `var(--mantine-color-${tone}-0)`,
    '--a2ui-verdict-border': `var(--mantine-color-${tone}-2)`,
    '--a2ui-verdict-fg': `var(--mantine-color-${tone}-${tone === 'blueprint' ? 6 : 7})`
  };
}

const DECISION_STYLES: Record<JudgmentDecision, DecisionStyle> = {
  possible: {
    accent: 'success',
    label: '가능성 있음',
    icon: <IconCircleCheck size={18} aria-hidden />,
    verdictVars: verdictVars('success')
  },
  conditional: {
    accent: 'warning',
    label: '조건부 가능',
    icon: <IconInfoCircle size={18} aria-hidden />,
    verdictVars: verdictVars('warning')
  },
  not_possible: {
    accent: 'danger',
    label: '어려움',
    icon: <IconCircleX size={18} aria-hidden />,
    verdictVars: verdictVars('danger')
  },
  needs_expert: {
    accent: 'blueprint',
    label: '전문가 확인 권장',
    icon: <IconUserSearch size={18} aria-hidden />,
    verdictVars: verdictVars('blueprint')
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
  const titleId = useId();

  return (
    <CardShell accent={style.accent} labelledBy={titleId}>
      <CardHeader
        icon={<IconScale size={17} aria-hidden />}
        eyebrow="사전검토 결과"
        title={payload.title}
        titleId={titleId}
      />

      {/* 결론 배너 — 1차 정보. 색 + 라벨 + 아이콘 셋으로 동시에 전달(WCAG·DESIGN §2.4). */}
      <div
        className="a2ui-verdict"
        role="status"
        style={{ ...style.verdictVars, marginTop: '0.75rem' }}
      >
        <span className="a2ui-verdict__icon">{style.icon}</span>
        <span className="a2ui-verdict__label">{style.label}</span>
      </div>

      <Text
        size="sm"
        c="var(--jippin-brand-copy)"
        mt="sm"
        style={{ lineHeight: 1.6 }}
      >
        {payload.summary}
      </Text>

      {risks.length > 0 ? (
        <Stack gap={6} mt="sm">
          <Text
            size="xs"
            fw={600}
            c="var(--jippin-brand-ink)"
            style={{ letterSpacing: '0.01em' }}
          >
            확인이 필요한 점
          </Text>
          <ul className="a2ui-risks">
            {risks.map((risk, index) => (
              <li key={index} className="a2ui-risks__item">
                {risk}
              </li>
            ))}
          </ul>
        </Stack>
      ) : null}

      <CardRule />

      <Text className="a2ui-legal">
        본 결과는 첨부 자료를 바탕으로 한 참고용 안내이며, 법적 판단을 대체하지
        않습니다. 정확한 확인은 전문가와 상담해 주세요.
      </Text>
    </CardShell>
  );
}

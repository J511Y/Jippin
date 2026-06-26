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

import { Button, Stack, Text } from '@mantine/core';
import {
  IconCircleCheck,
  IconCircleX,
  IconHeadset,
  IconInfoCircle,
  IconScale,
  IconUserSearch
} from '@tabler/icons-react';
import { useId, useState, type CSSProperties, type ReactNode } from 'react';

import { LEGAL_NOTICE_TEXT } from '@/components/LegalNotice';
import { QuickPrecheckConsultForm } from '@/components/leads/QuickPrecheckConsultForm';

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
  /** true 면 룰엔진(evaluate_rules) 판정 기반, false/미지정이면 규칙 평가 전 예비 결과. */
  rule_backed?: boolean;
  /** 하단 상담 CTA → 빠른 상담폼 prefill 용. */
  session_id?: string;
  prefill_address?: string;
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
  const [showConsult, setShowConsult] = useState(false);
  const [consultSubmitted, setConsultSubmitted] = useState(false);
  const prefillAddress =
    typeof payload.prefill_address === 'string' ? payload.prefill_address : undefined;

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

      {/* 판정 근거 투명성 — 법령 기준 검토를 거친 결과인지, 그 전 예비 관찰인지 한 줄로
          밝힌다. B2C 카피라 '룰엔진' 등 내부 용어는 노출하지 않는다. */}
      <Text size="11px" c="dimmed" mt={6} style={{ lineHeight: 1.4 }}>
        {payload.rule_backed
          ? '※ 법령 기준으로 검토한 결과예요.'
          : '※ 자동 분석 기반 예비 관찰이에요. 검토에 필요한 정보가 모이면 더 정확히 봐 드려요.'}
      </Text>

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

      {/* 상담 인입 — 결과를 본 직후 전문가 상담으로 자연스럽게 잇는다. 클릭하면 같은
          대화 화면에서 빠른 상담폼이 펼쳐지고, 주소 등은 이미 세션이 알고 있어 바로 제출. */}
      {consultSubmitted ? (
        <Text size="sm" c="var(--jippin-brand-copy)" mb="sm" style={{ lineHeight: 1.55 }}>
          상담 신청이 접수되었어요. 담당자가 영업일 기준 1일 이내에 연락드릴게요.
        </Text>
      ) : showConsult ? (
        <Stack gap="xs" mb="sm">
          <Text size="sm" fw={600} c="var(--jippin-brand-ink)">
            전문가 상담 신청
          </Text>
          <QuickPrecheckConsultForm
            prefillAddress={prefillAddress}
            ctaId="precheck_report"
            onSubmitted={() => setConsultSubmitted(true)}
          />
        </Stack>
      ) : (
        <Button
          color="coral"
          radius="md"
          fullWidth
          mb="sm"
          leftSection={<IconHeadset size={18} aria-hidden />}
          onClick={() => setShowConsult(true)}
        >
          전문가 상담 신청하기
        </Button>
      )}

      {/* 결과 화면 법적 고지 — 봉인된 SSOT 문구 그대로(TYPOGRAPHY §4.5/BRAND §6, 단축 금지). */}
      <Text className="a2ui-legal">{LEGAL_NOTICE_TEXT}</Text>
    </CardShell>
  );
}

'use client';

/**
 * A2UI `ConsultationHandoff` 카드 — 사전검토 상담 전환 인입 (CMP-DIRECT).
 *
 * 사전검토가 리포트까지 가지 못하고 실패/보류(HOLD_OR_HANDOFF)했을 때 백엔드가 방출한다.
 * 도면 확보 실패·분석 실패·저신뢰·판단값 수집 실패·자동 판단 불가 등 여러 실패 지점이
 * 모두 set_completion_decision('HOLD_OR_HANDOFF') 으로 모여, 그 시점에 이 카드가 뜬다.
 *
 * 안내 문구(reason) + **상담 신청 폼을 그대로 인라인 렌더**해 전문가 상담으로 이어 준다.
 * 사전검토에서 확정한 주소(prefill_address)는 상담 내용에 맥락으로 미리 담는다.
 *
 * payload: { reason?: string; prefill_address?: string; from_session?: string }
 */

import { Stack, Text } from '@mantine/core';
import { IconHeadset } from '@tabler/icons-react';
import { useId, useState } from 'react';

import { QuickPrecheckConsultForm } from '@/components/leads/QuickPrecheckConsultForm';

import { CardHeader, CardRule, CardShell } from './CardShell';

export type ConsultationHandoffPayload = {
  reason?: string;
  prefill_address?: string;
  from_session?: string;
};

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function isConsultationHandoffPayload(
  payload: unknown
): payload is ConsultationHandoffPayload {
  return isPlainObject(payload);
}

const DEFAULT_REASON =
  '지금 단계에서는 자동으로 확인하기 어려운 부분이 있어요. 전문가가 직접 도면을 보고 더 정확히 안내해 드릴게요.';

export function ConsultationHandoffCard({
  payload
}: {
  payload: ConsultationHandoffPayload;
}) {
  const titleId = useId();
  const [submitted, setSubmitted] = useState(false);

  const reason =
    typeof payload.reason === 'string' && payload.reason.trim().length > 0
      ? payload.reason.trim()
      : DEFAULT_REASON;
  const address =
    typeof payload.prefill_address === 'string' ? payload.prefill_address : undefined;

  return (
    <CardShell accent="primary" labelledBy={titleId}>
      <CardHeader
        icon={<IconHeadset size={17} aria-hidden />}
        eyebrow="전문가 상담"
        title={submitted ? '상담 신청이 접수되었어요' : '전문가 상담으로 도와드릴게요'}
        titleId={titleId}
      />
      <CardRule />

      {submitted ? (
        <Text size="sm" c="var(--jippin-brand-copy)" style={{ lineHeight: 1.6 }}>
          신청이 접수되었어요. 담당자가 영업일 기준 1일 이내에 연락드릴게요.
        </Text>
      ) : (
        <Stack gap="sm">
          <Text size="sm" c="var(--jippin-brand-copy)" style={{ lineHeight: 1.6 }}>
            {reason}
          </Text>
          {/* 사전검토 빠른 상담폼 — 이름/연락처만(로그인 시 자동) + 세션이 아는 주소로 바로 제출. */}
          <QuickPrecheckConsultForm
            prefillAddress={address}
            fromSession={
              typeof payload.from_session === 'string' ? payload.from_session : undefined
            }
            ctaId="precheck_handoff"
            onSubmitted={() => setSubmitted(true)}
          />
        </Stack>
      )}
    </CardShell>
  );
}

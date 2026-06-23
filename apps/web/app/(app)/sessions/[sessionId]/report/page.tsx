'use client';

import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  List,
  Loader,
  Stack,
  Text,
  Title
} from '@mantine/core';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';

import { LegalNotice } from '@/components/LegalNotice';
import { LeadCtaButton } from '@/components/analytics/LeadCtaButton';
import { parseApiError } from '@/lib/api/error';
import {
  getSessionReport,
  syncExistingToken,
  type SessionReportResponse
} from '@/lib/sessions/api';

const VERDICT: Record<string, { label: string; color: string }> = {
  ALLOW: { label: '가능성 있음', color: 'success' },
  WARN: { label: '조건부 가능', color: 'yellow' },
  HOLD: { label: '추가 확인 필요', color: 'gray' },
  DENY: { label: '어려움', color: 'red' }
};

type Facility = { label?: string; measurement_basis?: string };
type LegalBasis = { statute?: string; article?: string; summary?: string };

export default function SessionReportPage() {
  const params = useParams<{ sessionId: string }>();
  const sessionId = params.sessionId;
  const [report, setReport] = useState<SessionReportResponse | null>(null);
  const [notReady, setNotReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;
    void (async () => {
      try {
        await syncExistingToken();
        const data = await getSessionReport(sessionId);
        if (!ignore) setReport(data);
      } catch (err) {
        const parsed = parseApiError(err);
        if (ignore) return;
        if (parsed.code === 'REPORT_NOT_READY') setNotReady(true);
        else setError(parsed.message);
      }
    })();
    return () => {
      ignore = true;
    };
  }, [sessionId]);

  const result = report?.rule_eval_result as
    | {
        verdict?: string;
        user_message?: string;
        permit_required?: boolean;
        required_facilities?: Facility[];
        legal_basis?: LegalBasis[];
      }
    | undefined;
  const verdict = result?.verdict ? VERDICT[result.verdict] : undefined;

  return (
    <Stack gap="lg">
      <Stack gap="xs">
        <Title order={1}>AI 사전검토 리포트</Title>
        <Text c="dimmed" size="sm" style={{ wordBreak: 'keep-all' }}>
          도면과 주소 분석을 바탕으로 정리한 사전 판단 결과입니다. 최종 행위허가는
          관할 기관 판단에 따라 달라질 수 있어요.
        </Text>
      </Stack>

      {error && (
        <Alert color="red" variant="light" radius="md">
          {error}
        </Alert>
      )}

      {notReady && (
        <Card withBorder radius="md" padding="lg">
          <Stack gap="sm">
            <Text fw={600}>리포트가 아직 준비되지 않았어요</Text>
            <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
              AI 도우미와의 대화를 완료하면 판정 결과가 여기에 표시됩니다.
            </Text>
            <Button
              component="a"
              href={`/sessions/${sessionId}`}
              color="jippin"
              radius="md"
              w="fit-content"
            >
              대화로 돌아가기 →
            </Button>
          </Stack>
        </Card>
      )}

      {report === null && !notReady && !error && (
        <Group justify="center" py="lg">
          <Loader size="sm" color="jippin" />
        </Group>
      )}

      {report !== null && result && (
        <>
          <Card withBorder radius="md" padding="md">
            <Stack gap="sm">
              <Group justify="space-between">
                <Text fw={600}>판단 결과</Text>
                <Badge color={verdict?.color ?? 'gray'} variant="filled">
                  {verdict?.label ?? result.verdict ?? '판정'}
                </Badge>
              </Group>
              {result.user_message && (
                <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
                  {result.user_message}
                </Text>
              )}
              {/* HOLD(데이터 부족)면 엔진이 permit_required 를 보수적으로 true 로 직렬화하지만
                  실제 행위허가 필요 여부는 미정이다. boolean 만 보고 '필요'로 단정하지 않는다. */}
              <Text size="xs" c="dimmed">
                행위허가{' '}
                {result.verdict === 'HOLD'
                  ? '미정 (추가 확인 필요)'
                  : result.permit_required
                    ? '필요'
                    : '불요(또는 신고 대상)'}
              </Text>
            </Stack>
          </Card>

          {(result.required_facilities ?? []).length > 0 && (
            <Card withBorder radius="md" padding="md">
              <Stack gap="xs">
                <Text fw={600}>필요 안전시설</Text>
                <List size="sm" spacing={4}>
                  {(result.required_facilities ?? []).map((f, i) => (
                    <List.Item key={i}>
                      {f.label}
                      {f.measurement_basis ? ` — ${f.measurement_basis}` : ''}
                    </List.Item>
                  ))}
                </List>
              </Stack>
            </Card>
          )}

          {(result.legal_basis ?? []).length > 0 && (
            <Card withBorder radius="md" padding="md">
              <Stack gap="xs">
                <Text fw={600}>법적 근거</Text>
                <List size="sm" spacing={4}>
                  {(result.legal_basis ?? []).map((l, i) => (
                    <List.Item key={i}>
                      {[l.statute, l.article].filter(Boolean).join(' ')}
                      {l.summary ? ` — ${l.summary}` : ''}
                    </List.Item>
                  ))}
                </List>
              </Stack>
            </Card>
          )}
        </>
      )}

      {/* AGENTS.md §4.6: 리포트 화면 안에 inline LegalNotice 를 보장. */}
      <LegalNotice variant="inline" />

      <Stack gap="sm">
        <LeadCtaButton
          cta="report_bottom"
          fromSession={sessionId}
          size="lg"
          color="coral"
          radius="md"
          fullWidth
        >
          전문가 상담 신청하기
        </LeadCtaButton>
        <Button
          component="a"
          href="/sessions"
          variant="subtle"
          color="jippin"
          radius="md"
          fullWidth
        >
          세션 목록으로
        </Button>
      </Stack>
    </Stack>
  );
}

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
import { trackPrecheckReportView } from '@/lib/analytics/sessions-funnel';
import { friendlyApiMessage, parseApiError } from '@/lib/api/error';
import {
  getSessionReport,
  issueSessionReportPdf,
  syncExistingToken,
  type EstimateResult,
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
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);

  // PDF 리포트 발부 — 서버가 생성·보관한 PDF 의 단기 서명 URL 을 받아 새 탭으로 연다.
  // 팝업 차단 회피: 생성(await)을 기다린 뒤 window.open 을 호출하면 사용자 제스처가
  // 끊긴 것으로 보여 차단될 수 있다. 클릭 즉시 빈 탭을 먼저 열고 URL 도착 후 이동한다.
  const handleIssuePdf = async () => {
    setPdfLoading(true);
    setPdfError(null);
    const pdfTab = window.open('about:blank', '_blank');
    try {
      const { url } = await issueSessionReportPdf(sessionId);
      if (pdfTab) {
        // 역-탭내빙 방지: opener 끊고 신뢰된 서명 URL 로 이동.
        pdfTab.opener = null;
        pdfTab.location.href = url;
      } else {
        // 빈 탭이 막혔으면(차단/모바일) 현재 탭에서 연다.
        window.location.href = url;
      }
    } catch (err) {
      pdfTab?.close();
      setPdfError(friendlyApiMessage(err, 'PDF 리포트를 발부하지 못했어요. 잠시 후 다시 시도해 주세요.'));
    } finally {
      setPdfLoading(false);
    }
  };

  useEffect(() => {
    let ignore = false;
    void (async () => {
      try {
        await syncExistingToken();
        const data = await getSessionReport(sessionId);
        if (!ignore) {
          setReport(data);
          // 퍼널: 리포트 진입(판정 준비됨).
          trackPrecheckReportView(true);
        }
      } catch (err) {
        const parsed = parseApiError(err);
        if (ignore) return;
        if (parsed.code === 'REPORT_NOT_READY') {
          setNotReady(true);
          // 퍼널: 리포트 진입(아직 판정 미준비).
          trackPrecheckReportView(false);
        } else setError(friendlyApiMessage(err, '리포트를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.'));
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

          {report.estimate && <EstimateCard estimate={report.estimate} />}

          {/* PDF 리포트 발부 — 도면 오버레이·벽체 판단·견적·일정·상담을 담은 디자인
              리포트를 서버에서 생성해 단기 서명 URL 로 내려준다. */}
          <Card withBorder radius="md" padding="md">
            <Stack gap="sm">
              <Group justify="space-between" align="center" wrap="nowrap">
                <Stack gap={2} style={{ flex: 1 }}>
                  <Text fw={600}>PDF 리포트 발부</Text>
                  <Text size="xs" c="dimmed" style={{ wordBreak: 'keep-all' }}>
                    도면 분석·벽체 판단·예상 견적·진행 일정·상담 안내를 담은 리포트를
                    PDF 로 내려받을 수 있어요.
                  </Text>
                </Stack>
                <Button
                  color="jippin"
                  radius="md"
                  onClick={handleIssuePdf}
                  loading={pdfLoading}
                  style={{ whiteSpace: 'nowrap' }}
                >
                  PDF로 받기
                </Button>
              </Group>
              {pdfError && (
                <Alert color="red" variant="light" radius="md" py="xs">
                  {pdfError}
                </Alert>
              )}
            </Stack>
          </Card>
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

/** 원(KRW) 표기 — 천 단위 구분. */
function won(amount: number): string {
  return `${amount.toLocaleString('ko-KR')}원`;
}

/** 견적 항목 1줄의 금액 문구 — 고정 최소액/단가/별도견적을 구분해 표기. */
function amountText(item: EstimateResult['items'][number]): string {
  if (typeof item.amount_min === 'number') {
    return `${won(item.amount_min)}~`;
  }
  if (typeof item.unit_amount === 'number') {
    return `${won(item.unit_amount)}${item.unit ? ` / ${item.unit.replace(/^원\//, '')}` : ''}~`;
  }
  return '별도 견적';
}

/** 예상 견적 카드(REPORT-003) — /faq?category=cost 단가표 기반 예비 안내. */
function EstimateCard({ estimate }: { estimate: EstimateResult }) {
  return (
    <Card withBorder radius="md" padding="md">
      <Stack gap="sm">
        <Group justify="space-between" align="center">
          <Text fw={600}>예상 견적</Text>
          <Badge color="gray" variant="light">
            참고용 · 부가세 포함
          </Badge>
        </Group>

        <Stack gap={6}>
          {estimate.items.map((item) => (
            <Group key={item.code} justify="space-between" align="flex-start" wrap="nowrap">
              <Stack gap={0} style={{ flex: 1 }}>
                <Text size="sm" fw={500}>
                  {item.label}
                </Text>
                {item.note && (
                  <Text size="xs" c="dimmed" style={{ wordBreak: 'keep-all' }}>
                    {item.note}
                  </Text>
                )}
              </Stack>
              <Text size="sm" fw={600} style={{ whiteSpace: 'nowrap' }}>
                {amountText(item)}
              </Text>
            </Group>
          ))}
        </Stack>

        {typeof estimate.fixed_total_min === 'number' && (
          <Group justify="space-between" align="center">
            <Text size="sm" fw={600}>
              기본 합계 (최소)
            </Text>
            <Text size="sm" fw={700} c="coral">
              {won(estimate.fixed_total_min)}~
              {estimate.has_variable_items ? ' + 현장 항목' : ''}
            </Text>
          </Group>
        )}

        <Text size="xs" c="dimmed" style={{ wordBreak: 'keep-all' }}>
          {estimate.disclaimer}
        </Text>
        <Button
          component="a"
          href={estimate.source_url}
          variant="subtle"
          color="jippin"
          size="compact-sm"
          w="fit-content"
        >
          비용 안내 자세히 보기 →
        </Button>
      </Stack>
    </Card>
  );
}

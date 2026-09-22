'use client';

/**
 * 사전검토 리포트 화면 (2026-09 디자인 감사 재설계).
 *
 * 구조 — TYPOGRAPHY.md §3 결과 카드 4구간을 화면 전체에 적용한다.
 *   1. 결론 한 장: 판정 히어로(display 1줄 + 행위허가 칩 + 한 줄 사유) → 3행 요약(대상 벽체 ·
 *      행위허가 · 추가 확인) → 선택 도면 오버레이. 상태색은 히어로 한 곳에만.
 *   2. 다음 행동: PDF 로 받기(jippin filled) + 전문가 상담(코랄, 이 화면의 코랄 1회).
 *   3. 근거·상세: 법적 근거·추가 확인·안전시설·예상 견적을 접이식으로. 결론과 근거가 같은
 *      시야에 있도록 법적 근거와 추가 확인은 기본 펼침(DESIGN §2.1).
 *   4. 법적 고지(봉인 문구, AGENTS §4.6).
 *
 * 이전 화면의 문제(감사): 같은 무게 카드 6장 나열 → 위계 없음, 판정 2회 반복, 도면·주소·
 * 날짜 부재, xs dimmed 단락 연속, PDF 발부가 6번째 카드.
 */

import {
  Accordion,
  Alert,
  Badge,
  Button,
  Group,
  List,
  Skeleton,
  Stack,
  Text,
  Title,
  VisuallyHidden
} from '@mantine/core';
import {
  IconAlertTriangle,
  IconArrowLeft,
  IconCircleCheck,
  IconCircleX,
  IconFileDownload,
  IconHelpCircle
} from '@tabler/icons-react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useState, type ReactNode } from 'react';

import { LegalNotice } from '@/components/LegalNotice';
import { LeadCtaButton } from '@/components/analytics/LeadCtaButton';
import { ReportFloorplan, selectedIdsOf } from '@/components/report/ReportFloorplan';
import { trackPrecheckReportView } from '@/lib/analytics/sessions-funnel';
import { friendlyApiMessage, parseApiError } from '@/lib/api/error';
import {
  getSession,
  getSessionReport,
  issueSessionReportPdf,
  syncExistingToken,
  type EstimateResult,
  type SessionReportResponse,
  type SessionResponse
} from '@/lib/sessions/api';

// 판정 표기 — 색 + 라벨 + 아이콘 셋을 동시에 전달(DESIGN §2.4). 색은 상태 토큰만
// (success/warning/danger/info). HOLD(데이터 부족)는 경고도 실패도 아니어서 info.
const VERDICT: Record<
  string,
  { label: string; tone: 'success' | 'warning' | 'danger' | 'info'; icon: ReactNode }
> = {
  ALLOW: { label: '가능성 있음', tone: 'success', icon: <IconCircleCheck size={22} /> },
  WARN: { label: '조건부 가능', tone: 'warning', icon: <IconAlertTriangle size={22} /> },
  HOLD: { label: '추가 확인 필요', tone: 'info', icon: <IconHelpCircle size={22} /> },
  DENY: { label: '어려움', tone: 'danger', icon: <IconCircleX size={22} /> }
};

type Facility = { label?: string; measurement_basis?: string };
type LegalBasis = {
  statute?: string;
  article?: string;
  summary?: string;
  url?: string | null;
};
type RuleEval = {
  verdict?: string;
  user_message?: string;
  permit_required?: boolean;
  required_facilities?: Facility[];
  legal_basis?: LegalBasis[];
  additional_checks?: string[];
  ruleset_version?: string;
};

/** 주소 한 줄 — PDF `_address_line` 과 같은 조립 규칙(도로명 + 단지 + 동 + 호). */
export function addressLineOf(address: Record<string, unknown> | null | undefined): string | null {
  if (!address) return null;
  const str = (k: string) => (typeof address[k] === 'string' ? (address[k] as string).trim() : '');
  const parts = [str('road_address') || str('jibun_address'), str('apartment_name')].filter(Boolean);
  const dong = str('building_dong');
  if (dong) parts.push(dong.endsWith('동') ? dong : `${dong}동`);
  const ho = str('unit_ho');
  if (ho) parts.push(ho.endsWith('호') ? ho : `${ho}호`);
  const line = parts.join(' ').trim();
  return line || null;
}

function formatDateKr(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    timeZone: 'Asia/Seoul'
  }).format(d);
}

export default function SessionReportPage() {
  const params = useParams<{ sessionId: string }>();
  const sessionId = params.sessionId;
  const [report, setReport] = useState<SessionReportResponse | null>(null);
  const [session, setSession] = useState<SessionResponse | null>(null);
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
        if (ignore) return;
        setReport(data);
        // 퍼널: 리포트 진입(판정 준비됨).
        trackPrecheckReportView(true);
        // 도면 오버레이용 세션 메타(선택 도면·판단스키마) — 실패해도 리포트는 성립(best-effort).
        try {
          const row = await getSession(sessionId);
          if (!ignore) setSession(row);
        } catch {
          /* 도면 없이 렌더 */
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

  const result = report?.rule_eval_result as RuleEval | undefined;
  const verdict = result?.verdict ? VERDICT[result.verdict] : undefined;
  const additionalChecks = (result?.additional_checks ?? []).filter(
    (c): c is string => typeof c === 'string' && c.length > 0
  );
  const facilities = result?.required_facilities ?? [];
  const legalBasis = result?.legal_basis ?? [];
  const addressLine = addressLineOf(report?.address);
  const evaluatedKr = formatDateKr(report?.evaluated_at);
  const selectedCount = selectedIdsOf(session?.judgment_schema).length;
  // HOLD(데이터 부족)면 엔진이 permit_required 를 보수적으로 true 로 직렬화하지만 실제
  // 행위허가 필요 여부는 미정이다. boolean 만 보고 '필요'로 단정하지 않는다.
  const permit =
    result?.verdict === 'HOLD'
      ? { text: '미정 · 추가 확인 필요', tone: 'info' as const }
      : result?.permit_required
        ? { text: '필요', tone: 'warning' as const }
        : { text: '불요(또는 신고 대상)', tone: 'success' as const };

  const detailsDefault = [
    ...(legalBasis.length ? ['legal'] : []),
    ...(additionalChecks.length ? ['checks'] : [])
  ];

  return (
    <Stack gap="lg" maw={760} mx="auto">
      {/* 헤더 — Blueprint Navy 전문 축(상단 보더 + 네이비 아이브로). 제목 대신 주소·날짜가
          이 리포트가 '어느 집·언제' 것인지 말한다. 결론(display)은 바로 아래 히어로가 맡는다. */}
      <Stack
        gap={4}
        style={{
          borderTop: '3px solid var(--jippin-brand-professional)',
          paddingTop: 'var(--mantine-spacing-md)'
        }}
      >
        <Text size="sm" fw={600} c="var(--jippin-brand-professional)">
          AI 사전검토 리포트
        </Text>
        {report !== null ? (
          <Group gap="xs" align="baseline" wrap="wrap">
            {addressLine ? (
              <Text fw={600} style={{ wordBreak: 'keep-all' }}>
                {addressLine}
              </Text>
            ) : null}
            {evaluatedKr ? (
              <Text size="sm" c="dimmed">
                {evaluatedKr} 판정
              </Text>
            ) : null}
          </Group>
        ) : null}
      </Stack>

      {error && (
        <Alert color="danger" variant="light" radius="md">
          {error}
        </Alert>
      )}

      {notReady && (
        <Stack gap="sm" className="report-hero">
          <Text fw={600}>리포트가 아직 준비되지 않았어요</Text>
          <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
            AI 도우미와의 대화를 마치면 판정 결과가 여기에 표시됩니다.
          </Text>
          <Button
            component={Link}
            href={`/sessions/${sessionId}`}
            color="jippin"
            radius="md"
            w="fit-content"
            leftSection={<IconArrowLeft size={16} aria-hidden />}
          >
            대화로 돌아가기
          </Button>
        </Stack>
      )}

      {report === null && !notReady && !error && (
        <Stack gap="md" aria-busy="true" aria-label="리포트 불러오는 중">
          <Skeleton height={132} radius={14} />
          <Skeleton height={220} radius={12} />
          <Group grow>
            <Skeleton height={44} radius="md" />
            <Skeleton height={44} radius="md" />
          </Group>
        </Stack>
      )}

      {report !== null && result && (
        <>
          {/* ── 1. 결론 한 장 ── */}
          <section
            className={`report-hero report-hero--${verdict?.tone ?? 'info'}`}
            aria-labelledby="report-verdict"
          >
            <Group gap="md" align="center" wrap="nowrap">
              <span className="report-hero__disc" aria-hidden>
                {verdict?.icon ?? <IconHelpCircle size={22} />}
              </span>
              <Stack gap={2} style={{ minWidth: 0 }}>
                <Title order={1} id="report-verdict" className="report-hero__label">
                  <VisuallyHidden>사전검토 결과: </VisuallyHidden>
                  {verdict?.label ?? result.verdict ?? '판정'}
                </Title>
              </Stack>
            </Group>
            {result.user_message && (
              <Text mt="sm" style={{ wordBreak: 'keep-all', lineHeight: 1.6 }}>
                {result.user_message}
              </Text>
            )}
            <dl className="report-facts" style={{ margin: 0 }}>
              <div className="report-fact">
                <Text component="dt" size="sm" c="dimmed">
                  대상 벽체·창호
                </Text>
                <Text component="dd" size="sm" fw={600} m={0}>
                  {selectedCount > 0 ? `${selectedCount}곳 선택` : '선택 정보 없음'}
                </Text>
              </div>
              <div className="report-fact">
                <Text component="dt" size="sm" c="dimmed">
                  행위허가
                </Text>
                <Badge
                  component="dd"
                  color={permit.tone}
                  variant="dot"
                  radius="sm"
                  size="lg"
                  m={0}
                  styles={{ root: { textTransform: 'none', fontWeight: 600 } }}
                >
                  {permit.text}
                </Badge>
              </div>
              <div className="report-fact">
                <Text component="dt" size="sm" c="dimmed">
                  추가 확인
                </Text>
                <Badge
                  component="dd"
                  color={additionalChecks.length ? 'warning' : 'success'}
                  variant="dot"
                  radius="sm"
                  size="lg"
                  m={0}
                  styles={{ root: { textTransform: 'none', fontWeight: 600 } }}
                >
                  {additionalChecks.length ? `${additionalChecks.length}건` : '없음'}
                </Badge>
              </div>
            </dl>
          </section>

          {session?.selected_floorplan_asset_id ? (
            <ReportFloorplan
              sessionId={sessionId}
              assetId={session.selected_floorplan_asset_id}
              judgment={session.judgment_schema}
            />
          ) : null}

          {/* ── 2. 다음 행동 — PDF(제품 기능) + 상담(전환, 코랄 1회) ── */}
          <Stack gap="xs">
            <div className="report-actions">
              <Button
                color="jippin"
                radius="md"
                size="md"
                onClick={handleIssuePdf}
                loading={pdfLoading}
                leftSection={<IconFileDownload size={18} aria-hidden />}
              >
                PDF 리포트 받기
              </Button>
              <LeadCtaButton
                cta="report_bottom"
                fromSession={sessionId}
                size="md"
                color="coral"
                radius="md"
              >
                전문가 상담 신청하기
              </LeadCtaButton>
            </div>
            <Text size="xs" c="dimmed" ta="center" style={{ wordBreak: 'keep-all' }}>
              PDF 에는 도면 분석·챙겨야 할 요소·예상 견적·진행 일정이 함께 담겨요.
            </Text>
            {pdfError && (
              <Alert color="danger" variant="light" radius="md" py="xs">
                {pdfError}
              </Alert>
            )}
          </Stack>

          {/* ── 3. 근거·상세(접이식) ── */}
          <Accordion
            multiple
            defaultValue={detailsDefault}
            variant="separated"
            radius="md"
            className="report-details"
          >
            {legalBasis.length > 0 && (
              <Accordion.Item value="legal">
                <Accordion.Control>법적 근거</Accordion.Control>
                <Accordion.Panel>
                  <List size="sm" spacing={6}>
                    {legalBasis.map((l, i) => (
                      <List.Item key={i}>
                        {l.url ? (
                          // FR-REPORT-009 — 법령 원문 링크가 있으면 조문 표기를 링크로 연다.
                          <a
                            href={l.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ color: 'var(--jippin-brand-primary)', fontWeight: 600 }}
                          >
                            {[l.statute, l.article].filter(Boolean).join(' ')}
                          </a>
                        ) : (
                          <Text component="span" fw={600}>
                            {[l.statute, l.article].filter(Boolean).join(' ')}
                          </Text>
                        )}
                        {l.summary ? (
                          <Text component="span" c="dimmed">
                            {' '}
                            — {l.summary}
                          </Text>
                        ) : null}
                      </List.Item>
                    ))}
                  </List>
                  {result.ruleset_version && (
                    // RULE-003 — 판정 결정성 추적 키(적용 룰셋 버전) 노출.
                    <Text size="xs" c="dimmed" mt="xs">
                      적용 룰셋 버전 {result.ruleset_version}
                    </Text>
                  )}
                </Accordion.Panel>
              </Accordion.Item>
            )}

            {additionalChecks.length > 0 && (
              // REPORT-001 '판단 상태' — 보류/보수 가정 시 현장에서 확인할 체크리스트.
              <Accordion.Item value="checks">
                <Accordion.Control>추가로 확인하면 좋아요</Accordion.Control>
                <Accordion.Panel>
                  <List size="sm" spacing={6}>
                    {additionalChecks.map((check, i) => (
                      <List.Item key={i}>{check}</List.Item>
                    ))}
                  </List>
                </Accordion.Panel>
              </Accordion.Item>
            )}

            {facilities.length > 0 && (
              <Accordion.Item value="facilities">
                <Accordion.Control>필요 안전시설</Accordion.Control>
                <Accordion.Panel>
                  <List size="sm" spacing={6}>
                    {facilities.map((f, i) => (
                      <List.Item key={i}>
                        <Text component="span" fw={600}>
                          {f.label}
                        </Text>
                        {f.measurement_basis ? (
                          <Text component="span" c="dimmed">
                            {' '}
                            — {f.measurement_basis}
                          </Text>
                        ) : null}
                      </List.Item>
                    ))}
                  </List>
                </Accordion.Panel>
              </Accordion.Item>
            )}

            {report.estimate && result.verdict !== 'DENY' && (
              <Accordion.Item value="estimate">
                <Accordion.Control>예상 견적</Accordion.Control>
                <Accordion.Panel>
                  <EstimateBody estimate={report.estimate} />
                </Accordion.Panel>
              </Accordion.Item>
            )}
          </Accordion>
        </>
      )}

      {/* AGENTS.md §4.6: 리포트 화면 안에 inline LegalNotice 를 보장. */}
      <LegalNotice variant="inline" />

      {/* 보조 내비 — 미준비 상태는 위 카드가 '대화로 돌아가기'를 이미 제공하므로 생략. */}
      {report !== null ? (
        <Group justify="space-between">
          <Button
            component={Link}
            href={`/sessions/${sessionId}`}
            variant="subtle"
            color="jippin"
            radius="md"
            leftSection={<IconArrowLeft size={16} aria-hidden />}
          >
            대화로 돌아가기
          </Button>
          <Button component={Link} href="/sessions" variant="subtle" color="gray" radius="md">
            세션 목록
          </Button>
        </Group>
      ) : null}
    </Stack>
  );
}

/** 원(KRW) 표기 — 천 단위 구분. */
function won(amount: number): string {
  return `${amount.toLocaleString('ko-KR')}원`;
}

/** 견적 항목 1줄의 금액 문구 — 정액/전제 범위/단가/별도견적을 구분해 표기. */
function amountText(item: NonNullable<EstimateResult['items']>[number]): string {
  if (typeof item.amount_min === 'number') {
    if (typeof item.amount_max === 'number' && item.amount_max > item.amount_min) {
      return `${won(item.amount_min)}~${won(item.amount_max)}`;
    }
    return won(item.amount_min);
  }
  if (typeof item.unit_amount === 'number') {
    return `${won(item.unit_amount)}${item.unit ? ` / ${item.unit.replace(/^원\//, '')}` : ''}~`;
  }
  return '별도 견적';
}

/** 예상 견적(REPORT-003) — estimate-result 계약(1.1.0) 기반 예비 안내. */
function EstimateBody({ estimate }: { estimate: EstimateResult }) {
  const items = estimate.items ?? [];
  // 배포 스큐 방어: 구(1.0.0) API 응답엔 1.1.0 필드가 없다 — 전부 옵셔널로 접근한다.
  const assumptions = estimate.assumptions ?? [];
  const total = estimate.total_range;
  const hasTotal = total && total.max > 0;
  return (
    <Stack gap="sm">
      <Group justify="space-between" align="center">
        <Text size="xs" c="dimmed">
          참고용{estimate.vat_included ? ' · 부가세 포함' : ''}
        </Text>
      </Group>

      <Stack gap={6}>
        {items.map((item) => (
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
            <Text size="sm" fw={600} style={{ whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>
              {amountText(item)}
            </Text>
          </Group>
        ))}
      </Stack>

      {hasTotal && (
        <Group
          justify="space-between"
          align="center"
          pt="xs"
          style={{ borderTop: '1px solid var(--jippin-brand-border)' }}
        >
          <Text size="sm" fw={600}>
            합계 (예상 범위)
          </Text>
          {/* 금액 강조는 굵기만 — coral 은 전환 CTA 전용이라 금액에 쓰지 않는다. */}
          <Text size="sm" fw={700} style={{ fontVariantNumeric: 'tabular-nums' }}>
            {total.max > total.min ? `${won(total.min)}~${won(total.max)}` : won(total.min)}
            {estimate.consultation_required ? ' + 현장 견적 항목' : ''}
          </Text>
        </Group>
      )}

      {assumptions.length > 0 && (
        <List size="xs" spacing={2} c="dimmed">
          {assumptions.map((assumption, i) => (
            <List.Item key={i}>{assumption}</List.Item>
          ))}
        </List>
      )}

      {(estimate.variance_notes ?? []).map((note, i) => (
        <Text key={i} size="xs" c="dimmed" style={{ wordBreak: 'keep-all' }}>
          {note}
        </Text>
      ))}

      {estimate.disclaimer && (
        <Text size="xs" c="dimmed" style={{ wordBreak: 'keep-all' }}>
          {estimate.disclaimer}
        </Text>
      )}
      {estimate.source_url && (
        <Button
          component={Link}
          href={estimate.source_url}
          variant="subtle"
          color="jippin"
          size="compact-sm"
          w="fit-content"
        >
          비용 안내 자세히 보기 →
        </Button>
      )}
    </Stack>
  );
}

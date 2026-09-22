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
  IconHelpCircle,
  IconRefresh
} from '@tabler/icons-react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useState, type ReactNode } from 'react';

import { LegalNotice } from '@/components/LegalNotice';
import { LeadCtaButton } from '@/components/analytics/LeadCtaButton';
import {
  FloorplanUnavailable,
  ReportFloorplan,
  selectedIdsOf
} from '@/components/report/ReportFloorplan';
import { PageColumn, PageHeader } from '@/components/ui';
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
  const base = str('road_address') || str('jibun_address');
  const apt = str('apartment_name');
  // 도로명에 단지명이 이미 들어 있으면 반복하지 않는다(PDF _address_line 과 같은 포함 검사).
  const parts = [base, apt && !base.includes(apt) ? apt : ''].filter(Boolean);
  const dong = str('building_dong');
  if (dong) parts.push(dong.endsWith('동') ? dong : `${dong}동`);
  const ho = str('unit_ho');
  if (ho) parts.push(ho.endsWith('호') ? ho : `${ho}호`);
  const line = parts.join(' ').trim();
  return line || null;
}

/**
 * 리포트(evaluated_at = rule_evaluated_at)와 세션(verdict_revision = 같은 값의 epoch ms)이
 * 같은 판정을 가리키는지. 어느 쪽이든 리비전 정보가 없으면(구 API) 대조 불가 → 통과.
 * ms 반올림 차이(파이썬 int(ts*1000) vs JS Date.parse)를 2ms 허용한다.
 */
export function sameVerdictSnapshot(
  report: Pick<SessionReportResponse, 'evaluated_at'>,
  row: Pick<SessionResponse, 'has_report' | 'verdict_revision'>
): boolean {
  if (row.has_report === false) return false;
  const rev = row.verdict_revision;
  if (typeof rev !== 'number' || !report.evaluated_at) return true;
  const at = Date.parse(report.evaluated_at);
  if (Number.isNaN(at)) return true;
  return Math.abs(at - rev) <= 2;
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
  // 세션 메타(도면·판단스키마) 조회 실패 — 리포트는 성립하되 도면 구역은 '불러올 수 없음'으로.
  const [sessionFailed, setSessionFailed] = useState(false);
  // 리포트·세션 스냅샷이 재시도 뒤에도 어긋남 — 다른 탭에서 판정이 막 바뀐 상황. 옛 결론을
  // 보여주지 않고 다시 불러오기를 권한다.
  const [verdictChanged, setVerdictChanged] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [notReady, setNotReady] = useState(false);
  const reload = () => {
    setReport(null);
    setSession(null);
    setSessionFailed(false);
    setVerdictChanged(false);
    setError(null);
    setNotReady(false);
    setAttempt((n) => n + 1);
  };
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
        // 리포트(판정)와 세션 메타(선택 도면·판단스키마)를 **한 스냅샷**으로 맞춘다 — 두 요청
        // 사이에 다른 탭에서 벽을 다시 고르거나 도면을 바꾸면 옛 결론 위에 새 도면이 얹힐 수
        // 있다. 세션의 verdict_revision(rule_evaluated_at epoch ms)이 리포트의 evaluated_at 과
        // 다르거나 has_report 가 꺼져 있으면 리포트를 다시 읽는다(1회 재시도). 그래도 어긋나면
        // 옛 결론을 띄우지 않고 '판정이 갱신됨 · 다시 불러오기' 상태로 멈춘다.
        let data = await getSessionReport(sessionId);
        let row: SessionResponse | null = null;
        let rowFailed = false;
        let mismatch = false;
        for (let i = 0; i < 2; i += 1) {
          try {
            row = await getSession(sessionId);
          } catch {
            row = null;
            rowFailed = true; // 도면 구역은 '불러올 수 없음'으로 렌더(리포트는 성립)
            break;
          }
          if (sameVerdictSnapshot(data, row)) {
            mismatch = false;
            break;
          }
          mismatch = true;
          if (i === 0) data = await getSessionReport(sessionId);
        }
        if (ignore) return;
        if (mismatch) {
          setVerdictChanged(true);
          return;
        }
        setReport(data);
        setSession(row);
        setSessionFailed(rowFailed);
        // 퍼널: 리포트 진입(판정 준비됨).
        trackPrecheckReportView(true);
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
  }, [sessionId, attempt]);

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
  // PDF 안내 문구는 실제로 실리는 섹션만 말한다(report_pdf.py 게이팅: 일정은 ALLOW·WARN,
  // 견적은 DENY 제외).
  const pdfSections = [
    '도면 분석',
    '챙겨야 할 요소',
    ...(result?.verdict !== 'DENY' ? ['예상 견적'] : []),
    ...(result?.verdict === 'ALLOW' || result?.verdict === 'WARN' ? ['진행 일정'] : [])
  ];

  return (
    // AGENTS §4.8.1 — 좁은 읽기 컬럼은 PageColumn(prose 720)으로.
    <PageColumn width="prose">
    <Stack gap="lg">
      {/* 헤더 — Blueprint Navy 전문 축(상단 보더 + 네이비 아이브로). 제목 대신 주소·날짜가
          이 리포트가 '어느 집·언제' 것인지 말한다. 결론(display)은 바로 아래 히어로가 맡는다. */}
      <div
        style={{
          borderTop: '3px solid var(--jippin-brand-professional)',
          paddingTop: 'var(--mantine-spacing-md)'
        }}
      >
        {/* 페이지 h1 은 공용 PageHeader(theme h1 크기) — 로딩·미준비·오류·판정 갱신 상태에서도
            항상 렌더해 헤딩 내비게이션으로 이 화면을 식별한다. 판정 한 줄은 아래 히어로의
            h2(display 크기). 부제는 '어느 집·언제' 리포트인지. */}
        <PageHeader
          title={
            <Text component="span" inherit c="var(--jippin-brand-professional)">
              AI 사전검토 리포트
            </Text>
          }
          subtitle={
            report !== null && (addressLine || evaluatedKr)
              ? [addressLine, evaluatedKr ? `${evaluatedKr} 판정` : null]
                  .filter(Boolean)
                  .join(' · ')
              : undefined
          }
        />
      </div>

      {error && (
        // 일시 오류(네트워크·5xx)에도 복구 경로를 준다 — 다시 시도(전체 재조회) + 대화 복귀.
        <Alert color="danger" variant="light" radius="md">
          <Stack gap="sm">
            <Text size="sm">{error}</Text>
            <Group gap="xs">
              <Button
                size="sm"
                mih={44}
                color="jippin"
                radius="md"
                leftSection={<IconRefresh size={16} aria-hidden />}
                onClick={reload}
              >
                다시 시도
              </Button>
              <Button
                component={Link}
                href={`/sessions/${sessionId}`}
                size="sm"
                mih={44}
                variant="light"
                color="jippin"
                radius="md"
                leftSection={<IconArrowLeft size={16} aria-hidden />}
              >
                대화로 돌아가기
              </Button>
            </Group>
          </Stack>
        </Alert>
      )}

      {verdictChanged && (
        <Stack gap="sm" className="report-hero" role="status">
          <Text fw={600}>판정이 방금 갱신됐어요</Text>
          <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
            다른 탭에서 벽·창호 선택이나 도면이 바뀌어 결과가 새로 계산됐어요. 최신 리포트를
            다시 불러와 주세요.
          </Text>
          <Button
            color="jippin"
            radius="md"
            w="fit-content"
            leftSection={<IconRefresh size={16} aria-hidden />}
            onClick={reload}
          >
            최신 리포트 불러오기
          </Button>
        </Stack>
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

      {report === null && !notReady && !error && !verdictChanged && (
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
                <Title order={2} id="report-verdict" className="report-hero__label">
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
                  {/* 세션 메타를 못 읽었으면 0 을 사실처럼 말하지 않는다. */}
                  {sessionFailed
                    ? '불러올 수 없음'
                    : selectedCount > 0
                      ? `${selectedCount}곳 선택`
                      : '선택 정보 없음'}
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

          {/* 도면: 세션 메타를 못 읽었으면(네트워크) 조용히 빼지 않고 '불러올 수 없음'을 보여준다.
              세션은 읽었지만 선택 도면이 없는 리포트(도면 없이 진행)만 구역 자체를 생략. */}
          {sessionFailed ? (
            <FloorplanUnavailable onRetry={reload} />
          ) : session?.selected_floorplan_asset_id ? (
            <ReportFloorplan
              sessionId={sessionId}
              assetId={session.selected_floorplan_asset_id}
              judgment={session.judgment_schema}
            />
          ) : null}

          {/* ── 2. 다음 행동 — PDF(제품 기능) + 상담(전환, 코랄 1회) ── */}
          <Stack gap="xs">
            <div className="report-actions">
              {/* 모바일 터치 타깃 ≥44px(AGENTS §4.8.1) — md 버튼은 42px 이라 mih 로 보강. */}
              <Button
                color="jippin"
                radius="md"
                size="md"
                mih={44}
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
                mih={44}
                color="coral"
                radius="md"
              >
                전문가 상담 신청하기
              </LeadCtaButton>
            </div>
            <Text size="xs" c="dimmed" ta="center" style={{ wordBreak: 'keep-all' }}>
              PDF 에는 {pdfSections.join('·')}이 함께 담겨요.
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
    </PageColumn>
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

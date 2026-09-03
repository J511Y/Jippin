'use client';

import { Accordion, Anchor, Badge, Button, Group, Stack, Text } from '@mantine/core';
import {
  IconAlertTriangle,
  IconArrowRight,
  IconCalendarStats,
  IconChevronRight,
  IconCircleCheck,
  IconDownload,
  IconFileText,
  IconHelpCircle,
  IconRulerMeasure
} from '@tabler/icons-react';
import Link from 'next/link';
import type { ReactNode } from 'react';
import { useId } from 'react';
import type { HomeCheckReport } from '@contracts/home-check';

import { CardHeader, CardRule, CardShell, type CardAccent } from '@/components/a2ui/cards/CardShell';
import { CtaButton } from '@/components/ui';
import { homeCheckLeadHref } from '@/lib/home-check/lead-prefill';
import {
  formatArea,
  isoDate,
  jobAddressLabel,
  resolveVerdict,
  VERDICT_META,
  type Verdict,
  type VerdictTone
} from '@/lib/home-check/display';

/** 변동사항 중 확장·증축·용도변경 신호를 강조하기 위한 매칭 규칙. */
const EXTENSION_CHANGE_RE = /(확장|증축|용도변경)/;

/** tone → CardShell accent 레일 색 축. gray 는 neutral 로 매핑. */
const TONE_TO_ACCENT: Record<VerdictTone, CardAccent> = {
  danger: 'danger',
  warning: 'warning',
  success: 'success',
  gray: 'neutral'
};

/** verdict 별 CTA 카피(coral 버튼 전용). normal 은 CTA 를 노출하지 않는다. */
const CTA_COPY: Partial<Record<Verdict, { title: string; desc: string; label: string }>> = {
  illegal: {
    title: '위반표시 해소가 궁금하세요?',
    desc: '위반건축물 표시 해소나 사용검사 절차는 전문가 상담으로 도와드려요. 조회한 주소가 상담 신청서에 미리 채워져요.',
    label: '위반 해소 상담받기'
  },
  unrecorded_ext: {
    title: '미등재 확장, 어떻게 해야 할까요?',
    desc: '신고되지 않은 확장은 양성화(사용검사)나 원상복구가 필요할 수 있어요. 전문가 상담으로 다음 단계를 안내받으세요.',
    label: '확장 신고 상담받기'
  },
  caution: {
    title: '확인이 필요한 점이 있나요?',
    desc: '애매한 부분은 전문가 상담으로 명확히 짚어드려요. 조회한 주소가 상담 신청서에 미리 채워져요.',
    label: '전문가 상담받기'
  },
  not_checked: {
    title: '확장 여부가 궁금하세요?',
    desc: '확장·개조한 공간을 입력하면 대장 등재 여부를 대조해 드려요. 애매한 부분은 전문가 상담도 받을 수 있어요.',
    label: '전문가 상담받기'
  }
};

/** key-value 한 줄. 값이 없으면 렌더하지 않는다(호출부에서 필터). */
function DetailRow({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <Group justify="space-between" wrap="nowrap" gap="md" align="flex-start">
      <Text size="sm" c="dimmed" style={{ flexShrink: 0 }}>
        {label}
      </Text>
      <Text size="sm" ta="right" style={{ wordBreak: 'keep-all' }}>
        {value}
      </Text>
    </Group>
  );
}

/**
 * 우리집 체크 리포트 렌더 (CMP-DIRECT, ADR-0008, schema 1.2.0).
 *
 * a2ui 카드 시스템(CardShell/`.a2ui-verdict`/`.a2ui-risks`)을 그대로 재사용해 "투박함"을
 * 걷어낸다. 두 판정 축(공식 위반표시 + 확장 등재 대조)을 resolveVerdict 로 하나의 4-상태
 * 히어로에 합치고, 핵심을 "변동사항 + 확장 대조" 로 재배치한다.
 *
 * 순서: 히어로 → 확장 대조(핵심) → 변동사항 타임라인 → 대장 상세(접힘) → 발급 PDF →
 * CTA(coral) → 면책 → 다른 집 체크. 공동주택가격(prices) 섹션은 제거됨.
 */
export function HomeCheckReportView({
  report,
  checkId
}: {
  report: HomeCheckReport;
  checkId: string;
}) {
  const verdict = resolveVerdict(report);
  const meta = VERDICT_META[verdict];
  const accent = TONE_TO_ACCENT[meta.tone];
  const addressLabel = jobAddressLabel({ report });
  const heroTitleId = useId();
  const HeroIcon = meta.Icon;

  const ext = report.extension_check ?? null;
  // 표제부는 수집·판정·대장 상세/PDF 정본에 그대로 유지하고, 사용자가 보는 변동 이력은
  // 해당 세대의 전유부 이력만 보여 준다.
  const changes = (report.change_history ?? []).filter((entry) => entry.source === 'exclusive');
  const documents = (report.documents ?? []).filter((d) => d.url);
  const cautionReasons = report.caution_reasons ?? [];
  const unrecordedAreas = ext?.unrecorded_areas ?? [];

  // verdict=normal 한 줄 요약: 확장 등재는 **실제 매칭된 부위가 있을 때만** 단정한다. matched 가
  // 비면(무확장 응답 또는 부위 누락된 불완전 legal 응답) '확장도 등재됨'/'무확장'을 추정하지 않고
  // 위반표시 없음만 알린다 — 빈 배열로 무확장을 추정하지 않는다(#no-ext-infer).
  const heroOneLiner =
    verdict === 'normal'
      ? (ext?.matched_areas?.length ?? 0) > 0
        ? '위반표시가 없고, 신고하신 확장도 대장에 등재돼 있어요.'
        : '위반표시가 없어요.'
      : meta.oneLiner;

  // 히어로 "확인이 필요한 점" = caution 사유 ∪ 미등재 확장 부위(중복 제거).
  const checkPoints = Array.from(
    new Set([
      ...cautionReasons,
      ...unrecordedAreas.map((area) => `${area} · 대장 변동사항에서 확인 안 됨`)
    ])
  );

  const exclusiveRows = report.exclusive_part
    ? [
        { label: '전유면적', value: formatArea(report.exclusive_part.area_m2) },
        { label: '용도', value: report.exclusive_part.use_type },
        { label: '구조', value: report.exclusive_part.structure },
        { label: '층', value: report.exclusive_part.floor }
      ].filter((r) => r.value)
    : [];

  const buildingRows = report.building
    ? [
        { label: '주용도', value: report.building.main_use },
        { label: '층수', value: report.building.floors },
        { label: '사용승인일', value: report.building.approval_date },
        { label: '허가일', value: report.building.permit_date }
      ].filter((r) => r.value)
    : [];

  const hasRegisterDetail = exclusiveRows.length > 0 || buildingRows.length > 0;
  const cta = verdict === 'normal' ? null : CTA_COPY[verdict];

  return (
    <Stack gap="xl">
      {/* 1. VerdictHero — 두 축을 합친 4-상태 결론. 판정 아이콘+라벨을 카드 헤드에 직접
          싣는다(별도 결론 배너는 헤드와 중복이라 제거 — 운영자 디자인 피드백 2026-07-14).
          색+아이콘+라벨 동시 전달(WCAG·색 단독 금지)은 accent 헤드가 그대로 담당한다. */}
      <CardShell accent={accent} labelledBy={heroTitleId}>
        <div className="a2ui-card__head">
          <span className="a2ui-card__icon" aria-hidden>
            <HeroIcon size={17} />
          </span>
          <span style={{ minWidth: 0 }}>
            <span className="a2ui-card__eyebrow">{meta.label}</span>
            <span
              className="a2ui-card__title"
              id={heroTitleId}
              style={{ wordBreak: 'keep-all' }}
            >
              {addressLabel ?? '조회한 집'}
            </span>
          </span>
        </div>

        {/* 판정 한 줄 — 리포트 최상단 결론. 페이지 타이틀(h1)보다 커 보이지 않게 heading
            h2 토큰을 쓴다(TYPOGRAPHY.md §2 — 페이지별 임의 크기 발명 금지). */}
        <Text
          fw={700}
          mt="md"
          style={{
            fontSize: 'var(--mantine-h2-font-size)',
            lineHeight: 1.45,
            letterSpacing: '-0.01em',
            color: 'var(--jippin-brand-ink)',
            wordBreak: 'keep-all'
          }}
        >
          {heroOneLiner}
        </Text>

        {checkPoints.length > 0 ? (
          <Stack gap={6} mt="md">
            <Text size="xs" fw={600} c="var(--jippin-brand-ink)">
              이런 점을 함께 확인해 보세요
            </Text>
            <ul className="a2ui-risks">
              {checkPoints.map((point, i) => (
                <li key={i} className="a2ui-risks__item" style={{ wordBreak: 'keep-all' }}>
                  {point}
                </li>
              ))}
            </ul>
          </Stack>
        ) : null}
      </CardShell>

      {/* 2. ExtensionDiagnosisCard — 핵심. 신고 확장 ↔ 대장 등재 대조. */}
      <ExtensionDiagnosisCard report={report} />

      {/* 3. ChangeTimelineCard — 변동사항 세로 타임라인. 확장/증축/용도변경 강조. */}
      {changes.length > 0 ? (
        <SectionCard
          accent="blueprint"
          icon={<IconCalendarStats size={17} aria-hidden />}
          eyebrow="건축물대장 변동사항"
          title="변동 이력 타임라인"
        >
          <Stack gap={0}>
            {changes.map((entry, i) => {
              const highlighted = EXTENSION_CHANGE_RE.test(entry.reason);
              return (
                <div
                  key={i}
                  style={{
                    borderLeft: highlighted
                      ? '2px solid var(--mantine-color-warning-4)'
                      : '2px solid var(--jippin-brand-border)',
                    background: highlighted ? 'var(--mantine-color-warning-0)' : undefined,
                    borderRadius: highlighted ? 12 : 0,
                    padding: highlighted ? '0.625rem 1rem 0.625rem 0.875rem' : '0.5rem 0 0.5rem 0.875rem',
                    // 강조 배경은 컨텐츠 폭에만 — 카드 전체 폭으로 늘리면 빈 영역까지
                    // 칠해진다(운영자 피드백 2026-07-14).
                    width: highlighted ? 'fit-content' : undefined,
                    maxWidth: '100%',
                    marginBottom: i === changes.length - 1 ? 0 : 6
                  }}
                >
                  <Group gap="xs" wrap="nowrap" align="center">
                    <Text size="sm" fw={500} style={{ fontVariantNumeric: 'tabular-nums' }}>
                      {isoDate(entry.date) ?? '일자 미상'}
                    </Text>
                    <Badge size="xs" variant="light" color="gray" radius="sm">
                      {entry.source === 'heading' ? '표제부' : '전유부'}
                    </Badge>
                    {highlighted ? (
                      <Badge size="xs" variant="light" color="warning" radius="sm">
                        확장 관련
                      </Badge>
                    ) : null}
                  </Group>
                  <Text size="sm" c="dimmed" mt={2} style={{ wordBreak: 'keep-all' }}>
                    {entry.reason}
                  </Text>
                </div>
              );
            })}
          </Stack>
        </SectionCard>
      ) : null}

      {/* 4. 대장 상세 — 접힘 기본. 전유부/표제부 원자료는 부차 정보로 강등. */}
      {hasRegisterDetail ? (
        <Accordion variant="separated" radius="lg" chevronPosition="right">
          <Accordion.Item value="register-detail">
            <Accordion.Control icon={<IconFileText size={18} aria-hidden />}>
              <Text size="sm" fw={600}>
                대장 상세 (전유부·표제부)
              </Text>
            </Accordion.Control>
            <Accordion.Panel>
              <Stack gap="lg">
                {exclusiveRows.length > 0 ? (
                  <Stack gap="xs">
                    <Text size="xs" fw={600} c="dimmed">
                      전유부(우리집)
                    </Text>
                    {exclusiveRows.map((row) => (
                      <DetailRow key={row.label} label={row.label} value={row.value} />
                    ))}
                  </Stack>
                ) : null}
                {buildingRows.length > 0 ? (
                  <Stack gap="xs">
                    <Text size="xs" fw={600} c="dimmed">
                      건물(표제부)
                    </Text>
                    {buildingRows.map((row) => (
                      <DetailRow key={row.label} label={row.label} value={row.value} />
                    ))}
                  </Stack>
                ) : null}
              </Stack>
            </Accordion.Panel>
          </Accordion.Item>
        </Accordion>
      ) : null}

      {/* 5. 발급 PDF 다운로드 */}
      {documents.length > 0 ? (
        <SectionCard
          accent="blueprint"
          icon={<IconFileText size={17} aria-hidden />}
          eyebrow="원본 문서"
          title="발급 대장 PDF"
        >
          <Stack gap="xs">
            {/* 버튼은 콘텐츠 폭으로 나란히(좁은 화면에선 줄바꿈) — Stack 풀폭 + space-between
                은 아이콘/라벨이 양끝으로 벌어져 어색하다(운영자 피드백 2026-07-14). */}
            <Group gap="xs">
              {documents.map((doc) => (
                <Button
                  key={doc.kind}
                  component="a"
                  href={doc.url ?? '#'}
                  target="_blank"
                  rel="noopener noreferrer"
                  variant="light"
                  color="jippin"
                  radius="md"
                  leftSection={<IconDownload size={16} />}
                >
                  {doc.kind === 'building_heading' ? '표제부 대장 PDF' : '전유부 대장 PDF'}
                </Button>
              ))}
            </Group>
            <Text size="xs" c="dimmed">
              다운로드 링크는 보안을 위해 일정 시간이 지나면 만료될 수 있어요.
            </Text>
          </Stack>
        </SectionCard>
      ) : null}

      {/* 6. 상담 인입 CTA (coral) — normal 을 제외한 모든 상태에서 노출. */}
      {cta ? (
        <SectionCard
          accent={accent}
          icon={<HeroIcon size={17} aria-hidden />}
          eyebrow="다음 단계"
          title={cta.title}
        >
          <Text size="sm" c="var(--jippin-brand-copy)" style={{ wordBreak: 'keep-all' }}>
            {cta.desc}
          </Text>
          {/* 전환 CTA 표준(CtaButton, 화면당 1회) — 이 리포트에서 coral 은 여기뿐. */}
          <CtaButton
            component={Link}
            href={homeCheckLeadHref(checkId, addressLabel)}
            mt="sm"
            w="fit-content"
            rightSection={<IconArrowRight size={16} />}
          >
            {cta.label}
          </CtaButton>
        </SectionCard>
      ) : null}

      {/* 7. 조회 참고 안내 — 이 리포트에 한정된 문구다.
          §4.6 법적 고지("본 서비스는 AI 기반 사전 검토 시스템입니다…")는 여기서 되풀이하지
          않는다. 전역 푸터(LegalNotice)가 모든 페이지에 항상 렌더하므로 리포트 화면에도
          그대로 노출돼 §4.6("리포트 화면은 문구를 포함한다")을 충족한다 — 같은 화면에 두 번
          찍히던 중복만 제거한 것이고, 문구 자체는 누락·변형하지 않았다. */}
      <Text className="a2ui-legal" style={{ wordBreak: 'keep-all' }}>
        {report.disclaimer}
      </Text>

      {/* 8. 다른 집 체크하기 — 내부 내비게이션은 next/link 로(전체 리로드 방지). */}
      <Group justify="center">
        <Anchor
          component={Link}
          href="/home-check/new"
          size="sm"
          c="var(--jippin-brand-primary)"
        >
          다른 집 체크하기 →
        </Anchor>
      </Group>
    </Stack>
  );
}

/** a2ui CardShell + CardHeader + 본문 패딩을 묶은 섹션 프레임(리포트 내부 재사용). */
function SectionCard({
  accent,
  icon,
  eyebrow,
  title,
  children
}: {
  accent: CardAccent;
  icon: ReactNode;
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  const titleId = useId();
  return (
    <CardShell accent={accent} labelledBy={titleId}>
      <CardHeader icon={icon} eyebrow={eyebrow} title={title} titleId={titleId} />
      <CardRule />
      {children}
    </CardShell>
  );
}

/**
 * 확장 등재 대조 카드 — 리포트의 핵심. 신고한 확장 부위별로 대장 변동사항 등재 여부를
 * 매칭해 보여 준다. extension_check 가 없으면(사용자 미입력) 부드러운 유도 프롬프트로 대체.
 */
function ExtensionDiagnosisCard({ report }: { report: HomeCheckReport }) {
  const ext = report.extension_check ?? null;

  // 미입력 → 소프트 프롬프트. 강조/coral 없이 담백하게 재입력을 안내한다.
  if (!ext) {
    return (
      <SectionCard
        accent="neutral"
        icon={<IconRulerMeasure size={17} aria-hidden />}
        eyebrow="확장 등재 대조"
        title="확장·개조한 공간이 있으셨나요?"
      >
        <Text size="sm" c="var(--jippin-brand-copy)" style={{ wordBreak: 'keep-all' }}>
          입력하시면 신고하신 확장이 건축물대장 변동사항에 등재돼 있는지 자동으로 대조해
          드려요.
        </Text>
        <Anchor
          component={Link}
          href="/home-check/new"
          size="sm"
          mt="sm"
          c="var(--jippin-brand-primary)"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
        >
          확장 정보 입력하고 다시 체크하기
          <IconChevronRight size={15} aria-hidden />
        </Anchor>
      </SectionCard>
    );
  }

  const reported = ext.reported_areas ?? [];
  const matched = ext.matched_areas ?? [];
  const unrecorded = ext.unrecorded_areas ?? [];

  const extAccent: CardAccent =
    ext.verdict === 'violation' ? 'danger' : ext.verdict === 'legal' ? 'success' : 'warning';

  return (
    <SectionCard
      accent={extAccent}
      icon={<IconRulerMeasure size={17} aria-hidden />}
      eyebrow="확장 등재 대조"
      title="신고한 확장 ↔ 대장 등재"
    >
      <Stack gap="md">
        {/* 신고 부위 ↔ 대장 등재를 행 단위로 맞대는 비교 표 — 배지 나열 + 상태 리스트의
            이중 나열을 대체한다(운영자 디자인 피드백 2026-07-14). */}
        {reported.length > 0 ? (
          <div
            role="table"
            aria-label="신고한 확장과 대장 등재 대조"
            style={{
              border: '1px solid var(--jippin-brand-border)',
              borderRadius: 12,
              overflow: 'hidden'
            }}
          >
            <div
              role="row"
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 28px 1.4fr',
                gap: 8,
                alignItems: 'center',
                padding: '0.5rem 0.75rem',
                background: 'var(--jippin-brand-surface)',
                borderBottom: '1px solid var(--jippin-brand-border)'
              }}
            >
              <Text component="span" role="columnheader" size="xs" fw={600} c="dimmed">
                신고한 확장
              </Text>
              <span aria-hidden />
              <Text component="span" role="columnheader" size="xs" fw={600} c="dimmed">
                대장 등재
              </Text>
            </div>
            {reported.map((area, idx) => {
              const isUnrecorded = unrecorded.includes(area);
              // 동의어(베란다↔발코니)로 matched 라벨이 신고 라벨과 다를 수 있다. legal 판정이고
              // 미등재가 아니면 등재로 본다(exact matched 포함에만 의존하지 않음, #row-synonym).
              const isMatched =
                !isUnrecorded && (matched.includes(area) || ext.verdict === 'legal');
              const tone = isMatched
                ? { color: 'var(--mantine-color-success-7)', Icon: IconCircleCheck, note: '대장 등재 확인' }
                : isUnrecorded
                  ? { color: 'var(--mantine-color-danger-7)', Icon: IconAlertTriangle, note: '대장 미등재' }
                  : { color: 'var(--mantine-color-gray-6)', Icon: IconHelpCircle, note: '대조 확인 필요' };
              const RowIcon = tone.Icon;
              return (
                <div
                  key={area}
                  role="row"
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 28px 1.4fr',
                    gap: 8,
                    alignItems: 'center',
                    padding: '0.625rem 0.75rem',
                    borderTop: idx > 0 ? '1px solid var(--jippin-brand-border)' : undefined
                  }}
                >
                  <Text role="cell" size="sm" fw={500} style={{ wordBreak: 'keep-all' }}>
                    {area}
                  </Text>
                  <span
                    aria-hidden
                    style={{
                      display: 'inline-flex',
                      justifyContent: 'center',
                      color: 'var(--mantine-color-gray-5)'
                    }}
                  >
                    <IconArrowRight size={15} />
                  </span>
                  <div
                    role="cell"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      color: tone.color,
                      minWidth: 0
                    }}
                  >
                    <RowIcon size={16} aria-hidden style={{ flexShrink: 0 }} />
                    <Text component="span" size="sm" fw={500} style={{ color: 'inherit' }}>
                      {tone.note}
                    </Text>
                  </div>
                </div>
              );
            })}
          </div>
        ) : null}

        {ext.reason ? (
          <Text size="sm" c="var(--jippin-brand-copy)" style={{ lineHeight: 1.6, wordBreak: 'keep-all' }}>
            {ext.reason}
          </Text>
        ) : null}

        <Text size="11px" c="dimmed" style={{ lineHeight: 1.4 }}>
          ※ 대장 변동사항 기준으로 자동 대조한 결과예요.
        </Text>
      </Stack>
    </SectionCard>
  );
}

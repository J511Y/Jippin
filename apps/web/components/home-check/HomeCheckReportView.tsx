'use client';

import { Accordion, Anchor, Badge, Button, Group, Stack, Text } from '@mantine/core';
import {
  IconAlertTriangle,
  IconArrowRight,
  IconCalendarStats,
  IconChevronRight,
  IconCircleCheck,
  IconClipboardCheck,
  IconDownload,
  IconFileText,
  IconHelpCircle,
  IconRulerMeasure
} from '@tabler/icons-react';
import type { CSSProperties, ReactNode } from 'react';
import { useId } from 'react';
import type { HomeCheckReport } from '@contracts/home-check';

import { CardHeader, CardRule, CardShell, type CardAccent } from '@/components/a2ui/cards/CardShell';
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

/**
 * AGENTS.md §4.6 법적 고지 — **절대 누락·변형 금지**. 리포트 화면(앱/미리보기/공유링크)에서
 * 문구 그대로 노출한다. report.disclaimer(조회 참고 안내)와 함께 표시한다.
 */
const LEGAL_NOTICE =
  '본 서비스는 AI 기반 사전 검토 시스템입니다. 최종 행위허가 여부는 관할 행정기관 판단에 따라 달라질 수 있습니다.';

/** tone → CardShell accent 레일 색 축. gray 는 neutral 로 매핑. */
const TONE_TO_ACCENT: Record<VerdictTone, CardAccent> = {
  danger: 'danger',
  warning: 'warning',
  success: 'success',
  gray: 'neutral'
};

type VerdictBannerVars = CSSProperties & {
  '--a2ui-verdict-surface': string;
  '--a2ui-verdict-border': string;
  '--a2ui-verdict-fg': string;
};

/** `.a2ui-verdict` 배너 색 묶음. tone 은 전부 Mantine 색 토큰(0/2/7 셰이드)로 환원. */
function verdictBannerVars(tone: VerdictTone): VerdictBannerVars {
  return {
    '--a2ui-verdict-surface': `var(--mantine-color-${tone}-0)`,
    '--a2ui-verdict-border': `var(--mantine-color-${tone}-2)`,
    '--a2ui-verdict-fg': `var(--mantine-color-${tone}-7)`
  };
}

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
  const changes = report.change_history ?? [];
  const documents = (report.documents ?? []).filter((d) => d.url);
  const cautionReasons = report.caution_reasons ?? [];
  const unrecordedAreas = ext?.unrecorded_areas ?? [];

  // '없어요'(확장 없음) 응답 → verdict=normal + ext.legal + 신고 부위 없음. 이때 "신고하신 확장도
  // 대장에 등재돼 있어요"는 틀린 카피다(확장을 신고하지 않았으므로). 무확장 전용 카피로 교체한다.
  const isNoExtensionLegal =
    verdict === 'normal' && ext?.verdict === 'legal' && (ext.reported_areas?.length ?? 0) === 0;
  const heroOneLiner = isNoExtensionLegal
    ? '위반표시가 없고, 확장·개조한 곳도 없다고 확인해 주셨어요.'
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
      {/* 1. VerdictHero — 두 축을 합친 4-상태 결론. 오늘 3중 알럿을 여기로 통합. */}
      <CardShell accent={accent} labelledBy={heroTitleId}>
        <div className="a2ui-card__head">
          <span className="a2ui-card__icon" aria-hidden>
            <IconClipboardCheck size={17} />
          </span>
          <span style={{ minWidth: 0 }}>
            <span className="a2ui-card__eyebrow">우리집 체크 결과</span>
            <span
              className="a2ui-card__title"
              id={heroTitleId}
              style={{ wordBreak: 'keep-all' }}
            >
              {addressLabel ?? '조회한 집'}
            </span>
          </span>
        </div>

        {/* 결론 배너 — 색 + 아이콘 + 라벨 셋으로 동시 전달(WCAG·색 단독 금지). */}
        <div
          className="a2ui-verdict"
          role="status"
          style={{ ...verdictBannerVars(meta.tone), marginTop: '0.75rem' }}
        >
          <span className="a2ui-verdict__icon">
            <HeroIcon size={18} aria-hidden />
          </span>
          <span className="a2ui-verdict__label">{meta.label}</span>
        </div>

        <Text
          size="sm"
          c="var(--jippin-brand-copy)"
          mt="md"
          style={{ lineHeight: 1.7, wordBreak: 'keep-all' }}
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
                    padding: highlighted ? '0.625rem 0.75rem 0.625rem 0.875rem' : '0.5rem 0 0.5rem 0.875rem',
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
                justify="space-between"
                leftSection={<IconDownload size={16} />}
              >
                {doc.kind === 'building_heading' ? '표제부 대장 PDF' : '전유부 대장 PDF'}
              </Button>
            ))}
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
          <Button
            component="a"
            href={homeCheckLeadHref(checkId, addressLabel)}
            color="coral"
            radius="md"
            mt="sm"
            w="fit-content"
            rightSection={<IconArrowRight size={16} />}
          >
            {cta.label}
          </Button>
        </SectionCard>
      ) : null}

      {/* 7. 면책 고정 노출 — §4.6 필수 법적 고지(누락 금지) + 조회 참고 안내 */}
      <Stack gap={4}>
        <Text className="a2ui-legal" fw={600} style={{ wordBreak: 'keep-all' }}>
          {LEGAL_NOTICE}
        </Text>
        <Text className="a2ui-legal" style={{ wordBreak: 'keep-all' }}>
          {report.disclaimer}
        </Text>
      </Stack>

      {/* 8. 다른 집 체크하기 */}
      <Group justify="center">
        <Anchor href="/home-check/new" size="sm" c="var(--jippin-brand-primary)">
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
        {reported.length > 0 ? (
          <Stack gap={6}>
            <Text size="xs" fw={600} c="dimmed">
              신고한 확장
            </Text>
            <Group gap="xs">
              {reported.map((area) => (
                <Badge key={area} variant="light" color="gray" radius="sm" size="md">
                  {area}
                </Badge>
              ))}
            </Group>
          </Stack>
        ) : null}

        {reported.length > 0 ? (
          <Stack gap={8}>
            {reported.map((area) => {
              const isMatched = matched.includes(area);
              const isUnrecorded = unrecorded.includes(area);
              const tone = isMatched
                ? { color: 'var(--mantine-color-success-7)', Icon: IconCircleCheck, note: '대장 등재 확인' }
                : isUnrecorded
                  ? { color: 'var(--mantine-color-danger-7)', Icon: IconAlertTriangle, note: '대장 미등재' }
                  : { color: 'var(--mantine-color-gray-6)', Icon: IconHelpCircle, note: '대조 확인 필요' };
              const RowIcon = tone.Icon;
              return (
                <Group key={area} gap="sm" wrap="nowrap" align="flex-start">
                  <span style={{ color: tone.color, flexShrink: 0, marginTop: 1 }}>
                    <RowIcon size={18} aria-hidden />
                  </span>
                  <div style={{ minWidth: 0 }}>
                    <Text size="sm" fw={500} style={{ wordBreak: 'keep-all' }}>
                      {area}
                    </Text>
                    <Text size="xs" style={{ color: tone.color }}>
                      {tone.note}
                    </Text>
                  </div>
                </Group>
              );
            })}
          </Stack>
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

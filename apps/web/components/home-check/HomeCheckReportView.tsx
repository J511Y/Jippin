'use client';

import {
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Divider,
  Group,
  Stack,
  Text,
  ThemeIcon,
  Title
} from '@mantine/core';
import {
  IconAlertTriangle,
  IconArrowRight,
  IconCalendarStats,
  IconDownload,
  IconFileText
} from '@tabler/icons-react';
import type { HomeCheckReport } from '@contracts/home-check';

import { homeCheckLeadHref } from '@/lib/home-check/lead-prefill';
import {
  formatArea,
  formatPrice,
  isoDate,
  jobAddressLabel,
  SIGNAL_META
} from '@/lib/home-check/display';

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
 * 우리집 체크 리포트 렌더 (CMP-DIRECT, ADR-0008).
 *
 * 종합 신호등 → 위반표시 배너 → 전유부 → 건물(표제부) → 변동 타임라인 → 공동주택가격 →
 * 발급 PDF → 면책 순. 톤: 위반/정상 단정 대신 "위반표시 있음/없음" 사실 기술.
 */
export function HomeCheckReportView({
  report,
  checkId
}: {
  report: HomeCheckReport;
  checkId: string;
}) {
  const signal = SIGNAL_META[report.signal];
  const addressLabel = jobAddressLabel({ report });
  const isViolation = report.violation.is_violation;
  const showConsultCta = report.signal === 'violation' || report.signal === 'caution';

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

  const changes = report.change_history ?? [];
  const prices = report.prices ?? [];
  const documents = (report.documents ?? []).filter((d) => d.url);
  const cautionReasons = report.caution_reasons ?? [];

  return (
    <Stack gap="lg">
      {/* 종합 신호등 */}
      <Card withBorder radius="lg" padding="xl">
        <Stack gap="sm" align="center" ta="center">
          <Text fz={48} lh={1} aria-hidden>
            {signal.emoji}
          </Text>
          <Badge color={signal.color} variant="light" size="lg" radius="sm">
            {signal.label}
          </Badge>
          {addressLabel ? (
            <Text fw={600} style={{ wordBreak: 'keep-all' }}>
              {addressLabel}
            </Text>
          ) : null}
          <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
            {signal.description}
          </Text>
        </Stack>
      </Card>

      {/* 위반표시 강조 배너 */}
      {isViolation ? (
        <Alert
          color="red"
          variant="light"
          radius="md"
          icon={<IconAlertTriangle size={18} />}
          title="위반건축물 표시가 확인됩니다"
        >
          <Stack gap={4}>
            <Text size="sm" style={{ wordBreak: 'keep-all' }}>
              건축물대장에 위반건축물(노란딱지) 표시가 있습니다.
            </Text>
            <Group gap="xs">
              {report.violation.exclusive ? (
                <Badge color="red" variant="outline" size="sm" radius="sm">
                  전유부(호) 표시
                </Badge>
              ) : null}
              {report.violation.heading ? (
                <Badge color="red" variant="outline" size="sm" radius="sm">
                  표제부(건물) 표시
                </Badge>
              ) : null}
            </Group>
          </Stack>
        </Alert>
      ) : null}

      {/* caution 사유 */}
      {cautionReasons.length > 0 ? (
        <Alert color="yellow" variant="light" radius="md" title="추가 확인이 필요해요">
          <Stack gap={4}>
            {cautionReasons.map((reason, i) => (
              <Group key={i} gap="xs" wrap="nowrap" align="flex-start">
                <Text size="sm" c="dimmed" style={{ flexShrink: 0 }}>
                  ·
                </Text>
                <Text size="sm" style={{ wordBreak: 'keep-all' }}>
                  {reason}
                </Text>
              </Group>
            ))}
          </Stack>
        </Alert>
      ) : null}

      {/* 전유부 정보 */}
      {exclusiveRows.length > 0 ? (
        <Card withBorder radius="lg" padding="lg">
          <Stack gap="sm">
            <Title order={2} fz="h4">
              전유부(우리집) 정보
            </Title>
            <Divider />
            <Stack gap="xs">
              {exclusiveRows.map((row) => (
                <DetailRow key={row.label} label={row.label} value={row.value} />
              ))}
            </Stack>
          </Stack>
        </Card>
      ) : null}

      {/* 건물(표제부) 정보 */}
      {buildingRows.length > 0 ? (
        <Card withBorder radius="lg" padding="lg">
          <Stack gap="sm">
            <Title order={2} fz="h4">
              건물(표제부) 정보
            </Title>
            <Divider />
            <Stack gap="xs">
              {buildingRows.map((row) => (
                <DetailRow key={row.label} label={row.label} value={row.value} />
              ))}
            </Stack>
          </Stack>
        </Card>
      ) : null}

      {/* 변동사항 타임라인 */}
      {changes.length > 0 ? (
        <Card withBorder radius="lg" padding="lg">
          <Stack gap="md">
            <Group gap="xs" wrap="nowrap" align="center">
              <ThemeIcon color="jippin" variant="light" size={24} radius="xl">
                <IconCalendarStats size={14} />
              </ThemeIcon>
              <Title order={2} fz="h4">
                변동사항 이력
              </Title>
            </Group>
            <Stack gap="md">
              {changes.map((entry, i) => (
                <Group
                  key={i}
                  gap="sm"
                  wrap="nowrap"
                  align="flex-start"
                  style={{
                    borderLeft: '2px solid var(--mantine-color-default-border)',
                    paddingLeft: 'var(--mantine-spacing-md)'
                  }}
                >
                  <Stack gap={4} style={{ flex: 1 }}>
                    <Group gap="xs" wrap="nowrap">
                      <Text size="sm" fw={500}>
                        {isoDate(entry.date) ?? '일자 미상'}
                      </Text>
                      <Badge size="xs" variant="light" color="gray" radius="sm">
                        {entry.source === 'heading' ? '표제부' : '전유부'}
                      </Badge>
                    </Group>
                    <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
                      {entry.reason}
                    </Text>
                  </Stack>
                </Group>
              ))}
            </Stack>
          </Stack>
        </Card>
      ) : null}

      {/* 공동주택가격 */}
      {prices.length > 0 ? (
        <Card withBorder radius="lg" padding="lg">
          <Stack gap="sm">
            <Title order={2} fz="h4">
              공동주택가격
            </Title>
            <Divider />
            <Stack gap="xs">
              {prices.map((price, i) => (
                <DetailRow
                  key={i}
                  label={isoDate(price.reference_date) ?? '기준일 미상'}
                  value={formatPrice(price.base_price)}
                />
              ))}
            </Stack>
          </Stack>
        </Card>
      ) : null}

      {/* 발급 PDF 다운로드 */}
      {documents.length > 0 ? (
        <Card withBorder radius="lg" padding="lg">
          <Stack gap="sm">
            <Group gap="xs" wrap="nowrap" align="center">
              <ThemeIcon color="jippin" variant="light" size={24} radius="xl">
                <IconFileText size={14} />
              </ThemeIcon>
              <Title order={2} fz="h4">
                발급 문서(PDF)
              </Title>
            </Group>
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
            </Stack>
            <Text size="xs" c="dimmed">
              다운로드 링크는 보안을 위해 일정 시간이 지나면 만료될 수 있어요.
            </Text>
          </Stack>
        </Card>
      ) : null}

      {/* 상담 인입 CTA — 위반/확인필요 결과에서만 */}
      {showConsultCta ? (
        <Card withBorder radius="lg" padding="lg" bg="var(--mantine-color-gray-0)">
          <Stack gap="sm">
            <Text fw={600} style={{ wordBreak: 'keep-all' }}>
              사용검사·위반 해소가 궁금하세요?
            </Text>
            <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
              위반표시 해소나 사용검사 절차는 전문가 상담으로 도와드려요. 조회한 주소가
              상담 신청서에 미리 채워집니다.
            </Text>
            <Button
              component="a"
              href={homeCheckLeadHref(checkId, addressLabel)}
              color="coral"
              radius="md"
              w="fit-content"
              rightSection={<IconArrowRight size={16} />}
            >
              사용검사 상담받기
            </Button>
          </Stack>
        </Card>
      ) : null}

      {/* 면책 고정 노출 */}
      <Alert color="gray" variant="light" radius="md">
        <Text size="xs" c="dimmed" style={{ wordBreak: 'keep-all' }}>
          {report.disclaimer}
        </Text>
      </Alert>

      <Group justify="center">
        <Anchor href="/home-check/new" size="sm" c="var(--jippin-brand-primary)">
          다른 집 체크하기 →
        </Anchor>
      </Group>
    </Stack>
  );
}

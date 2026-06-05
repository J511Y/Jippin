import { Badge, Button, Card, Group, Stack, Text, Title } from '@mantine/core';
import type { Metadata } from 'next';
import { LegalNotice } from '@/components/LegalNotice';

type ReportPageProps = {
  params: Promise<{ sessionId: string }>;
};

export const metadata: Metadata = {
  title: '사전검토 리포트'
};

export default async function SessionReportPage({ params }: ReportPageProps) {
  const { sessionId } = await params;

  return (
    <Stack gap="lg">
      <Stack gap="xs">
        <Badge color="jippin" variant="light" radius="sm" w="fit-content">
          리포트 미리보기 · {sessionId}
        </Badge>
        <Title order={1}>AI 사전검토 리포트</Title>
        <Text c="dimmed" size="sm" style={{ wordBreak: 'keep-all' }}>
          도면과 주소 분석을 바탕으로 정리한 사전 판단 결과입니다. 최종 행위허가는
          관할 기관 판단에 따라 달라질 수 있어요.
        </Text>
      </Stack>

      <Card withBorder radius="md" padding="md">
        <Stack gap="sm">
          <Group justify="space-between">
            <Text fw={600}>판단 결과</Text>
            <Badge color="success" variant="filled">
              조건부 가능
            </Badge>
          </Group>
          <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
            대상 벽은 비내력벽일 가능성이 높으나, 일부 배관 간섭 구간에 대해 현장
            확인이 필요합니다. (placeholder 내용)
          </Text>
        </Stack>
      </Card>

      <Card withBorder radius="md" padding="md">
        <Stack gap="xs">
          <Text fw={600}>주요 위험 구간</Text>
          <Text size="sm" c="dimmed">
            · 배수 배관 인접 (예시)
          </Text>
          <Text size="sm" c="dimmed">
            · 콘센트/전기 라인 인접 (예시)
          </Text>
        </Stack>
      </Card>

      {/* AGENTS.md §4.6: 리포트 화면 안에 inline LegalNotice 를 보장. */}
      <LegalNotice variant="inline" />

      <Stack gap="sm">
        <Button
          component="a"
          href={`/leads/new?fromSession=${sessionId}`}
          size="lg"
          color="coral"
          radius="md"
          fullWidth
        >
          전문가 상담 신청하기
        </Button>
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

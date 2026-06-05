import { Badge, Button, Card, Stack, Text, Title } from '@mantine/core';
import type { Metadata } from 'next';

type ContactDetailProps = {
  params: Promise<{ contactId: string }>;
};

export const metadata: Metadata = {
  title: '상담 상세'
};

export default async function ContactDetailPage({ params }: ContactDetailProps) {
  const { contactId } = await params;

  return (
    <Stack gap="lg">
      <Stack gap="xs">
        <Badge color="jippin" variant="light" radius="sm" w="fit-content">
          상담 ID · {contactId}
        </Badge>
        <Title order={1}>상담 진행 상세</Title>
        <Text c="dimmed" size="sm" style={{ wordBreak: 'keep-all' }}>
          담당자와의 메모, 진행 단계, 첨부 파일을 한 화면에서 확인할 수 있어요.
        </Text>
      </Stack>

      <Card withBorder radius="md" padding="md">
        <Stack gap="sm">
          <Text fw={600}>진행 단계</Text>
          <Stack gap="xs">
            <Text size="sm">· 1. 신청 접수 — 완료</Text>
            <Text size="sm">· 2. 담당자 배정 — 완료</Text>
            <Text size="sm">· 3. 현장 방문 — 예정</Text>
            <Text size="sm" c="dimmed">
              · 4. 행위허가 검토 — 대기
            </Text>
          </Stack>
        </Stack>
      </Card>

      <Card withBorder radius="md" padding="md">
        <Stack gap="sm">
          <Text fw={600}>최근 메모</Text>
          <Text size="sm" c="dimmed">
            placeholder · 담당자가 남긴 메모와 첨부 미리보기가 이 영역에 표시됩니다.
          </Text>
        </Stack>
      </Card>

      <Button
        component="a"
        href="/contacts"
        variant="subtle"
        color="jippin"
        radius="md"
        fullWidth
      >
        상담 목록으로
      </Button>
    </Stack>
  );
}

import { Card, Stack, Text, Title } from '@mantine/core';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '개인정보처리방침'
};

export default function PrivacyPage() {
  return (
    <Stack gap="lg">
      <Stack gap="xs">
        <Title order={1}>개인정보처리방침</Title>
        <Text c="dimmed" size="sm">
          MVP placeholder 개인정보처리방침입니다. 정식 본문은 법무 검토 후 게재됩니다.
        </Text>
      </Stack>

      <Card withBorder radius="md" padding="md">
        <Stack gap="sm">
          <Text fw={600}>1. 수집 항목</Text>
          <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
            상담/사전검토 요청 시 이름, 연락처, 대상 주소, 도면 파일을 수집할 수
            있습니다. (placeholder)
          </Text>
          <Text fw={600}>2. 이용 목적</Text>
          <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
            AI 사전검토 제공, 상담 진행, 행위허가 후속 절차 안내에 사용됩니다.
            (placeholder)
          </Text>
          <Text fw={600}>3. 보관 기간</Text>
          <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
            관계 법령이 정한 기간 또는 이용자 요청 시까지 보관됩니다. (placeholder)
          </Text>
        </Stack>
      </Card>
    </Stack>
  );
}

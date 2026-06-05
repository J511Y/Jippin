import { Card, Stack, Text, Title } from '@mantine/core';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '이용약관'
};

export default function TermsPage() {
  return (
    <Stack gap="lg">
      <Stack gap="xs">
        <Title order={1}>이용약관</Title>
        <Text c="dimmed" size="sm">
          MVP placeholder 약관 화면입니다. 정식 약관 본문은 법무 검토 후 게재됩니다.
        </Text>
      </Stack>

      <Card withBorder radius="md" padding="md">
        <Stack gap="sm">
          <Text fw={600}>제1조 (목적)</Text>
          <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
            본 약관은 집핀이 제공하는 비내력벽 철거 사전검토 서비스의 이용 조건을
            정합니다. (placeholder)
          </Text>
          <Text fw={600}>제2조 (서비스의 성격)</Text>
          <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
            집핀의 사전검토 결과는 참고용이며, 최종 행위허가는 관할 기관 판단을
            따릅니다. (placeholder)
          </Text>
        </Stack>
      </Card>
    </Stack>
  );
}

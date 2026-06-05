import { Anchor, Button, Card, Stack, Text, Title } from '@mantine/core';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '상담 신청'
};

export default function LeadsPage() {
  return (
    <Stack gap="lg">
      <Stack gap="xs">
        <Title order={1}>상담 신청</Title>
        <Text c="dimmed" size="sm" style={{ wordBreak: 'keep-all' }}>
          사전검토 없이 전문가 상담을 바로 신청할 수 있어요. 신청한 상담은{' '}
          <Anchor href="/contacts" c="var(--jippin-brand-primary)">
            상담 진행
          </Anchor>{' '}
          에서 관리합니다.
        </Text>
      </Stack>

      <Card withBorder radius="md" padding="md">
        <Stack gap="sm">
          <Text fw={600}>이런 분께 권해요</Text>
          <Text size="sm" c="dimmed">
            · 도면 없이 위치/사진만 있는 경우
          </Text>
          <Text size="sm" c="dimmed">
            · 사전검토 리포트만으로 판단이 어려운 경우
          </Text>
          <Text size="sm" c="dimmed">
            · 행위허가 신청까지 한 번에 진행하고 싶은 경우
          </Text>
        </Stack>
      </Card>

      <Button
        component="a"
        href="/leads/new"
        size="lg"
        color="coral"
        radius="md"
        fullWidth
      >
        상담 신청하기
      </Button>

      <Card withBorder radius="md" padding="md" bg="var(--jippin-brand-surface)">
        <Stack gap="xs">
          <Text fw={600}>이미 신청했나요?</Text>
          <Text size="sm" c="dimmed">
            신청한 상담의 진행 상태는 상담 탭에서 확인할 수 있어요.
          </Text>
          <Button
            component="a"
            href="/contacts"
            variant="subtle"
            color="jippin"
            radius="md"
            w="fit-content"
            mt="xs"
          >
            상담 진행 보기 →
          </Button>
        </Stack>
      </Card>
    </Stack>
  );
}

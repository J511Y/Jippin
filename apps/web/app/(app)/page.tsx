import { Badge, Button, Card, Group, Stack, Text, Title } from '@mantine/core';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '집핀 — 비내력벽 철거 사전검토 AI'
};

export default function HomePage() {
  return (
    <Stack gap="xl">
      <Stack gap="xs">
        <Badge color="jippin" variant="light" radius="sm" w="fit-content">
          MVP · 모바일 사전검토
        </Badge>
        <Title order={1} style={{ wordBreak: 'keep-all' }}>
          비내력벽 철거, 신청 전에 1분 사전검토
        </Title>
        <Text c="dimmed" style={{ wordBreak: 'keep-all' }}>
          도면과 주소만 있으면 AI 가 행위허가 가능성을 사전검토합니다. 결과를 보고
          전문가 상담으로 바로 전환할 수 있습니다.
        </Text>
      </Stack>

      <Group grow>
        <Button
          component="a"
          href="/sessions/new"
          size="lg"
          color="jippin"
          radius="md"
        >
          사전검토 시작
        </Button>
        <Button
          component="a"
          href="/leads/new"
          size="lg"
          color="coral"
          variant="light"
          radius="md"
        >
          상담 바로 신청
        </Button>
      </Group>

      <Stack gap="md">
        <Title order={2}>이렇게 진행돼요</Title>
        <Stack gap="sm">
          <Card withBorder radius="md" padding="md">
            <Group gap="sm" align="flex-start" wrap="nowrap">
              <Badge color="jippin" variant="filled" radius="sm">
                1
              </Badge>
              <Stack gap={2}>
                <Text fw={600}>주소와 도면 업로드</Text>
                <Text size="sm" c="dimmed">
                  익명으로 시작할 수 있어요. 로그인 없이 사전검토를 받아보세요.
                </Text>
              </Stack>
            </Group>
          </Card>
          <Card withBorder radius="md" padding="md">
            <Group gap="sm" align="flex-start" wrap="nowrap">
              <Badge color="jippin" variant="filled" radius="sm">
                2
              </Badge>
              <Stack gap={2}>
                <Text fw={600}>AI 사전검토 리포트 미리 보기</Text>
                <Text size="sm" c="dimmed">
                  철거 가능성, 위험 구간, 법적 고지를 한 화면에서 확인합니다.
                </Text>
              </Stack>
            </Group>
          </Card>
          <Card withBorder radius="md" padding="md">
            <Group gap="sm" align="flex-start" wrap="nowrap">
              <Badge color="jippin" variant="filled" radius="sm">
                3
              </Badge>
              <Stack gap={2}>
                <Text fw={600}>필요하면 전문가 상담으로 전환</Text>
                <Text size="sm" c="dimmed">
                  사전검토 결과를 첨부해 상담을 신청하면 진행 상태를 추적할 수 있어요.
                </Text>
              </Stack>
            </Group>
          </Card>
        </Stack>
      </Stack>

      <Card withBorder radius="md" padding="lg" bg="var(--jippin-brand-surface)">
        <Stack gap="xs">
          <Text fw={600}>가격이 궁금하다면</Text>
          <Text size="sm" c="dimmed">
            상담 상품과 사전검토 옵션은 가격 페이지에서 확인할 수 있어요.
          </Text>
          <Button
            component="a"
            href="/prices"
            variant="subtle"
            color="jippin"
            radius="md"
            w="fit-content"
            mt="xs"
          >
            가격 확인하기 →
          </Button>
        </Stack>
      </Card>
    </Stack>
  );
}

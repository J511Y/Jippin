import {
  Anchor,
  Button,
  Card,
  Group,
  Stack,
  Text,
  ThemeIcon,
  Title
} from '@mantine/core';
import { IconArrowRight, IconCheck } from '@tabler/icons-react';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '상담 신청'
};

const FOR_WHOM = [
  '도면 없이 위치·사진만 있는 경우',
  '사전검토 리포트만으로 판단이 어려운 경우',
  '행위허가 신청까지 한 번에 진행하고 싶은 경우'
];

export default function LeadsPage() {
  return (
    <Stack gap="xl">
      <Stack gap="xs">
        <Title order={1} fz="h1">
          전문가 상담 신청
        </Title>
        <Text c="dimmed" size="sm" style={{ wordBreak: 'keep-all' }}>
          사전검토 없이 전문가 상담을 바로 신청할 수 있어요. 신청한 상담은{' '}
          <Anchor href="/mypage?tab=consultations" c="var(--jippin-brand-primary)">
            상담 진행
          </Anchor>
          에서 관리합니다.
        </Text>
      </Stack>

      <Card withBorder radius="lg" padding="xl">
        <Stack gap="md">
          <Text fw={600}>이런 분께 권해요</Text>
          <Stack gap="sm">
            {FOR_WHOM.map((item) => (
              <Group key={item} gap="xs" wrap="nowrap" align="center">
                <ThemeIcon color="jippin" variant="light" size={22} radius="xl">
                  <IconCheck size={14} />
                </ThemeIcon>
                <Text size="sm">{item}</Text>
              </Group>
            ))}
          </Stack>
        </Stack>
      </Card>

      <Button
        component="a"
        href="/leads/new"
        size="lg"
        color="coral"
        radius="md"
        fullWidth
        rightSection={<IconArrowRight size={18} />}
      >
        상담 신청서 작성하기
      </Button>

      <Card withBorder radius="lg" padding="lg">
        <Stack gap="xs">
          <Text fw={600}>이미 신청했나요?</Text>
          <Text size="sm" c="dimmed">
            신청한 상담의 진행 상태는 상담 진행에서 확인할 수 있어요.
          </Text>
          <Button
            component="a"
            href="/mypage?tab=consultations"
            variant="subtle"
            color="jippin"
            radius="md"
            w="fit-content"
            mt={4}
          >
            상담 진행 보기 →
          </Button>
        </Stack>
      </Card>
    </Stack>
  );
}

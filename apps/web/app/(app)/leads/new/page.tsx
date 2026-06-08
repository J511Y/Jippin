import {
  Anchor,
  Button,
  Card,
  Group,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title
} from '@mantine/core';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '상담 신청서 작성'
};

export default function NewLeadPage() {
  return (
    <Stack gap="xl">
      <Stack gap="xs">
        <Title order={1} fz="h1">
          전문가 상담 신청
        </Title>
        <Text c="dimmed" size="sm" style={{ wordBreak: 'keep-all' }}>
          담당 전문가가 영업일 기준 1일 이내에 연락드려요. 진행 중인 사전검토가 있으면
          리포트가 자동으로 첨부됩니다.
        </Text>
      </Stack>

      <Card withBorder radius="lg" padding="xl">
        <Stack gap="md">
          <TextInput
            label="연락 가능한 이름"
            placeholder="예: 홍길동"
            radius="md"
            size="md"
            withAsterisk
          />
          <TextInput
            label="연락처"
            placeholder="010-0000-0000 또는 이메일"
            radius="md"
            size="md"
            withAsterisk
          />
          <TextInput
            label="대상 주소"
            placeholder="예: 서울 강남구 ○○로 12"
            radius="md"
            size="md"
          />
          <Textarea
            label="상담 메모"
            placeholder="어떤 부분이 궁금하신가요? (예: 거실을 넓히려고 주방 옆 벽을 헐 수 있는지)"
            minRows={4}
            autosize
            radius="md"
            size="md"
          />
          <Button size="md" color="coral" radius="md" fullWidth mt="xs">
            상담 신청하기
          </Button>
          <Text size="xs" c="dimmed" ta="center" style={{ wordBreak: 'keep-all' }}>
            신청 시{' '}
            <Anchor href="/terms" size="xs" c="var(--jippin-brand-primary)">
              이용약관
            </Anchor>{' '}
            및{' '}
            <Anchor href="/privacy" size="xs" c="var(--jippin-brand-primary)">
              개인정보처리방침
            </Anchor>
            에 동의하는 것으로 간주됩니다.
          </Text>
        </Stack>
      </Card>

      <Group justify="flex-end">
        <Button
          component="a"
          href="/contacts"
          variant="subtle"
          color="jippin"
          radius="md"
        >
          이미 신청했나요? 상담 진행 보기 →
        </Button>
      </Group>
    </Stack>
  );
}

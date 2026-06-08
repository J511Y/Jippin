import { Anchor, Button, Group, Stack, Text, Title } from '@mantine/core';
import type { Metadata } from 'next';
import { ConsultationLeadForm } from '@/components/leads/ConsultationLeadForm';

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
          담당 전문가가 영업일 기준 1일 이내에 연락드려요. 로그인 없이도 신청할 수 있어요.
        </Text>
      </Stack>

      <ConsultationLeadForm />

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

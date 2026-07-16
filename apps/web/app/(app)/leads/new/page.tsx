import { Anchor, Button, Group, Stack, Text } from '@mantine/core';
import { IconArrowRight } from '@tabler/icons-react';
import type { Metadata } from 'next';
import { ConsultationLeadForm } from '@/components/leads/ConsultationLeadForm';
import { PageColumn, PageHeader } from '@/components/ui';

export const metadata: Metadata = {
  title: '상담 신청서 작성'
};

export default function NewLeadPage() {
  return (
    // 단일 입력 폼 페이지 — lg(1140px) 컨테이너에서 폼이 늘어지지 않게
    // 폼 표준 폭(560px) 컬럼으로 좁힌다.
    <PageColumn width="form">
      <PageHeader
        title="전문가 상담 신청"
        subtitle="담당 전문가가 영업일 기준 1일 이내에 연락드려요. 로그인 없이도 신청할 수 있어요."
      />

      <Stack gap="xl">
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
          {/* 서버 컴포넌트라 component={Link} 는 SSG 프리렌더가 깨져 component="a" 유지. */}
          <Button
            component="a"
            href="/mypage?tab=consultations"
            variant="subtle"
            color="jippin"
            rightSection={<IconArrowRight size={16} aria-hidden />}
          >
            이미 신청했나요? 상담 진행 보기
          </Button>
        </Group>
      </Stack>
    </PageColumn>
  );
}

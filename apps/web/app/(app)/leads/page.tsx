import {
  Anchor,
  Button,
  Card,
  Group,
  Stack,
  Text,
  ThemeIcon
} from '@mantine/core';
import { IconArrowRight, IconCheck } from '@tabler/icons-react';
import type { Metadata } from 'next';

import { LeadCtaButton } from '@/components/analytics/LeadCtaButton';
import { PageColumn, PageHeader } from '@/components/ui';

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
    // 상담 인입 퍼널 페이지 — lg(1140px) 컨테이너 그대로면 카드·CTA 가 과하게
    // 늘어나므로 폼 폭(560px) 컬럼으로 좁힌다(/leads/new 와 동일 폭 유지).
    <PageColumn width="form">
      <PageHeader
        title="전문가 상담 신청"
        subtitle={
          <>
            사전검토 없이 전문가 상담을 바로 신청할 수 있어요. 신청한 상담은{' '}
            <Anchor href="/mypage?tab=consultations" c="var(--jippin-brand-primary)">
              상담 진행
            </Anchor>
            에서 관리합니다.
          </>
        }
      />

      <Stack gap="xl">
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

        {/* 이 화면 유일한 전환 CTA(coral) — 퍼널 진입 버튼이라 lg 로 강조한다. */}
        <LeadCtaButton
          cta="leads_list"
          size="lg"
          color="coral"
          fw={700}
          fullWidth
          rightSection={<IconArrowRight size={18} />}
        >
          상담 신청서 작성하기
        </LeadCtaButton>

        <Card withBorder radius="lg" padding="lg">
          <Stack gap="xs">
            <Text fw={600}>이미 신청했나요?</Text>
            <Text size="sm" c="dimmed">
              신청한 상담의 진행 상태는 상담 진행에서 확인할 수 있어요.
            </Text>
            {/* 서버 컴포넌트라 component={Link} 는 SSG 프리렌더가 깨져 component="a" 유지. */}
            <Button
              component="a"
              href="/mypage?tab=consultations"
              variant="subtle"
              color="jippin"
              w="fit-content"
              mt={4}
              rightSection={<IconArrowRight size={16} aria-hidden />}
            >
              상담 진행 보기
            </Button>
          </Stack>
        </Card>
      </Stack>
    </PageColumn>
  );
}

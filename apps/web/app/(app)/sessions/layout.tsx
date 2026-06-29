import { Card, Stack, Text, ThemeIcon } from '@mantine/core';
import { IconSparkles } from '@tabler/icons-react';
import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { LeadCtaButton } from '@/components/analytics/LeadCtaButton';

/**
 * `/sessions/*` 는 개인 사전검토 워크플로우(주소·도면·판정)라 크롤러 색인 대상이 아니다.
 * 세션 상세/리포트 URL 이 공유·노출돼도 색인되지 않도록 라우트 그룹 전체에 noindex 를
 * 건다(클라이언트 페이지는 metadata 를 export 할 수 없으므로 서버 layout 에서 보장).
 */
export const metadata: Metadata = {
  robots: { index: false, follow: false }
};

// AI 분석을 구동하는 에이전트가 꺼져 있으면 세션 생성→리포트가 dead workflow 가 된다
// (도면을 올려도 분석이 안 돌아 리포트가 영영 NOT_READY). 그 빌드에선 전체 플로우를
// 노출하지 않고 안내 + 상담 인입으로 대체한다(#gate-when-agent-disabled).
const AGENT_ENABLED = process.env.NEXT_PUBLIC_AGENT_ENABLED === 'true';

export default function SessionsLayout({ children }: { children: ReactNode }) {
  if (!AGENT_ENABLED) {
    return (
      <Stack align="center" justify="center" mih="min(60vh, 520px)" px="md">
        <Card shadow="sm" radius="lg" padding="xl" withBorder maw={440} w="100%">
          <Stack align="center" gap="md">
            <ThemeIcon size={56} radius="xl" variant="light" color="jippin">
              <IconSparkles size={28} />
            </ThemeIcon>
            <Stack gap={6}>
              <Text fw={700} fz="xl" ta="center" style={{ wordBreak: 'keep-all' }}>
                AI 사전검토, 마무리 단계예요
              </Text>
              <Text size="sm" c="dimmed" ta="center" style={{ wordBreak: 'keep-all' }}>
                대화형 검토 엔진을 다듬고 있어요. 지금은 전문가가 직접 사전검토부터
                행위허가까지 도와드립니다.
              </Text>
            </Stack>
            <LeadCtaButton cta="sessions_gate" color="coral" size="md" radius="md" fullWidth>
              전문가 상담 신청하기
            </LeadCtaButton>
          </Stack>
        </Card>
      </Stack>
    );
  }
  return <>{children}</>;
}

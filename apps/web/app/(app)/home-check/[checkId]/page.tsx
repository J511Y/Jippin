import { Stack, Text, Title } from '@mantine/core';
import type { Metadata } from 'next';

import { HomeCheckResultClient } from '@/components/home-check/HomeCheckResultClient';

type HomeCheckResultPageProps = {
  params: Promise<{ checkId: string }>;
};

export const metadata: Metadata = {
  title: '우리집 체크 결과',
  // 잡 단위 결과는 개인 조회 결과라 색인하지 않는다.
  robots: { index: false, follow: false }
};

export default async function HomeCheckResultPage({ params }: HomeCheckResultPageProps) {
  const { checkId } = await params;

  return (
    <Stack gap="lg">
      <Stack gap="xs">
        <Title order={1} fz="h1" style={{ wordBreak: 'keep-all' }}>
          우리집 체크 결과
        </Title>
        <Text c="dimmed" size="sm" style={{ wordBreak: 'keep-all' }}>
          건축물대장(전유부·표제부) 조회 결과예요.
        </Text>
      </Stack>

      <HomeCheckResultClient checkId={checkId} />
    </Stack>
  );
}

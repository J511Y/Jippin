import { Stack, Text, Title } from '@mantine/core';
import type { Metadata } from 'next';

import { HomeCheckNewForm } from '@/components/home-check/HomeCheckNewForm';

export const metadata: Metadata = {
  title: '내 집 체크 시작',
  // 시작 폼은 랜딩(`/home-check`)과 주제가 같은 thin/중복 콘텐츠라 색인하지 않고
  // canonical 을 랜딩으로 통합한다. follow 는 살려 내부 크롤 경로는 유지.
  robots: { index: false, follow: true },
  alternates: { canonical: '/home-check' }
};

export default function HomeCheckNewPage() {
  return (
    <Stack gap="xl">
      <Stack gap="xs">
        <Title order={1} fz="h1" style={{ wordBreak: 'keep-all' }}>
          내 집 체크 시작
        </Title>
        <Text c="dimmed" size="sm" style={{ wordBreak: 'keep-all' }}>
          조회할 집합건물의 주소와 동·호를 입력하면 건축물대장(전유부·표제부)을 조회해
          위반표시·변동 등재 여부를 알려드려요. 로그인 없이도 이용할 수 있어요.
        </Text>
      </Stack>

      <HomeCheckNewForm />
    </Stack>
  );
}

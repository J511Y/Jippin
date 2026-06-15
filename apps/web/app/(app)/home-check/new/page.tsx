import { Stack, Text, Title } from '@mantine/core';
import type { Metadata } from 'next';

import { HomeCheckNewForm } from '@/components/home-check/HomeCheckNewForm';

export const metadata: Metadata = {
  title: '내 집 체크 시작',
  // 조회 결과 페이지(잡 단위)는 색인 대상이 아니며, 시작 폼은 색인 무방하나 canonical 만 둔다.
  alternates: { canonical: '/home-check/new' }
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

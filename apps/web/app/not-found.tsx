import { Button } from '@mantine/core';
import { IconArrowRight, IconHome } from '@tabler/icons-react';
import type { Metadata } from 'next';
import { ErrorState } from '@/components/ErrorState';

/**
 * 전역 404. 없는 라우트 진입 또는 `notFound()` 호출 시 노출된다.
 *
 * 서버 컴포넌트(정적 프리렌더)이므로 내부 링크는 Mantine `component={Link}` 대신
 * 네이티브 `component="a"` 를 쓴다(RSC 프리렌더 비호환 회피).
 */

export const metadata: Metadata = {
  title: '페이지를 찾을 수 없어요',
  robots: { index: false, follow: false }
};

export default function NotFound() {
  return (
    <ErrorState
      kind="notfound"
      title="페이지를 찾을 수 없어요"
      description="요청하신 주소가 변경되었거나 더 이상 존재하지 않습니다."
      actions={
        <>
          <Button
            component="a"
            href="/"
            color="jippin"
            size="md"
            radius="md"
            fullWidth
            leftSection={<IconHome size={18} />}
          >
            홈으로 가기
          </Button>
          <Button
            component="a"
            href="/sessions"
            variant="subtle"
            color="jippin"
            size="sm"
            radius="md"
            fullWidth
            rightSection={<IconArrowRight size={16} />}
          >
            사전검토 시작하기
          </Button>
        </>
      }
    />
  );
}

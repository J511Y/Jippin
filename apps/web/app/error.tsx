'use client';

import { Button } from '@mantine/core';
import { IconHome, IconLogin2, IconRefresh } from '@tabler/icons-react';
import Link from 'next/link';
import { useEffect } from 'react';
import { ErrorState } from '@/components/ErrorState';
import { resolveErrorContent } from '@/lib/api/error-content';

/**
 * 라우트 세그먼트 에러 경계. 렌더 중 던져진 예외(서버 액션·data fetch 의 ApiError 포함)를
 * 잡아 브랜드 화면으로 노출한다. `ApiError.status` 를 읽어 401/403(로그인) · 404(홈) ·
 * 5xx/네트워크(재시도)로 CTA 를 분기한다.
 *
 * 루트 레이아웃 자체에서 난 에러는 이 경계가 잡지 못하므로 `global-error.tsx` 가 폴백한다.
 */

export default function RouteError({
  error,
  reset
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // 개발 콘솔/서버 로그에 원본을 남긴다. digest 는 서버 측 로그와 상관관계를 맺는 키.
    console.error('[route-error]', error);
  }, [error]);

  const { kind, title, message, retryable, apiError } = resolveErrorContent(error);
  const requestId = apiError.requestId;

  const homeButton = (
    <Button
      component={Link}
      href="/"
      variant="subtle"
      color="jippin"
      size="sm"
      radius="md"
      fullWidth
      leftSection={<IconHome size={16} />}
    >
      홈으로 가기
    </Button>
  );

  let primary: React.ReactNode = null;
  if (kind === 'auth') {
    primary = (
      <Button
        component={Link}
        href="/login"
        color="jippin"
        size="md"
        radius="md"
        fullWidth
        leftSection={<IconLogin2 size={18} />}
      >
        로그인하기
      </Button>
    );
  } else if (retryable) {
    primary = (
      <Button
        onClick={reset}
        color="jippin"
        size="md"
        radius="md"
        fullWidth
        leftSection={<IconRefresh size={18} />}
      >
        다시 시도
      </Button>
    );
  }

  return (
    <ErrorState
      kind={kind}
      title={title}
      description={message}
      requestId={requestId}
      actions={
        <>
          {primary}
          {homeButton}
        </>
      }
    />
  );
}

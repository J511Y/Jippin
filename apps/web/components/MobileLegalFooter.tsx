'use client';

import { Box } from '@mantine/core';
import { usePathname } from 'next/navigation';

import { LegalNotice } from '@/components/LegalNotice';
import { isChatRoute } from '@/components/SiteShell';

/**
 * 모바일(<sm) 전용 compact 법적 푸터 — 사업자 표기 상시 노출(표시 의무).
 *
 * 채팅 라우트는 헤더 아래를 100dvh 로 '정확히' 채우고 overflow:hidden 이라, 여기에
 * 푸터를 더하면 body 가 넘쳐 sticky 입력 도크가 페이지 스크롤로 밀려 화면 밖으로
 * 사라진다. 그래서 채팅에서는 렌더하지 않는다(풀 표기는 햄버거 Drawer 에 계속 존재).
 *
 * layout.tsx(서버 컴포넌트)는 pathname 을 모르므로 이 클라이언트 래퍼가 판정을 맡는다.
 */
export function MobileLegalFooter() {
  const pathname = usePathname() ?? '/';
  if (isChatRoute(pathname)) return null;
  return (
    <Box hiddenFrom="sm">
      <LegalNotice variant="compact" />
    </Box>
  );
}

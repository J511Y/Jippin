import type { ReactNode } from 'react';
import { SiteShell } from '@/components/SiteShell';

/**
 * 인증 화면(/login 등)도 앱과 동일한 헤더(SiteShell)를 공유한다.
 * 헤더의 브랜드 로고가 홈 진입점을 겸하므로 페이지 내부의 별도 "홈으로" 링크는 두지 않는다.
 */
export default function AuthLayout({ children }: { children: ReactNode }) {
  return <SiteShell>{children}</SiteShell>;
}

import type { Metadata } from 'next';
import type { ReactNode } from 'react';

/**
 * `/sessions/*` 는 개인 사전검토 워크플로우(주소·도면·판정)라 크롤러 색인 대상이 아니다.
 * 세션 상세/리포트 URL 이 공유·노출돼도 색인되지 않도록 라우트 그룹 전체에 noindex 를
 * 건다(클라이언트 페이지는 metadata 를 export 할 수 없으므로 서버 layout 에서 보장).
 */
export const metadata: Metadata = {
  robots: { index: false, follow: false }
};

export default function SessionsLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}

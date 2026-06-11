import type { Metadata } from 'next';

import { MyPageClient } from './mypage-client';

export const metadata: Metadata = {
  title: '마이페이지',
  robots: { index: false, follow: false }
};

export default function MyPage() {
  return <MyPageClient />;
}

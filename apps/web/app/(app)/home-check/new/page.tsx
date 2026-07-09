import type { Metadata } from 'next';

import { HomeCheckFunnel } from '@/components/home-check/HomeCheckFunnel';

export const metadata: Metadata = {
  title: '내 집 체크 시작',
  // 시작 화면은 랜딩(`/home-check`)과 주제가 같은 thin/중복 콘텐츠라 색인하지 않고
  // canonical 을 랜딩으로 통합한다. follow 는 살려 내부 크롤 경로는 유지.
  robots: { index: false, follow: true },
  alternates: { canonical: '/home-check' }
};

export default function HomeCheckNewPage() {
  // 한 화면에 한 질문(토스/삼쩜삼식 퍼널). 페이지 타이틀/설명은 퍼널 인트로가 대신한다.
  return <HomeCheckFunnel />;
}

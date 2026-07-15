import type { Metadata } from 'next';

import { HomeCheckResultClient } from '@/components/home-check/HomeCheckResultClient';
import { PageColumn, PageHeader } from '@/components/ui';
import { fetchQuizzes } from '@/lib/quiz';

type HomeCheckResultPageProps = {
  params: Promise<{ checkId: string }>;
};

export const metadata: Metadata = {
  title: '우리집 체크 결과',
  // 잡 단위 결과는 개인 조회 결과라 색인하지 않되, follow 는 살려 공개 페이지로의
  // 내부 크롤 경로는 유지한다.
  robots: { index: false, follow: true }
};

export default async function HomeCheckResultPage({ params }: HomeCheckResultPageProps) {
  const { checkId } = await params;
  // 대기 화면 퀴즈 — 서버에서 ISR 로 받아 클라이언트에 주입한다(실패 시 정적 폴백이
  // 반환되므로 대기 화면 콘텐츠는 API 가용성과 무관하게 항상 있다).
  const quizzes = await fetchQuizzes();

  return (
    // 컨테이너가 전 페이지 lg(1140px)로 통일돼, 리포트 카드 열은 PageColumn(prose
    // 720px)으로 좁힌다 — 판정·타임라인 카드가 1140px 로 늘어지면 읽기 어렵다.
    // 타이틀 크기는 theme headings h1 이 SSOT(PageHeader) — fz 오버라이드 금지.
    <PageColumn width="prose">
      <PageHeader
        title="우리집 체크 결과"
        subtitle="건축물대장(전유부·표제부) 조회 결과예요."
      />
      <HomeCheckResultClient checkId={checkId} quizzes={quizzes} />
    </PageColumn>
  );
}

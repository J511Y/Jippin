import type { ReactNode } from 'react';
import { ComingSoonGate } from '@/components/ComingSoonGate';

/**
 * 검토(사전검토 세션)는 메인 기능이지만 아직 개발 중이므로, /sessions/* 전체를
 * blur 게이트로 감싸 전문가 상담으로 인입시킨다. (CMP-DIRECT 디자인 트랙)
 */
export default function SessionsLayout({ children }: { children: ReactNode }) {
  return (
    <ComingSoonGate
      title="AI 사전검토, 마무리 단계예요"
      description="검토 엔진을 다듬고 있어요. 지금은 전문가가 직접 사전검토부터 행위허가까지 도와드립니다."
    >
      {children}
    </ComingSoonGate>
  );
}

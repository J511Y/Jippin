'use client';

/**
 * 새 사전검토 진입 (CMP-DIRECT 대화형 UX 재설계).
 *
 * 주소/동/호/파일 입력 폼을 모두 제거하고 ChatGPT/Gemini 식 단일 입력 화면을 띄운다.
 * 첫 전송 시 SessionChat 이 세션을 생성하고 URL 을 `/sessions/{id}` 로 부드럽게 교체한다.
 */

import { SessionChat } from '@/components/agent/SessionChat';

export default function NewSessionPage() {
  return <SessionChat />;
}

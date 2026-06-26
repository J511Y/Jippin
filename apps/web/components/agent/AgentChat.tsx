'use client';

/**
 * 에이전트 채팅 (CMP-DIRECT).
 *
 * 대화형 UX 재설계로 본체는 `SessionChat` 으로 이전됐다. 기존 import 호환을 위해
 * 얇은 래퍼만 남긴다 — `sessionId` 가 있으면 해당 세션 대화를 마운트한다.
 */

import { SessionChat } from './SessionChat';

export function AgentChat({ sessionId }: { sessionId?: string }) {
  return <SessionChat sessionId={sessionId} />;
}

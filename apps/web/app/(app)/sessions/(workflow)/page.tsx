/**
 * `/sessions` — 새 사전검토 진입(대화형 채팅).
 *
 * 과거엔 `/sessions` 가 `/sessions/new` 로 리다이렉트했으나, 리다이렉트 깜빡임을 없애고
 * 진입 URL 을 `/sessions` 하나로 통합했다(#sessions-entry-unified). `SessionChat` 은
 * activeId(=sessionId) 가 없으면 compose 화면을 띄우고, 첫 전송 시 세션을 생성해
 * `history.replaceState` 로 `/sessions/{id}` 로 URL 만 교체한다.
 *
 * noindex 는 상위 `(workflow)/layout.tsx` 가 보장한다. 공개 색인 페이지는 `/sessions/landing`.
 */

import { SessionChat } from '@/components/agent/SessionChat';

export default function NewSessionPage() {
  return <SessionChat />;
}

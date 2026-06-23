'use client';

/**
 * 채팅 액션 컨텍스트 (CMP-DIRECT 채팅 UX 개선).
 *
 * A2UI 동적 컴포넌트(주소 후보 선택, 도면 업로드 유도 카드 등)가 대화 흐름으로
 * 되돌아갈 수 있게, 채팅 컨테이너가 제공하는 액션을 컨텍스트로 내려 준다.
 * 카드에서 사용자가 무언가 선택/업로드하면 `sendMessage` 로 에이전트에 이어 보낸다.
 */

import { createContext, useContext } from 'react';

export interface ChatActions {
  /** 현재 세션 ID. */
  sessionId: string;
  /** 사용자를 대신해 에이전트에 메시지를 보낸다(카드의 선택/완료를 대화로 이어 줌). */
  sendMessage: (text: string) => void | Promise<void>;
  /** 세션 메타(도면 첨부 여부 등)를 다시 읽어 상위 상태를 갱신한다. */
  refreshSession?: () => void | Promise<void>;
  /** 스트리밍 중 여부 — 카드가 액션 버튼 비활성 판단에 쓴다. */
  busy: boolean;
}

const ChatActionsContext = createContext<ChatActions | null>(null);

export const ChatActionsProvider = ChatActionsContext.Provider;

/** 채팅 컨텍스트 밖에서 호출되면 액션이 없으므로 null 을 돌려준다(카드가 안전 처리). */
export function useChatActions(): ChatActions | null {
  return useContext(ChatActionsContext);
}

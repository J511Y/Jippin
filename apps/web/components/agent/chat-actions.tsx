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
  /**
   * 현재 세션의 선택 도면 asset id(없으면 null, 아직 조회 전이면 undefined).
   * 업로드/교체 후 refreshSession 이 갱신한다 — 스레드에 도면 카드가 여러 장일 때,
   * 한 카드의 업로드를 **다른 카드들도** 이 값 변화로 감지해 상태를 재조정한다
   * (#floorplan-cards-broadcast). 값을 못 주는 호스트(테스트 등)에서는 카드가
   * 자체 조회로 폴백한다.
   */
  selectedFloorplanAssetId?: string | null;
  /**
   * 미리보기 전용 — true 면 도면 카드가 업로드/등록/전송을 실제로 하지 않고 첨부 완료
   * 상태만 재현한다. `/a2ui-preview` 는 공개 경로라 익명 세션 발급·잘못된 session_id 로의
   * 업로드 호출(422)이 일어나면 안 된다. 실서비스 호스트(SessionChat)는 설정하지 않는다.
   */
  simulateUploads?: boolean;
}

const ChatActionsContext = createContext<ChatActions | null>(null);

export const ChatActionsProvider = ChatActionsContext.Provider;

/** 채팅 컨텍스트 밖에서 호출되면 액션이 없으므로 null 을 돌려준다(카드가 안전 처리). */
export function useChatActions(): ChatActions | null {
  return useContext(ChatActionsContext);
}

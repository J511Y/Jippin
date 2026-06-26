/**
 * A2UI (Agent-to-User Interface) 공통 타입.
 *
 * SDD §6.2 CHAT 모듈의 메시지·동적 컴포넌트 모델을 본 골격 단계에서 최소화하여 둔다.
 * 정본 스키마는 `packages/contracts` 가 발행되면 그쪽으로 이전한다 (CMP-528).
 */

export type Role = 'user' | 'assistant' | 'system';

export type ChatMessage = {
  id: string;
  role: Role;
  content: string;
  createdAt: string;
  /** AI가 결정한 동적 컴포넌트 슬롯 (단일, 하위호환). 가능하면 dynamics 사용. */
  dynamic?: A2uiComponent;
  /** AI가 응답에 첨부한 A2UI 컴포넌트 목록. json-render(`A2uiSurface`)로 렌더된다. */
  dynamics?: A2uiComponent[];
  /**
   * 이 어시스턴트 턴에서 메시지 직전에 수행된 도구 활동(주소 확인·도면 분석 등).
   * 한 턴 = 한 아바타 아래 [활동 → 본문] 순서로 렌더한다(도구가 먼저 실행되므로).
   */
  activity?: ChatActivityStep[];
};

/** 도구 활동 한 단계. UI(MessageThread)가 스피너/체크/실패점으로 렌더한다. */
export type ChatActivityStep = {
  id: string;
  status: 'started' | 'succeeded' | 'failed';
  /** 화이트라벨 문구. raw 도구명은 담지 않는다. */
  text: string;
};

/**
 * 에이전트가 보내는 A2UI 컴포넌트의 raw 객체. 두 포맷 모두 허용한다:
 *  - json-render spec: `{ root, elements }`
 *  - 레거시: `{ kind, payload }` (`adapt.toSpec` 가 spec 으로 변환)
 */
export type A2uiComponent = Record<string, unknown>;

/** @deprecated 레거시 자체 포맷. 신규 코드는 A2uiComponent + A2uiSurface 사용. */
export type DynamicComponentSpec = {
  kind: string;
  payload: Record<string, unknown>;
};

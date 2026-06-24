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

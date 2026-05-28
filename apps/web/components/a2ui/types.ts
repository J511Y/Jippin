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
  /** AI가 결정한 동적 컴포넌트 슬롯 (있으면 DynamicComponent로 렌더). */
  dynamic?: DynamicComponentSpec;
};

/**
 * AI가 응답에 첨부하는 동적 컴포넌트의 식별자·페이로드.
 * `kind`는 클라이언트 컴포넌트 레지스트리의 키. 미등록 키는 fallback으로 렌더.
 */
export type DynamicComponentSpec = {
  kind: string;
  payload: Record<string, unknown>;
};

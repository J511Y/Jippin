import type { A2uiComponent } from './types';
import { toSpec } from './adapt';

/** 저장 포맷(native spec/legacy)에 관계없이 카드의 최상위 타입을 읽는다. */
export function a2uiRootType(component: unknown): string | null {
  const spec = toSpec(component);
  if (!spec) return null;

  const root = spec.elements[spec.root];
  return root && typeof root.type === 'string' ? root.type : null;
}

/**
 * 최종 결과와 상담 폼이 같은 턴에 들어온 옛/경합 메시지를 표시용으로 정규화한다.
 * JudgmentSummary 자체가 상담 CTA와 prefill 폼을 소유하므로, 함께 온
 * ConsultationHandoff는 결과를 가리고 중복 lead를 만들 수 있는 중복 UI다.
 */
export function presentTurnDynamics(
  dynamics: readonly A2uiComponent[]
): A2uiComponent[] {
  const hasJudgmentSummary = dynamics.some(
    (component) => a2uiRootType(component) === 'JudgmentSummary'
  );
  if (!hasJudgmentSummary) return [...dynamics];

  return dynamics.filter(
    (component) => a2uiRootType(component) !== 'ConsultationHandoff'
  );
}

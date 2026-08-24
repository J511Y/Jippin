import { describe, expect, it } from 'vitest';

import { a2uiRootType, presentTurnDynamics } from './presentation';

const consultation = {
  root: 'ch',
  elements: { ch: { type: 'ConsultationHandoff', props: { session_id: 's1' } } }
};
const judgment = {
  root: 'j',
  elements: { j: { type: 'JudgmentSummary', props: { session_id: 's1' } } }
};

describe('A2UI 턴 표시 정규화', () => {
  it('native spec과 legacy 카드 타입을 읽는다', () => {
    expect(a2uiRootType(judgment)).toBe('JudgmentSummary');
    expect(a2uiRootType({ kind: 'consultation-handoff', payload: {} })).toBe(
      'ConsultationHandoff'
    );
  });

  it('최종 결과와 함께 온 상담 폼은 숨겨 결과 CTA를 먼저 보여 준다', () => {
    const other = { root: 'x', elements: { x: { type: 'FloorplanOverlay', props: {} } } };
    const visible = presentTurnDynamics([consultation, other, judgment]);

    expect(visible).toEqual([other, judgment]);
  });

  it('최종 결과가 없는 상담 인계 카드는 유지한다', () => {
    expect(presentTurnDynamics([consultation])).toEqual([consultation]);
  });
});

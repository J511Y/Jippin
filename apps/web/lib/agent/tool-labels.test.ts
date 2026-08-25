import { describe, expect, it } from 'vitest';

import { toolStepText } from './tool-labels';

describe('toolStepText', () => {
  it('진행 중에는 서버가 보낸 세부 분석 안내를 우선한다', () => {
    expect(
      toolStepText(
        'segment_floorplan',
        'started',
        '벽의 종류와 도면 구성을 확인하고 있어요',
      ),
    ).toBe('벽의 종류와 도면 구성을 확인하고 있어요');
  });

  it('세부 안내가 없으면 기존 생활어 문구로 폴백한다', () => {
    expect(toolStepText('segment_floorplan', 'started')).toBe('도면을 분석하고 있어요');
  });
});

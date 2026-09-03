import { cleanup, render, screen } from '@/test-utils';
import { afterEach, describe, expect, it } from 'vitest';
import type { HomeCheckReport } from '@contracts/home-check';

import { HomeCheckReportView } from '../HomeCheckReportView';

afterEach(() => {
  cleanup();
});

const REPORT: HomeCheckReport = {
  signal: 'normal',
  violation: { is_violation: false, exclusive: false, heading: false, raw: null },
  address: {
    road_addr: '서울특별시 영등포구 여의대방로 1',
    dong: '101',
    ho: '1403'
  },
  change_history: [
    { date: '2005-08-11', reason: '표제부 신규 사용승인', source: 'heading' },
    { date: '2019-03-15', reason: '전유부 발코니 확장 등재', source: 'exclusive' }
  ],
  extension_check: null,
  documents: [],
  caution_reasons: [],
  disclaimer: '조회 결과는 참고용입니다.'
};

describe('우리집 체크 변동 이력', () => {
  it('전유부 변동만 표시하고 표제부 변동은 타임라인에서 숨긴다', () => {
    render(<HomeCheckReportView report={REPORT} checkId="check-1" />);

    expect(screen.getByText('전유부 발코니 확장 등재')).toBeDefined();
    expect(screen.queryByText('표제부 신규 사용승인')).toBeNull();
  });
});

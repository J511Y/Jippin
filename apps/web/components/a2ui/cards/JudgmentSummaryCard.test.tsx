import { cleanup, render, screen } from '@/test-utils';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/components/leads/QuickPrecheckConsultForm', () => ({
  QuickPrecheckConsultForm: ({
    prefillAddress,
    fromSession
  }: {
    prefillAddress?: string;
    fromSession?: string;
  }) => (
    <div data-testid="quick-consult-form" data-address={prefillAddress} data-session={fromSession}>
      상담 정보 입력
    </div>
  )
}));

import { JudgmentSummaryCard } from './JudgmentSummaryCard';

afterEach(cleanup);

describe('JudgmentSummaryCard 상담 전환', () => {
  it('결과를 먼저 보여 주고 CTA를 누른 뒤 세션 주소를 유지한 상담 폼을 연다', async () => {
    const user = userEvent.setup();
    render(
      <JudgmentSummaryCard
        payload={{
          decision: 'conditional',
          title: '지금 정보만으로는 추가 확인이 필요해요',
          summary: '선택한 벽과 창호를 기준으로 검토한 결과예요.',
          session_id: 'session-1',
          prefill_address: '서울특별시 강남구 테헤란로 12'
        }}
      />
    );

    expect(screen.getByText('선택한 벽과 창호를 기준으로 검토한 결과예요.')).not.toBeNull();
    expect(screen.queryByTestId('quick-consult-form')).toBeNull();

    await user.click(screen.getByRole('button', { name: '전문가 상담 신청하기' }));

    const form = screen.getByTestId('quick-consult-form');
    expect(form.getAttribute('data-address')).toBe('서울특별시 강남구 테헤란로 12');
    expect(form.getAttribute('data-session')).toBe('session-1');
    expect(screen.queryByRole('button', { name: '전문가 상담 신청하기' })).toBeNull();
  });
});

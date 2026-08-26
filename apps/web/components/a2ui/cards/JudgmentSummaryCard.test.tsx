import { cleanup, render, screen } from '@/test-utils';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ChatActionsProvider } from '@/components/agent/chat-actions';

const apiMocks = vi.hoisted(() => ({
  getSession: vi.fn(() =>
    Promise.resolve({ selected_floorplan_asset_id: null as string | null })
  )
}));

vi.mock('@/lib/sessions/api', () => apiMocks);

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

describe('JudgmentSummaryCard 도면 교체 감지 (#judgment-asset-stamp)', () => {
  function Card({
    currentAssetId,
    stampedAssetId
  }: {
    currentAssetId: string;
    stampedAssetId: string;
  }) {
    return (
      <ChatActionsProvider
        value={{
          sessionId: 'session-1',
          busy: false,
          sendMessage: vi.fn(),
          selectedFloorplanAssetId: currentAssetId
        }}
      >
        <JudgmentSummaryCard
          payload={{
            decision: 'possible',
            title: '검토 결과',
            summary: '요약이에요.',
            rule_backed: true,
            asset_id: stampedAssetId
          }}
        />
      </ChatActionsProvider>
    );
  }

  it('결과가 유래한 도면과 현재 도면이 다르면 이전 도면 기준으로 표시하고 상담 CTA 를 막는다', () => {
    render(<Card currentAssetId="asset-2" stampedAssetId="asset-1" />);

    expect(screen.getByText(/이전에 올렸던 도면 기준/)).toBeTruthy();
    expect(
      screen.queryByRole('button', { name: '전문가 상담 신청하기' })
    ).toBeNull();
    expect(
      screen.getByText('새 도면 기준 검토를 마치면, 새 결과 카드에서 상담을 신청할 수 있어요.')
    ).toBeTruthy();
  });

  it('같은 도면이면 상담 CTA 를 그대로 노출한다', () => {
    render(<Card currentAssetId="asset-1" stampedAssetId="asset-1" />);

    expect(
      screen.getByRole('button', { name: '전문가 상담 신청하기' })
    ).toBeTruthy();
    expect(screen.queryByText(/이전에 올렸던 도면 기준/)).toBeNull();
  });

  it('CTA 클릭 시점 재검증 — 다른 탭의 교체를 감지하면 폼 대신 이전 도면 안내로 전환한다', async () => {
    // 브로드캐스트(같은 탭)는 아직 asset-1 이지만 서버는 이미 asset-2 — 다른 탭 교체.
    const user = userEvent.setup();
    apiMocks.getSession.mockResolvedValueOnce({
      selected_floorplan_asset_id: 'asset-2'
    });
    render(<Card currentAssetId="asset-1" stampedAssetId="asset-1" />);

    await user.click(screen.getByRole('button', { name: '전문가 상담 신청하기' }));

    expect(await screen.findByText(/이전에 올렸던 도면 기준/)).toBeTruthy();
    expect(screen.queryByTestId('quick-consult-form')).toBeNull();
    expect(apiMocks.getSession).toHaveBeenCalledTimes(1);
  });

  it('CTA 클릭 시점 재검증 — 서버도 같은 도면이면 폼을 연다', async () => {
    const user = userEvent.setup();
    apiMocks.getSession.mockResolvedValueOnce({
      selected_floorplan_asset_id: 'asset-1'
    });
    render(<Card currentAssetId="asset-1" stampedAssetId="asset-1" />);

    await user.click(screen.getByRole('button', { name: '전문가 상담 신청하기' }));

    expect(await screen.findByTestId('quick-consult-form')).toBeTruthy();
  });
});

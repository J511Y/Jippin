import { cleanup, render, screen } from '@/test-utils';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ChatActionsProvider } from '@/components/agent/chat-actions';

const apiMocks = vi.hoisted(() => ({
  // 실제 SessionRow 의 부분집합만 흉내낸다 — 게이트는 필드 부재 시 통과(best-effort)
  // 하므로, 각 테스트가 필요한 필드만 명시한다.
  getSession: vi.fn(
    (): Promise<Record<string, unknown>> =>
      Promise.resolve({ selected_floorplan_asset_id: null })
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

afterEach(() => {
  cleanup();
  // 레거시 게이트가 CTA 클릭마다 getSession 을 부르므로, 호출 수 단언이 테스트 간
  // 누적되지 않게 초기화한다(구현은 유지 — clear 는 calls 만 비운다).
  vi.clearAllMocks();
});

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

describe('JudgmentSummaryCard 레거시(스탬프 없는) 카드 신선도 (#legacy-judgment-freshness)', () => {
  function legacyPayload(ruleBacked: boolean) {
    // asset_id 미지정 = #185 이전에 저장된 결과 카드. 도면 교체 뒤에도 asset 대조가
    // 불가하므로, CTA 클릭 시점에 세션의 판정/분석 잔존으로 신선도를 가른다.
    return {
      decision: 'possible' as const,
      title: '검토 결과',
      summary: '요약이에요.',
      rule_backed: ruleBacked,
      session_id: 'session-1'
    };
  }

  it('법령 검토 결과인데 세션 판정이 소거됐으면(도면 교체) 폼 대신 이전 도면 안내로 전환한다', async () => {
    const user = userEvent.setup();
    apiMocks.getSession.mockResolvedValueOnce({
      selected_floorplan_asset_id: 'asset-2',
      has_report: false
    });
    render(<JudgmentSummaryCard payload={legacyPayload(true)} />);

    await user.click(screen.getByRole('button', { name: '전문가 상담 신청하기' }));

    expect(await screen.findByText(/이전에 올렸던 도면 기준/)).toBeTruthy();
    expect(screen.queryByTestId('quick-consult-form')).toBeNull();
  });

  it('법령 검토 결과이고 세션 판정이 살아 있으면 폼을 연다', async () => {
    const user = userEvent.setup();
    apiMocks.getSession.mockResolvedValueOnce({
      selected_floorplan_asset_id: 'asset-1',
      has_report: true
    });
    render(<JudgmentSummaryCard payload={legacyPayload(true)} />);

    await user.click(screen.getByRole('button', { name: '전문가 상담 신청하기' }));

    expect(await screen.findByTestId('quick-consult-form')).toBeTruthy();
  });

  it('예비 관찰인데 분석 산출이 전부 리셋됐으면(교체 직후) 차단한다', async () => {
    const user = userEvent.setup();
    apiMocks.getSession.mockResolvedValueOnce({
      selected_floorplan_asset_id: 'asset-2',
      judgment_schema: { judgment_values: { floor_count: 6 } }
    });
    render(<JudgmentSummaryCard payload={legacyPayload(false)} />);

    await user.click(screen.getByRole('button', { name: '전문가 상담 신청하기' }));

    expect(await screen.findByText(/이전에 올렸던 도면 기준/)).toBeTruthy();
    expect(screen.queryByTestId('quick-consult-form')).toBeNull();
  });

  it('예비 관찰이고 분석 산출이 남아 있으면(빈 검출 포함) 폼을 연다', async () => {
    const user = userEvent.setup();
    apiMocks.getSession.mockResolvedValueOnce({
      selected_floorplan_asset_id: 'asset-1',
      judgment_schema: { wall_objects: [] }
    });
    render(<JudgmentSummaryCard payload={legacyPayload(false)} />);

    await user.click(screen.getByRole('button', { name: '전문가 상담 신청하기' }));

    expect(await screen.findByTestId('quick-consult-form')).toBeTruthy();
  });
});

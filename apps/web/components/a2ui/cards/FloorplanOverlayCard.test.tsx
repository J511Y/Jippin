import { cleanup, render, waitFor } from '@/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ChatActionsProvider } from '@/components/agent/chat-actions';

const apiMocks = vi.hoisted(() => ({
  getFloorplanAssetSignedUrl: vi.fn(() => Promise.resolve('https://example.test/plan.jpg')),
  // 실제 SessionRow 의 부분집합만 흉내낸다 — 각 테스트가 필요한 필드만 명시.
  getSession: vi.fn(
    (): Promise<Record<string, unknown>> =>
      Promise.resolve({
        judgment_schema: { selected_walls: ['wall:1'], selected_windows: [] }
      })
  ),
  updateSelectedWalls: vi.fn(() =>
    Promise.resolve({ selected_walls: [], selected_windows: [] })
  )
}));

vi.mock('@/lib/sessions/api', () => apiMocks);
vi.mock('@/lib/analytics/sessions-funnel', () => ({
  trackPrecheckOverlayView: vi.fn(),
  trackPrecheckWallSelect: vi.fn()
}));

import { FloorplanOverlayCard, type FloorplanOverlayPayload } from './FloorplanOverlayCard';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function Card({
  payload,
  selectedFloorplanAssetId
}: {
  payload: FloorplanOverlayPayload;
  selectedFloorplanAssetId?: string | null;
}) {
  return (
    <ChatActionsProvider
      value={{
        sessionId: 'session-1',
        busy: false,
        sendMessage: vi.fn(),
        selectedFloorplanAssetId
      }}
    >
      <FloorplanOverlayCard payload={payload} />
    </ChatActionsProvider>
  );
}

const wallPayload: FloorplanOverlayPayload = {
  asset_id: 'asset-1',
  image: { width: 100, height: 100 },
  vocab_version: 4,
  regions: [
    {
      region_id: 'wall:1',
      class_name: 'wall_nonbearing',
      polygon: [10, 10, 20, 10, 20, 20]
    }
  ]
};

describe('FloorplanOverlayCard 도면 복원', () => {
  it('같은 A2UI payload가 새 객체로 재구성돼도 signed URL과 세션을 다시 조회하지 않는다', async () => {
    const payload: FloorplanOverlayPayload = {
      asset_id: 'asset-1',
      image: { width: 100, height: 100 },
      vocab_version: 4,
      regions: [
        {
          region_id: 'wall:1',
          class_name: 'wall_nonbearing',
          polygon: [10, 10, 20, 10, 20, 20]
        }
      ]
    };
    const view = render(<Card payload={payload} />);

    await waitFor(() => {
      expect(apiMocks.getFloorplanAssetSignedUrl).toHaveBeenCalledTimes(1);
      expect(apiMocks.getSession).toHaveBeenCalledTimes(1);
    });

    view.rerender(
      <Card
        payload={{
          ...payload,
          image: { ...payload.image },
          regions: payload.regions?.map((region) => ({
            ...region,
            polygon: [...region.polygon]
          }))
        }}
      />
    );

    await waitFor(() =>
      expect(apiMocks.getFloorplanAssetSignedUrl).toHaveBeenCalledTimes(1)
    );
    expect(apiMocks.getSession).toHaveBeenCalledTimes(1);
  });

  it('세션의 선택이 이 카드의 도면 기준이면 제출됨 상태로 복원한다', async () => {
    apiMocks.getSession.mockResolvedValueOnce({
      selected_floorplan_asset_id: 'asset-1',
      judgment_schema: { selected_walls: ['wall:1'], selected_windows: [] }
    });
    const view = render(<Card payload={wallPayload} />);

    await waitFor(() =>
      expect(
        view.getByRole('button', { name: '철거 검토 요청을 보냈어요 · 1곳' })
      ).toBeTruthy()
    );
  });
});

describe('FloorplanOverlayCard 도면 교체 감지 (#overlay-asset-fingerprint 복원 짝)', () => {
  it('복원 시점에 도면이 교체돼 있으면 세션의 선택(새 도면 것)을 복원하지 않고 만료 표시한다', async () => {
    // region id(pred:N/wall:N)는 도면이 달라도 재사용된다 — 세션에 저장된 선택은
    // 교체된 새 도면(asset-2)의 것이지만 id 교집합만으로는 이 옛 카드(asset-1)에
    // '제출됨'으로 되살아난다. asset 지문 대조가 이를 막는다.
    apiMocks.getSession.mockResolvedValueOnce({
      selected_floorplan_asset_id: 'asset-2',
      judgment_schema: { selected_walls: ['wall:1'], selected_windows: [] }
    });
    const view = render(<Card payload={wallPayload} />);

    await waitFor(() =>
      expect(view.getByText(/이 카드의 선택은 더 이상 쓸 수 없어요/)).toBeTruthy()
    );
    expect(
      view.getByRole('button', { name: '이 카드는 이전 분석 결과예요' })
    ).toBeTruthy();
    expect(
      view.queryByRole('button', { name: '철거 검토 요청을 보냈어요 · 1곳' })
    ).toBeNull();
  });

  it('브로드캐스트가 다른 선택 도면을 알리면 즉시 만료 표시한다', async () => {
    // 같은 트리의 형제 도면 카드가 새 도면을 올린 직후 — 세션 재조회 없이도
    // 컨텍스트 브로드캐스트(#floorplan-cards-broadcast)로 이 카드가 함께 재조정된다.
    const view = render(
      <Card payload={wallPayload} selectedFloorplanAssetId="asset-2" />
    );

    await waitFor(() =>
      expect(view.getByText(/이 카드의 선택은 더 이상 쓸 수 없어요/)).toBeTruthy()
    );
    expect(
      view.getByRole('button', { name: '이 카드는 이전 분석 결과예요' })
    ).toBeTruthy();
  });

  it('스탬프 없는 구 카드는 종전대로 id 교집합 복원을 유지한다', async () => {
    apiMocks.getSession.mockResolvedValueOnce({
      selected_floorplan_asset_id: 'asset-2',
      judgment_schema: { selected_walls: ['wall:1'], selected_windows: [] }
    });
    const legacyPayload: FloorplanOverlayPayload = { ...wallPayload };
    delete legacyPayload.asset_id;
    const view = render(<Card payload={legacyPayload} />);

    await waitFor(() =>
      expect(
        view.getByRole('button', { name: '철거 검토 요청을 보냈어요 · 1곳' })
      ).toBeTruthy()
    );
  });
});

import { cleanup, render, waitFor } from '@/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ChatActionsProvider } from '@/components/agent/chat-actions';

const apiMocks = vi.hoisted(() => ({
  getFloorplanAssetSignedUrl: vi.fn(() => Promise.resolve('https://example.test/plan.jpg')),
  getSession: vi.fn(() =>
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

function Card({ payload }: { payload: FloorplanOverlayPayload }) {
  return (
    <ChatActionsProvider
      value={{ sessionId: 'session-1', busy: false, sendMessage: vi.fn() }}
    >
      <FloorplanOverlayCard payload={payload} />
    </ChatActionsProvider>
  );
}

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
});

import { cleanup, render, screen, waitFor } from '@/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';

const apiMocks = vi.hoisted(() => ({
  getFloorplanAssetSignedUrl: vi.fn()
}));
vi.mock('@/lib/sessions/api', () => apiMocks);

import { ReportFloorplan, scaleObjectsToImage, selectedIdsOf } from './ReportFloorplan';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('scaleObjectsToImage', () => {
  it('0~1 정규화 좌표(MaskCoord)는 이미지 크기로 환산한다 — PDF report_overlay 와 동일 판정', () => {
    const scaled = scaleObjectsToImage(
      [{ id: 'w1', kind: 'wall', wallType: 'NON_LOAD_BEARING', pts: [{ x: 0.1, y: 0.5 }, { x: 0.9, y: 0.5 }] }],
      { w: 1000, h: 400 }
    );
    expect(scaled[0].pts).toEqual([{ x: 100, y: 200 }, { x: 900, y: 200 }]);
  });
  it('픽셀 좌표는 그대로 둔다', () => {
    const objs = [{ id: 'w1', kind: 'wall' as const, wallType: 'UNKNOWN', pts: [{ x: 10, y: 10 }, { x: 200, y: 10 }] }];
    expect(scaleObjectsToImage(objs, { w: 1000, h: 400 })).toEqual(objs);
  });
});

describe('selectedIdsOf', () => {
  it('벽체 → 창호 순서를 보존하고 중복을 제거한다', () => {
    expect(selectedIdsOf({ selected_walls: ['w2', 'w1'], selected_windows: ['win1', 'w1'] })).toEqual([
      'w2',
      'w1',
      'win1'
    ]);
    expect(selectedIdsOf(null)).toEqual([]);
  });
});

describe('ReportFloorplan 실패 상태', () => {
  it('서명 URL 발급 실패 시 조용히 사라지지 않고 안내 + 다시 시도를 보여준다', async () => {
    apiMocks.getFloorplanAssetSignedUrl.mockRejectedValueOnce(new Error('boom'));
    render(<ReportFloorplan sessionId="s" assetId="a" judgment={{}} />);
    await waitFor(() => expect(screen.getByText('도면 이미지를 지금 불러올 수 없어요')).toBeTruthy());
    expect(screen.getByRole('button', { name: '다시 시도' })).toBeTruthy();
    expect(apiMocks.getFloorplanAssetSignedUrl).toHaveBeenCalledTimes(1);
  });
});

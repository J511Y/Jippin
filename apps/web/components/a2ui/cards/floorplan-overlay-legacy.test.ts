import { describe, expect, it } from 'vitest';

import { normalizeLegacyRegions, type OverlayRegion } from './FloorplanOverlayCard';

/**
 * 저장된 v3 오버레이 카드의 의미 보존 — 세그멘테이션 v4 어휘 전환의 하위호환 지점.
 *
 * v3 에서 `wall_other` 는 초록 '비내력벽 후보'였고, v4 에서는 '미확정 벽'이다.
 * `chat_messages.ui_components` 에 남은 옛 payload 를 새 규칙으로 읽으면 사용자가 이미
 * 비내력벽으로 안내받고 고른 벽이 미확정으로 뒤바뀌어 보인다(그 세션의 wall_objects 는
 * NON_LOAD_BEARING 으로 굳어 있어 리포트와도 어긋난다).
 */
describe('normalizeLegacyRegions', () => {
  const regions: OverlayRegion[] = [
    { region_id: 'r1', class_name: 'wall_other', polygon: [0, 0, 10, 0, 10, 10] },
    { region_id: 'r2', class_name: 'wall_unknown', polygon: [0, 0, 10, 0, 10, 10] },
    { region_id: 'r3', class_name: 'wall_nonbearing', polygon: [0, 0, 10, 0, 10, 10] },
    { region_id: 'r4', class_name: 'window', polygon: [0, 0, 10, 0, 10, 10] }
  ];

  it('v3 저장분(판별자 없음)의 wall_other 를 비내력 후보로 되돌린다', () => {
    const out = normalizeLegacyRegions(regions, 3);
    expect(out.map((r) => r.class_name)).toEqual([
      'wall_nonbearing', // v3 의 초록 비내력 후보 — 의미 보존
      'wall_unknown', // v3 에서도 회색 불확실 — 그대로
      'wall_nonbearing',
      'window'
    ]);
  });

  it('v4 payload 는 그대로 둔다(wall_other = 미확정 벽)', () => {
    const out = normalizeLegacyRegions(regions, 4);
    expect(out).toBe(regions);
    expect(out[0]?.class_name).toBe('wall_other');
  });

  it('원본 배열을 변형하지 않는다', () => {
    normalizeLegacyRegions(regions, 3);
    expect(regions[0]?.class_name).toBe('wall_other');
  });
});

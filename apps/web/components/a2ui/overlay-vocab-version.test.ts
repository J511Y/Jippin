import { describe, expect, it } from 'vitest';

import { a2uiCatalog } from './jsonrender';

/**
 * `vocab_version` 이 카탈로그 검증을 **통과해 카드까지 살아 남는지** 고정한다.
 *
 * 이 값이 카드에 닿지 않으면 모든 v4 오버레이가 v3 저장분으로 오인돼 `wall_other`
 * (미확정 벽)가 초록 '비내력벽 후보'로 뒤집혀 그려진다 — 이번 마이그레이션이 바로잡으려던
 * 반전이 그대로 되살아나는 셈이라, 조용히 깨지면 가장 치명적인 지점이다.
 * Zod 객체 스키마는 선언되지 않은 키를 떨어뜨릴 수 있으므로 명시 선언을 회귀로 잠근다.
 */
describe('FloorplanOverlay 카탈로그 props', () => {
  const props = (
    a2uiCatalog as unknown as {
      data: {
        components: Record<string, { props: { parse: (v: unknown) => unknown } }>;
      };
    }
  ).data.components.FloorplanOverlay.props;

  it('vocab_version 을 보존한다', () => {
    const parsed = props.parse({
      asset_id: 'a1',
      image: { width: 10, height: 10 },
      regions: [],
      vocab_version: 4
    }) as { vocab_version?: number };
    expect(parsed.vocab_version).toBe(4);
  });

  it('vocab_version 이 없는 payload(v3 저장분)도 통과시킨다', () => {
    const parsed = props.parse({
      asset_id: 'a1',
      image: { width: 10, height: 10 },
      regions: []
    }) as { vocab_version?: number };
    expect(parsed.vocab_version).toBeUndefined();
  });
});

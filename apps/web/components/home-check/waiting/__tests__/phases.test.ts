/**
 * 대기 화면 진행 로직 유닛 — phase 매핑/시간 폴백 경계/안심 문구 티어.
 * 미지의 phase 는 null(→ 시간 추정 폴백)이 계약(contracts 1.3.0 open string)이다.
 */

import { describe, expect, it } from 'vitest';

import {
  estimateIndexFromElapsed,
  phaseToIndex,
  reassuranceCopy,
  WAIT_STEPS
} from '../phases';

describe('phaseToIndex', () => {
  it('알려진 phase 4종을 순서대로 매핑한다', () => {
    expect(WAIT_STEPS).toHaveLength(4);
    expect(phaseToIndex('received')).toBe(0);
    expect(phaseToIndex('issuing_registers')).toBe(1);
    expect(phaseToIndex('judging')).toBe(2);
    expect(phaseToIndex('saving_report')).toBe(3);
  });

  it('null/undefined/빈 문자열은 null(시간 추정 폴백)', () => {
    expect(phaseToIndex(null)).toBeNull();
    expect(phaseToIndex(undefined)).toBeNull();
    expect(phaseToIndex('')).toBeNull();
  });

  it('미지의 phase(향후 세분화)도 null 로 폴백한다 — 엄격 enum 금지 계약', () => {
    expect(phaseToIndex('issuing_exclusive')).toBeNull();
    expect(phaseToIndex('whatever_new_phase')).toBeNull();
  });
});

describe('estimateIndexFromElapsed', () => {
  it('구간 경계: <10s→0, 10~100s→1, 100~150s→2, ≥150s→3', () => {
    expect(estimateIndexFromElapsed(0)).toBe(0);
    expect(estimateIndexFromElapsed(9_999)).toBe(0);
    expect(estimateIndexFromElapsed(10_000)).toBe(1);
    expect(estimateIndexFromElapsed(99_999)).toBe(1);
    expect(estimateIndexFromElapsed(100_000)).toBe(2);
    expect(estimateIndexFromElapsed(149_999)).toBe(2);
    expect(estimateIndexFromElapsed(150_000)).toBe(3);
    expect(estimateIndexFromElapsed(10 * 60_000)).toBe(3);
  });

  it('마지막 스텝(3)을 넘지 않는다 — 완료는 status=completed 로만', () => {
    expect(estimateIndexFromElapsed(Number.MAX_SAFE_INTEGER)).toBe(3);
  });
});

describe('reassuranceCopy', () => {
  it('<180s 는 기본(2~3분) 안내', () => {
    expect(reassuranceCopy(0)).toContain('2~3분');
    expect(reassuranceCopy(179_999)).toContain('2~3분');
  });

  it('180~300s 는 혼잡(최대 5분) 안내', () => {
    expect(reassuranceCopy(180_000)).toContain('5분');
    expect(reassuranceCopy(299_999)).toContain('5분');
  });

  it('≥300s 는 지연 안심 안내', () => {
    expect(reassuranceCopy(300_000)).toContain('오래');
  });
});

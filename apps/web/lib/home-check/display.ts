/**
 * 우리집 체크 표시용 라벨/포맷 헬퍼 (CMP-DIRECT, ADR-0008).
 *
 * 톤 규칙(ADR-0008 §2.4): 위반/정상을 단정하지 않고 "위반표시 있음/없음" 사실을 기술한다.
 */

import type { HomeCheckJob } from '@contracts/home-check';

export type Signal = NonNullable<HomeCheckJob['signal']>;
export type JobStatus = HomeCheckJob['status'];

export interface SignalMeta {
  emoji: string;
  label: string;
  /** Mantine color 토큰. */
  color: string;
  description: string;
}

/** 종합 신호등 메타. 단정 회피 톤(위반표시 있음/확인 필요/없음). */
export const SIGNAL_META: Record<Signal, SignalMeta> = {
  violation: {
    emoji: '🔴',
    label: '위반표시 있음',
    color: 'red',
    description: '건축물대장에 위반건축물 표시가 확인됩니다.'
  },
  caution: {
    emoji: '🟡',
    label: '확인 필요',
    color: 'yellow',
    description: '추가 확인이 필요한 항목이 있습니다.'
  },
  normal: {
    emoji: '🟢',
    label: '위반표시 없음',
    color: 'teal',
    description: '조회 시점 기준 위반건축물 표시가 확인되지 않았습니다.'
  }
};

export interface StatusMeta {
  label: string;
  color: string;
}

/** 잡 상태 라벨(목록·진행 표시용). */
export const STATUS_META: Record<JobStatus, StatusMeta> = {
  pending: { label: '대기 중', color: 'gray' },
  querying: { label: '조회 중', color: 'jippin' },
  needs_input: { label: '추가 입력 필요', color: 'yellow' },
  completed: { label: '조회 완료', color: 'teal' },
  failed: { label: '조회 실패', color: 'red' }
};

/** 잡/리포트에서 대표 주소 문자열을 뽑는다(목록·상단 헤더용). */
export function jobAddressLabel(job: Pick<HomeCheckJob, 'report'>): string | null {
  const addr = job.report?.address;
  if (!addr) return null;
  const base = addr.road_addr ?? addr.jibun_addr ?? '';
  const detail = [addr.dong ? `${addr.dong}동` : null, addr.ho ? `${addr.ho}호` : null]
    .filter(Boolean)
    .join(' ');
  return [base, detail].filter(Boolean).join(' ').trim() || null;
}

/** ISO-8601 → 'YYYY-MM-DD'. 빈 값이면 null. */
export function isoDate(value?: string | null): string | null {
  if (!value) return null;
  return value.slice(0, 10);
}

/** 면적(㎡) 표시 — 평 환산 병기. */
export function formatArea(m2?: number | null): string | null {
  if (m2 == null) return null;
  const pyeong = m2 / 3.305_785;
  return `${m2.toLocaleString('ko-KR')}㎡ (약 ${pyeong.toFixed(1)}평)`;
}

/** 공동주택가격(원) 표시. */
export function formatPrice(won?: number | null): string | null {
  if (won == null) return null;
  return `${won.toLocaleString('ko-KR')}원`;
}

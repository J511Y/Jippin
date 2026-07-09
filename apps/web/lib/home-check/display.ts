/**
 * 우리집 체크 표시용 라벨/포맷 헬퍼 (CMP-DIRECT, ADR-0008).
 *
 * 톤 규칙(ADR-0008 §2.4): 위반/정상을 단정하지 않고 "위반표시 있음/없음" 사실을 기술한다.
 */

import {
  IconAlertCircle,
  IconAlertTriangle,
  IconCircleCheck,
  IconHelpCircle,
  IconInfoCircle
} from '@tabler/icons-react';

import type { HomeCheckJob, HomeCheckReport } from '@contracts/home-check';

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

/**
 * 리포트 종합 판정 — 두 개의 독립 축(공식 위반표시 + 확장 등재 대조)을 하나의 4-상태
 * 히어로로 합친 값. `signal`(백엔드 신호등)과 달리 web 이 리포트 필드로부터 파생한다.
 *
 * - illegal        : 노란딱지(공식 위반표시).
 * - unrecorded_ext : 신고 확장이 대장 변동사항에 미등재(위반 소지).
 * - caution        : 대조 모호 또는 별도 확인 사유 있음.
 * - normal         : 위반표시 없음 + 신고 확장 등재 확인.
 * - not_checked    : 위반표시는 없으나 확장 입력이 없어 등재 대조를 못 함.
 */
export type Verdict =
  | 'illegal'
  | 'unrecorded_ext'
  | 'caution'
  | 'normal'
  | 'not_checked';

/**
 * 두 축을 우선순위대로 접어 하나의 Verdict 로 환원한다(ADR-0008, schema 1.2.0).
 * 공식 위반표시(violation.is_violation)가 언제나 최우선이며, 그다음이 확장 등재 대조다.
 */
export function resolveVerdict(report: HomeCheckReport): Verdict {
  if (report.violation?.is_violation) return 'illegal';

  const ext = report.extension_check;
  if (ext?.verdict === 'violation') return 'unrecorded_ext';
  if (ext?.verdict === 'uncertain' || (report.caution_reasons?.length ?? 0) > 0) {
    return 'caution';
  }
  if (ext?.verdict === 'legal') return 'normal';
  return 'not_checked';
}

/** Verdict 배너·카드 강조에 쓰는 상태 톤. gray 는 CardShell 의 neutral accent 로 매핑. */
export type VerdictTone = 'danger' | 'warning' | 'success' | 'gray';

/** 모든 Tabler 아이콘이 공유하는 컴포넌트 타입(어떤 아이콘이든 대입 가능). */
type VerdictIcon = typeof IconAlertTriangle;

export interface VerdictMeta {
  /** 장식용 이모지(신호등). 접근성은 아이콘+라벨이 담당하므로 배너 밖 보조 표기에만 쓴다. */
  emoji: string;
  /** 상태 톤 — 배너 색과 카드 강조 레일 색의 근거. */
  tone: VerdictTone;
  /** 배너 아이콘(색만으로 상태를 전달하지 않기 위한 형태 신호). */
  Icon: VerdictIcon;
  /** 4-상태 라벨. */
  label: string;
  /** 히어로 한 줄 요약(생활어·단정 회피 톤). */
  oneLiner: string;
}

/**
 * Verdict 메타 — 히어로/배지에서 색+아이콘+라벨을 한 번에 뽑는다.
 * 🟢(normal)은 브랜드 틸이 아니라 success 그린을 쓴다(브랜드색과 판정색 혼동 방지).
 * coral(포인트색)은 CTA 전용이라 여기 등장하지 않는다.
 */
export const VERDICT_META: Record<Verdict, VerdictMeta> = {
  illegal: {
    emoji: '🔴',
    tone: 'danger',
    Icon: IconAlertTriangle,
    label: '위반건축물',
    oneLiner: '건축물대장에 위반건축물(노란딱지)로 등재돼 있어요.'
  },
  unrecorded_ext: {
    emoji: '🔴',
    tone: 'danger',
    Icon: IconAlertCircle,
    label: '미등재 확장 의심',
    oneLiner: '신고하신 확장이 대장 변동사항에서 확인되지 않아요.'
  },
  caution: {
    emoji: '🟡',
    tone: 'warning',
    Icon: IconInfoCircle,
    label: '주의 · 확인 필요',
    oneLiner: '추가로 확인이 필요한 항목이 있어요.'
  },
  normal: {
    emoji: '🟢',
    tone: 'success',
    Icon: IconCircleCheck,
    label: '정상 · 적법',
    oneLiner: '위반표시가 없고, 신고하신 확장도 대장에 등재돼 있어요.'
  },
  not_checked: {
    emoji: '⚪',
    tone: 'gray',
    Icon: IconHelpCircle,
    label: '확인 필요 · 미대조',
    oneLiner: '위반표시는 없지만, 확장 여부를 입력하지 않아 등재 대조는 못 했어요.'
  }
};

/** VerdictTone → Mantine color 토큰(목록/배지용). */
export const VERDICT_TONE_COLOR: Record<VerdictTone, string> = {
  danger: 'red',
  warning: 'yellow',
  success: 'teal',
  gray: 'gray'
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

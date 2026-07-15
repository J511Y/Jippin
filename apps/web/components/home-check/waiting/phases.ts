/**
 * 대기 화면 진행 로직 — phase→스텝 매핑 + 시간 폴백 + 안심 문구 (순수 함수, 유닛 대상).
 *
 * 백엔드 phase(contracts 1.3.0, 정보성 open string)가 정본이고, phase 가 없거나
 * (구 잡/스태거드 배포) 미지의 값이면 경과 시간으로 스텝을 추정한다. 계약상 미지의
 * phase 는 일반 대기 표시로 폴백해야 한다 — phaseToIndex 가 null 을 돌려주면
 * 호출측이 시간 추정을 쓰는 구조가 그 폴백이다.
 */

export type WaitStepKey =
  | 'received'
  | 'issuing_registers'
  | 'judging'
  | 'saving_report';

export interface WaitStep {
  key: WaitStepKey;
  /** 스텝 라벨(짧게 — 모바일 세로 스테퍼). */
  label: string;
  /** 현재 스텝에만 노출하는 설명(해요체). */
  description: string;
}

/** 백엔드 phase 순서와 동일한 4스텝. */
export const WAIT_STEPS: readonly WaitStep[] = [
  { key: 'received', label: '접수 확인', description: '조회 요청을 접수했어요' },
  {
    key: 'issuing_registers',
    label: '대장 발급',
    description: '건축물대장 전유부·표제부를 발급하고 있어요'
  },
  {
    key: 'judging',
    label: '확장 대조 분석',
    description: '대장 변동사항과 확장 등재 여부를 대조하고 있어요'
  },
  { key: 'saving_report', label: '리포트 생성', description: '결과 리포트를 정리하고 있어요' }
];

/** phase → 스텝 인덱스. null/미지의 값은 null(호출측이 시간 추정으로 폴백). */
export function phaseToIndex(phase: string | null | undefined): number | null {
  if (!phase) return null;
  const idx = WAIT_STEPS.findIndex((step) => step.key === phase);
  return idx >= 0 ? idx : null;
}

/**
 * 경과 시간 기반 스텝 추정(phase 부재 시 폴백). 실측 파이프라인 소요(발급 ~1-2분,
 * 판정·저장 수십 초)에 맞춘 보수적 구간 — 마지막 스텝은 여기서 완료되지 않는다
 * (완료는 오직 실제 status=completed 로만).
 */
export function estimateIndexFromElapsed(elapsedMs: number): number {
  if (elapsedMs < 10_000) return 0;
  if (elapsedMs < 100_000) return 1;
  if (elapsedMs < 150_000) return 2;
  return 3;
}

/** 경과 시간대별 안심 문구 — 기대치(보통 2~3분)를 정직하게 안내한다. */
export function reassuranceCopy(elapsedMs: number): string {
  if (elapsedMs < 180_000) {
    return '보통 2~3분 정도 걸려요. 화면을 닫지 말고 잠시만 기다려 주세요. 조회가 끝나면 결과가 자동으로 표시돼요.';
  }
  if (elapsedMs < 300_000) {
    return '정부 시스템(세움터)이 혼잡할 때는 최대 5분까지 걸릴 수 있어요. 조금만 더 기다려 주세요.';
  }
  return '평소보다 조회가 오래 걸리고 있어요. 화면을 유지해 주시면 완료되는 대로 바로 보여드릴게요.';
}

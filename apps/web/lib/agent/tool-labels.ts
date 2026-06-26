/**
 * 도구 활동 화이트라벨 (CMP-DIRECT 채팅 UX 개선).
 *
 * 에이전트 SSE `tool_step` 이벤트의 `tool_name` 은 내부 식별자(write_todos,
 * confirm_address 등)다. 사용자에겐 생활어 라벨/문구로 바꿔 "지금 무엇을 하고 있는지"
 * 를 안심되게 보여 준다. 백엔드가 `summary`(사람이 읽는 요약)를 주면 그걸 우선 쓴다.
 */

export interface ToolDisplay {
  /** 짧은 명사 라벨 (예: "주소 확인"). */
  label: string;
  /** 진행 중 문구 (예: "주소를 확인하고 있어요"). */
  active: string;
  /** 완료 문구 (예: "주소 확인 완료"). */
  done: string;
  /** true 면 활동 UI 에 노출하지 않는다(순수 내부 단계). */
  hidden?: boolean;
}

const TOOL_DISPLAY: Record<string, ToolDisplay> = {
  search_address: {
    label: '주소 검색',
    active: '주소 후보를 찾고 있어요',
    done: '주소 후보를 찾았어요'
  },
  confirm_address: {
    label: '주소 확인',
    active: '주소를 확인하고 있어요',
    done: '주소를 확인했어요'
  },
  lookup_floorplan_candidates: {
    label: '보유 도면 확인',
    active: '내부 보유 도면을 찾고 있어요',
    done: '보유 도면을 확인했어요'
  },
  check_building_register: {
    label: '건축물대장 조회',
    active: '건축물대장을 조회하고 있어요',
    done: '건축물대장 조회를 시작했어요'
  },
  segment_floorplan: {
    label: '도면 분석',
    active: '도면을 분석하고 있어요',
    done: '도면 분석을 마쳤어요'
  },
  evaluate_rules: {
    label: '리모델링 가능성 평가',
    active: '리모델링 규정을 확인하고 있어요',
    done: '리모델링 가능성을 평가했어요'
  },
  emit_ui_component: {
    label: '결과 정리',
    active: '결과를 정리하고 있어요',
    done: '결과를 정리했어요'
  },
  // 카드 방출 도구 — 카드 자체가 보이는 결과라 활동 타임라인엔 숨긴다.
  emit_floorplan_request: { label: '', active: '', done: '', hidden: true },
  emit_address_candidates: { label: '', active: '', done: '', hidden: true },
  emit_judgment_summary: { label: '', active: '', done: '', hidden: true },
  // 순수 내부 결정 단계 — 사용자에게 노출할 의미가 없어 숨긴다.
  set_completion_decision: { label: '', active: '', done: '', hidden: true },
  // deepagents 내장 계획 도구 — 이제 PlanPanel 로 계획을 보여 주므로 활동 타임라인엔
  // 중복 노출하지 않는다(hidden). label/문구는 폴백/접근성용으로 남겨 둔다.
  write_todos: {
    label: '작업 계획',
    active: '필요한 작업을 정리하고 있어요',
    done: '작업 계획을 정리했어요',
    hidden: true
  }
};

const FALLBACK: ToolDisplay = {
  label: '처리',
  active: '필요한 작업을 처리하고 있어요',
  done: '처리를 마쳤어요'
};

export function toolDisplay(toolName: string): ToolDisplay {
  return TOOL_DISPLAY[toolName] ?? FALLBACK;
}

export type ToolStepStatus = 'started' | 'succeeded' | 'failed';

/**
 * 활동 한 줄에 보여 줄 문구를 만든다. 백엔드 `summary`(생활어)가 있으면 우선 사용하고,
 * 없으면 화이트라벨 문구로 폴백한다. 실패는 명확히 알린다.
 */
export function toolStepText(
  toolName: string,
  status: ToolStepStatus,
  summary?: string | null
): string {
  const display = toolDisplay(toolName);
  if (status === 'failed') {
    return summary?.trim() || `${display.label || '처리'}에 실패했어요`;
  }
  if (status === 'succeeded') {
    return summary?.trim() || display.done;
  }
  return display.active;
}

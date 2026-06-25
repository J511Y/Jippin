/**
 * 사전검토(우리집 체크) 대화형 퍼널 이벤트 추적 — CMP-DIRECT.
 *
 * `lead-cta.ts` 와 동일하게 `dataLayer` 에 push 한다 → GTM Custom Event 트리거 →
 * GA4 이벤트로 매핑(프로덕션 GTM 컨테이너에서 설정). GTM 스니펫보다 먼저 실행돼도
 * 안전하다(배열만 만들어 두면 GTM 로드 시 소비). 이벤트 이름은 GTM 트리거와 1:1.
 *
 * | 이벤트                      | 발화 시점                                  |
 * | --------------------------- | ------------------------------------------ |
 * | precheck_session_start      | 사전검토 세션 생성(첫 메시지 전송)         |
 * | precheck_address_select     | 주소 후보 카드에서 주소 선택               |
 * | precheck_floorplan_attach   | 도면 첨부(업로드+등록) 성공                |
 * | precheck_report_view        | 사전검토 리포트 페이지 진입                |
 */

type DataLayerEvent = { event: string } & Record<string, unknown>;

/** dataLayer push(SSR/미초기화 안전). lead-cta.ts 와 동일 패턴. */
function pushToDataLayer(event: DataLayerEvent): void {
  if (typeof window === 'undefined') return;
  const w = window as unknown as { dataLayer?: DataLayerEvent[] };
  w.dataLayer = w.dataLayer ?? [];
  w.dataLayer.push(event);
}

export const PRECHECK_SESSION_START_EVENT = 'precheck_session_start';
export const PRECHECK_ADDRESS_SELECT_EVENT = 'precheck_address_select';
export const PRECHECK_FLOORPLAN_ATTACH_EVENT = 'precheck_floorplan_attach';
export const PRECHECK_OVERLAY_VIEW_EVENT = 'precheck_overlay_view';
export const PRECHECK_WALL_SELECT_EVENT = 'precheck_wall_select';
export const PRECHECK_REPORT_VIEW_EVENT = 'precheck_report_view';

/** 세션 시작(첫 메시지로 세션 생성). entry: 예시칩 클릭('example') / 직접 입력('typed'). */
export function trackPrecheckSessionStart(entry: 'example' | 'typed'): void {
  pushToDataLayer({ event: PRECHECK_SESSION_START_EVENT, entry });
}

/** 주소 후보 카드에서 주소 선택. */
export function trackPrecheckAddressSelect(): void {
  pushToDataLayer({ event: PRECHECK_ADDRESS_SELECT_EVENT });
}

/** 도면 첨부(업로드+asset 등록) 성공. */
export function trackPrecheckFloorplanAttach(): void {
  pushToDataLayer({ event: PRECHECK_FLOORPLAN_ATTACH_EVENT });
}

/** 도면 오버레이 카드 노출(분석 결과 렌더). wall_other_count: 선택 가능한 비내력벽 후보 수. */
export function trackPrecheckOverlayView(wallOtherCount: number): void {
  pushToDataLayer({
    event: PRECHECK_OVERLAY_VIEW_EVENT,
    wall_other_count: wallOtherCount
  });
}

/** 오버레이에서 철거 대상 벽 선택 변경. selected_count: 현재 선택 수. */
export function trackPrecheckWallSelect(selectedCount: number): void {
  pushToDataLayer({
    event: PRECHECK_WALL_SELECT_EVENT,
    selected_count: selectedCount
  });
}

/** 사전검토 리포트 진입. has_report: 판정 결과 준비 여부. */
export function trackPrecheckReportView(hasReport: boolean): void {
  pushToDataLayer({ event: PRECHECK_REPORT_VIEW_EVENT, has_report: hasReport });
}

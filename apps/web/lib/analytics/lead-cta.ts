/**
 * 상담 신청(`/leads/new`) 인입 CTA 추적 SSOT (CMP-DIRECT).
 *
 * 운영자 요청은 "내부 상담 인입 버튼에 utm 태그를 달자"였지만, 내부 링크에 진짜
 * `utm_*` 파라미터를 붙이면 GA4 가 해당 시점에 세션을 끊고 원래 유입 소스
 * (검색·광고·SNS)를 내부 값으로 덮어써 어트리뷰션이 오염된다. utm 은 **외부 → 사이트**
 * 유입 전용이므로, 내부 인입 구분은 다음 두 갈래로 측정한다.
 *
 *  1) 내부 전용 쿼리 파라미터 `cta=<위치 식별자>` 를 `/leads/new` 링크에 부착
 *     — GTM 에서 URL 변수로 읽어 GA4 이벤트 파라미터로 매핑한다(세션/소스 귀속 무영향).
 *  2) 클릭 시점에 dataLayer `cta_click` 이벤트 push — 페이지 도달 전에 이탈해도
 *     클릭 자체를 셀 수 있고, GTM Custom Event 트리거로 바로 GA4 이벤트가 된다.
 *
 * 식별자 값 체계는 `<페이지>_<위치>` (snake_case). 새 인입 지점을 추가할 때는
 * `LEAD_CTA_IDS` 에 식별자를 등록하고 `LeadCtaButton` 또는 `leadsNewHref()` 를 쓴다.
 */

/** 내부 인입 구분 쿼리 파라미터 키. `utm_*` 예약 접두사는 의도적으로 피한다. */
export const LEAD_CTA_PARAM = 'cta';

/** dataLayer 이벤트 이름 — GTM Custom Event 트리거와 1:1. */
export const CTA_CLICK_EVENT = 'cta_click';
export const LEAD_SUBMIT_EVENT = 'lead_submit';

/**
 * 인입 지점 식별자 전체 목록 (GTM/GA4 보고서에 그대로 노출되는 값).
 *
 * | 식별자          | 위치                                          |
 * | --------------- | --------------------------------------------- |
 * | home_hero       | 홈 히어로 "전문가 상담"                       |
 * | home_quick_form | 홈 하단 "빠른 상담" 인라인 폼(링크 아님)      |
 * | prices_consult  | 가격 — "전문가 단건 상담" 플랜 CTA            |
 * | prices_permit   | 가격 — "행위허가 대행" 플랜 CTA               |
 * | faq_detail      | FAQ 상세 하단 "전문가 상담"                   |
 * | leads_list      | /leads 안내 페이지 "상담 신청서 작성하기"     |
 * | mypage_header   | 마이페이지 상담 현황 헤더 "새 상담"           |
 * | mypage_empty    | 마이페이지 상담 0건 빈 상태 "상담 신청하기"   |
 * | report_bottom   | 사전검토 리포트 하단 "전문가 상담 신청하기"   |
 * | sessions_gate   | /sessions ComingSoonGate 오버레이 CTA         |
 * | precheck_handoff| 사전검토 대화 중 상담 전환(HOLD_OR_HANDOFF) 카드 |
 * | precheck_report | 사전검토 판정 결과 카드(JudgmentSummary) 하단 상담 CTA |
 */
export const LEAD_CTA_IDS = [
  'home_hero',
  'home_quick_form',
  'prices_consult',
  'prices_permit',
  'faq_detail',
  'leads_list',
  'mypage_header',
  'mypage_empty',
  'report_bottom',
  'sessions_gate',
  'precheck_handoff',
  'precheck_report'
] as const;

export type LeadCtaId = (typeof LEAD_CTA_IDS)[number];

/**
 * `/leads/new` 인입 링크 href 빌더.
 *
 * 기존 `fromSession`(리포트 → 상담 전환 컨텍스트) 파라미터와 공존한다.
 * 하드코딩 문자열을 흩뿌리지 않기 위해 모든 인입 링크는 본 함수를 거친다.
 */
export function leadsNewHref(
  cta: LeadCtaId,
  extra?: { fromSession?: string }
): string {
  const params = new URLSearchParams();
  params.set(LEAD_CTA_PARAM, cta);
  if (extra?.fromSession) {
    params.set('fromSession', extra.fromSession);
  }
  return `/leads/new?${params.toString()}`;
}

type DataLayerEvent = { event: string } & Record<string, unknown>;

/**
 * dataLayer push. GTM 스니펫보다 먼저 실행돼도 안전하다 — 배열만 만들어 두면
 * GTM 이 로드 시점에 기존 항목을 그대로 소비한다. `@next/third-parties` 의
 * `sendGTMEvent` 는 GTM 미초기화 환경(로컬/프리뷰)에서 경고를 뿜으므로 직접 push 한다.
 */
function pushToDataLayer(event: DataLayerEvent): void {
  if (typeof window === 'undefined') return;
  const w = window as unknown as { dataLayer?: DataLayerEvent[] };
  w.dataLayer = w.dataLayer ?? [];
  w.dataLayer.push(event);
}

/**
 * CTA 클릭 추적. GTM 설정: Custom Event 트리거 `cta_click` → GA4 이벤트
 * `cta_click` (파라미터 `cta_id`, `cta_destination`).
 */
export function trackLeadCtaClick(cta: LeadCtaId): void {
  pushToDataLayer({
    event: CTA_CLICK_EVENT,
    cta_id: cta,
    cta_destination: '/leads/new'
  });
}

/**
 * 현재 URL 에서 `cta` 파라미터를 읽는다. 임의 외부 값(파라미터 변조·오타 링크)이
 * 보고서를 오염시키지 않도록 등록된 식별자만 인정한다.
 */
export function readLeadCtaFromLocation(): LeadCtaId | null {
  if (typeof window === 'undefined') return null;
  const raw = new URLSearchParams(window.location.search).get(LEAD_CTA_PARAM);
  return raw && (LEAD_CTA_IDS as readonly string[]).includes(raw)
    ? (raw as LeadCtaId)
    : null;
}

/**
 * 상담 신청 폼 제출 **성공** 시점 추적(실제 전환). GTM 설정: Custom Event 트리거
 * `lead_submit` → GA4 `generate_lead` 권장 이벤트로 매핑.
 *
 * @param sourceForm 백엔드 `source_form` 과 동일 값('main_page' | 'lead_page').
 * @param cta 인입 식별자. 생략하면 현재 URL 의 `cta` 파라미터에서 읽고,
 *            그것도 없으면 '(direct)' (북마크·직접 진입·외부 유입).
 */
export function trackLeadSubmit(
  sourceForm: 'main_page' | 'lead_page' | 'precheck_session',
  cta?: LeadCtaId
): void {
  pushToDataLayer({
    event: LEAD_SUBMIT_EVENT,
    source_form: sourceForm,
    cta_id: cta ?? readLeadCtaFromLocation() ?? '(direct)'
  });
}

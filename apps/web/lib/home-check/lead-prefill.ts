/**
 * 우리집 체크 → 상담 인입 라우팅 헬퍼 (CMP-DIRECT, ADR-0008).
 *
 * 위반/확인필요 결과에서 상담 폼으로 이동할 때, 출처(checkId)와 조회 주소를 쿼리로 넘겨
 * `ConsultationLeadForm` 이 주소를 prefill 한다. source_form='property_check' 매핑은
 * 백엔드가 처리하므로 web 은 라우팅/프리필 쿼리만 책임진다.
 */

/** 우리집 체크 인입 식별 쿼리 키. ConsultationLeadForm 이 이 값들을 읽어 prefill 한다. */
export const HOME_CHECK_FROM = 'home-check';

/**
 * 상담 신청서(`/leads/new`) href. 우리집 체크 출처/주소를 쿼리로 부착한다.
 * 주소가 없으면(체크 미완) checkId 만 넘긴다.
 */
export function homeCheckLeadHref(checkId: string, address?: string | null): string {
  const params = new URLSearchParams();
  params.set('from', HOME_CHECK_FROM);
  params.set('checkId', checkId);
  if (address) {
    params.set('address', address);
  }
  return `/leads/new?${params.toString()}`;
}

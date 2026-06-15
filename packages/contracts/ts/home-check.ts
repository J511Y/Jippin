/* eslint-disable */
/**
 * THIS FILE IS AUTO-GENERATED — DO NOT EDIT BY HAND.
 * Source: packages/contracts/schemas/*.schema.json
 * Regenerate: pnpm -C packages/contracts run generate
 */

/**
 * 우리집 체크 조회 잡 + 결과 리포트. CODEF 세움터 집합건축물대장 전유부+표제부 응답을 PII-free 로 매핑한 정본. 결정: docs/adr/0008-home-check-building-register.md. 소유자/설계자 성명·주민번호·세움터 password 등 PII 는 절대 포함하지 않는다(원본 PDF 는 Storage 보관).
 */
export interface HomeCheckJob {
  /**
   * 스키마 버전 (semver).
   */
  schema_version: "1.0.0";
  /**
   * 조회 잡 UUID.
   */
  id: string;
  /**
   * 잡 상태. needs_input = 동·호 자동매칭 실패 또는 보안문자(reqSecureNo) 발생 폴백.
   */
  status: "pending" | "querying" | "needs_input" | "completed" | "failed";
  /**
   * 종합 신호등. status=completed 일 때만 채워진다. violation=🔴, caution=🟡, normal=🟢.
   */
  signal?: "violation" | "caution" | "normal" | null;
  /**
   * 잡 생성 시각 (ISO-8601).
   */
  created_at?: string | null;
  /**
   * 잡 갱신 시각 (ISO-8601).
   */
  updated_at?: string | null;
  /**
   * 실패 사유 (status=failed).
   */
  error?: ErrorInfo | null;
  /**
   * 추가 입력 요구 (status=needs_input).
   */
  needs_input?: NeedsInput | null;
  /**
   * 결과 리포트 (status=completed).
   */
  report?: HomeCheckReport | null;
}
export interface ErrorInfo {
  /**
   * 오류 코드 (예: UPSTREAM_UNAVAILABLE, NOT_FOUND, INVALID_ADDRESS).
   */
  code: string;
  /**
   * 사용자 안내용 메시지.
   */
  message: string;
}
export interface NeedsInput {
  /**
   * 폴백 종류. dong_ho=동·호 자동매칭 실패로 선택 필요, secure_no=보안문자 입력 필요.
   */
  kind: "dong_ho" | "secure_no";
  /**
   * 사용자 안내용 메시지.
   */
  message: string;
}
/**
 * 전유부+표제부 병행 조회 결과의 PII-free 리포트.
 */
export interface HomeCheckReport {
  /**
   * 종합 신호등.
   */
  signal: "violation" | "caution" | "normal";
  violation: Violation;
  address: AddressInfo;
  /**
   * 전유부분 요약 (전유부 resOwnedList 중 resType='0').
   */
  exclusive_part?: ExclusivePart | null;
  /**
   * 건물(표제부) 요약.
   */
  building?: BuildingHeading | null;
  /**
   * 전유부+표제부 변동사항(resChangeList) 통합 타임라인. 확장 등재 여부 대조의 핵심.
   */
  change_history?: ChangeEntry[];
  /**
   * 전유부 공동주택가격(resPriceList).
   */
  prices?: PriceEntry[];
  /**
   * 발급 PDF 다운로드 링크(전유부/표제부).
   */
  documents?: DocumentRef[];
  /**
   * 🟡 caution 판정 사유(예: '신고하신 확장이 대장 변동이력에 없음', '전유부 기준이라 건물 위반표시는 별도 확인 필요').
   */
  caution_reasons?: string[];
  /**
   * 발급 메타데이터.
   */
  meta?: ReportMeta | null;
  /**
   * 면책 고지(참고용·최종판단은 관할 행정청/전문가).
   */
  disclaimer: string;
}
/**
 * 노란딱지(위반건축물) 판정. is_violation = 전유부 OR 표제부 resViolationStatus=='위반건축물'.
 */
export interface Violation {
  /**
   * 종합 위반 여부.
   */
  is_violation: boolean;
  /**
   * 전유부 위반표시.
   */
  exclusive?: boolean | null;
  /**
   * 표제부(건물) 위반표시.
   */
  heading?: boolean | null;
  /**
   * 원본 resViolationStatus 값(예: '위반건축물').
   */
  raw?: string | null;
}
export interface AddressInfo {
  /**
   * 도로명주소.
   */
  road_addr?: string | null;
  /**
   * 지번주소.
   */
  jibun_addr?: string | null;
  /**
   * 동.
   */
  dong?: string | null;
  /**
   * 호.
   */
  ho?: string | null;
}
export interface ExclusivePart {
  /**
   * 전유면적(㎡).
   */
  area_m2?: number | null;
  /**
   * 용도(resUseType).
   */
  use_type?: string | null;
  /**
   * 구조(resStructure).
   */
  structure?: string | null;
  /**
   * 층(resFloor).
   */
  floor?: string | null;
}
export interface BuildingHeading {
  /**
   * 주용도.
   */
  main_use?: string | null;
  /**
   * 층수(예: '지하 1층 지상 12층').
   */
  floors?: string | null;
  /**
   * 사용승인일.
   */
  approval_date?: string | null;
  /**
   * 허가일.
   */
  permit_date?: string | null;
  /**
   * 표제부 고유번호.
   */
  comm_unique_no?: string | null;
}
export interface ChangeEntry {
  /**
   * 변동일자(정규화 문자열).
   */
  date?: string | null;
  /**
   * 변동내용 및 원인(resChangeReason).
   */
  reason: string;
  /**
   * 출처 대장(전유부/표제부).
   */
  source: "exclusive" | "heading";
}
export interface PriceEntry {
  /**
   * 기준일자.
   */
  reference_date?: string | null;
  /**
   * 공동주택가격(원, 정수).
   */
  base_price?: number | null;
}
export interface DocumentRef {
  /**
   * PDF 종류.
   */
  kind: "exclusive_part" | "building_heading";
  /**
   * 백엔드 서명 다운로드 URL(단기 만료).
   */
  url?: string | null;
}
export interface ReportMeta {
  /**
   * 전유부 고유번호.
   */
  comm_unique_no?: string | null;
  /**
   * 전유부 문서확인번호.
   */
  res_doc_no?: string | null;
  /**
   * 발급일자.
   */
  issue_date?: string | null;
  /**
   * 발급기관.
   */
  issue_org?: string | null;
  /**
   * 조회(스크래핑) 시각.
   */
  queried_at?: string | null;
}

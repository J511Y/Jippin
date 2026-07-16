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
   * 스키마 버전 (semver). 1.3.0: phase(진행 단계, 정보성 open string) 추가 — 대기 화면 실시간 스텝 표시용. 1.2.0: report 에 extension_check(신고확장↔변동사항 LLM 대조) 추가 + prices(공동주택가격) 제거 — 우리집 체크는 확장 등재 여부가 목적이라 가격/속성 노이즈 제외.
   */
  schema_version: "1.3.0";
  /**
   * 조회 잡 UUID.
   */
  id: string;
  /**
   * 잡 상태. needs_input = 동·호 자동매칭 실패 또는 보안문자(reqSecureNo) 발생 폴백.
   */
  status: "pending" | "querying" | "needs_input" | "completed" | "failed";
  /**
   * 백그라운드 파이프라인 진행 단계(정보성 — status 가 상태 기계 정본). 알려진 값: received → issuing_registers → judging → saving_report. status=pending|querying 일 때만 의미가 있으며 터미널 상태에선 마지막 값이 남는다. 워커 통합/세분화로 값이 추가될 수 있으므로 엄격 enum 이 아니다 — 클라이언트는 미지의 값을 일반 대기 문구로 폴백해야 한다.
   */
  phase?: string | null;
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
   * 폴백 종류. dong_ho=주소·동·호 후보 선택 필요, secure_no=보안문자 입력 필요.
   */
  kind: "dong_ho" | "secure_no";
  /**
   * 사용자 안내용 메시지.
   */
  message: string;
  /**
   * kind=dong_ho 일 때 사용자가 골라야 하는 축(address=주소, dong=동, ho=호). options 와 함께 채워진다.
   */
  field?: "address" | "dong" | "ho" | null;
  /**
   * 선택 후보 목록(CODEF reqAddrList/reqDongNumList/reqHoNumList 정규화). 사용자가 하나를 골라 재개한다. CODEF 자동매칭이 0건/복수건일 때만 채워진다.
   */
  options?: NeedsInputOption[] | null;
}
/**
 * 동·호·주소 선택 후보 1건.
 */
export interface NeedsInputOption {
  /**
   * 재개(continue) 시 selection 으로 그대로 전송할 CODEF 식별자(호=commHoNum, 동=commDongNum, 주소=지번/도로명).
   */
  value: string;
  /**
   * 사용자 표시용 명칭(호=reqHo, 동=reqDong, 주소=도로명/지번).
   */
  label: string;
  /**
   * 전유면적(㎡, reqArea). 호 후보에만 제공 — 같은 번호의 호를 면적으로 구분하는 데 쓴다.
   */
  area?: string | null;
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
   * 사용자가 신고한 확장·개조 부위와 대장 변동사항을 대조한 LLM 판정. 사용자 입력이 있을 때만 채워진다. 노란딱지(violation)와 별개 축.
   */
  extension_check?: ExtensionCheck | null;
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
/**
 * 신고 확장 ↔ 대장 변동사항 대조(LLM). 노란딱지(violation.is_violation)와 별개 축. verdict=violation 이면 종합 signal 을 violation 으로 올리되 violation.is_violation(공식 표시)은 건드리지 않는다.
 */
export interface ExtensionCheck {
  /**
   * violation=신고했으나 미등재, legal=등재확인/확장없음, uncertain=대조모호.
   */
  verdict: "violation" | "legal" | "uncertain";
  /**
   * 한국어 판정 근거(대장 변동사항 기준).
   */
  reason?: string | null;
  /**
   * 사용자가 신고한 확장 부위.
   */
  reported_areas?: string[];
  /**
   * 변동사항에서 등재 확인된 부위.
   */
  matched_areas?: string[];
  /**
   * 신고했으나 미등재된 부위(위반 소지).
   */
  unrecorded_areas?: string[];
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

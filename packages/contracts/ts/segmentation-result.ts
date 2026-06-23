/* eslint-disable */
/**
 * THIS FILE IS AUTO-GENERATED — DO NOT EDIT BY HAND.
 * Source: packages/contracts/schemas/*.schema.json
 * Regenerate: pnpm -C packages/contracts run generate
 */

/**
 * 평면도 세그멘테이션 도구(HuggingFace 엣지 엔드포인트) 의 구조화 결과. 도구는 절대 raise 하지 않고 본 형태를 반환한다 — 엔드포인트 미배포/콜드스타트/타임아웃도 ok=false 로 표현된다.
 */
export interface SegmentationResult {
  /**
   * 스키마 버전 (semver). 1.1.0: error_code 에 NO_IMAGE/NOT_SCANNED 추가(추가형).
   */
  schema_version: "1.1.0";
  /**
   * 추론 성공 여부. false 면 error_code 가 채워지고 에이전트는 degrade 한다.
   */
  ok: boolean;
  /**
   * ok=false 시 안정적 에러 코드. 미배포/DNS/404=ENDPOINT_UNAVAILABLE, 503=COLD_START_TIMEOUT 등.
   */
  error_code?:
    | "SEGMENTATION_ENDPOINT_UNAVAILABLE"
    | "SEGMENTATION_COLD_START_TIMEOUT"
    | "SEGMENTATION_TIMEOUT"
    | "SEGMENTATION_UPSTREAM_ERROR"
    | "SEGMENTATION_BAD_REQUEST"
    | "SEGMENTATION_BAD_RESPONSE"
    | "SEGMENTATION_NO_IMAGE"
    | "SEGMENTATION_NOT_SCANNED"
    | null;
  /**
   * 저장된 segmentation_mask floorplan_assets.id (있으면). 마스크 이미지는 Storage 에만 두고 여기엔 포인터만.
   */
  mask_asset_id?: string | null;
  /**
   * 검출된 인스턴스 요약 목록. 좌표·원본 마스크는 포함하지 않는다(요약만).
   */
  instances?: Instance[];
  /**
   * 사람이 읽을 수 있는 짧은 요약 (예: '내력벽 후보 3, 비내력벽 후보 5').
   */
  summary?: string | null;
}
export interface Instance {
  /**
   * 모델 클래스 라벨. STR 5 + SPA 13 (floor-plan-model-train 정합).
   */
  label:
    | "door"
    | "window"
    | "wall_reinforced_concrete"
    | "wall_other"
    | "wall_unknown"
    | "space_multipurpose"
    | "space_elevator_hall"
    | "space_stairwell"
    | "space_living_room"
    | "space_bedroom"
    | "space_kitchen"
    | "space_entrance"
    | "space_balcony"
    | "space_bathroom"
    | "space_ac_room"
    | "space_dress_room"
    | "space_other"
    | "space_elevator";
  /**
   * 해당 라벨 인스턴스 수.
   */
  count: number;
  /**
   * 평균 신뢰도.
   */
  mean_confidence?: number | null;
}

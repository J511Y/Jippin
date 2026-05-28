/* eslint-disable */
/**
 * THIS FILE IS AUTO-GENERATED — DO NOT EDIT BY HAND.
 * Source: packages/contracts/schemas/*.schema.json
 * Regenerate: pnpm -C packages/contracts run generate
 */

/**
 * 공통 판단 스키마 — AI 분석·OVERLAY 선택·CHAT 보완값이 CHAT/session 에서 병합되어 FLOW_GUARD 평가를 거쳐 RULE 의 단일 입력 컨트랙트가 된다. SDD §5.2 정본.
 */
export interface CommonJudgmentSchema {
  /**
   * 세션 추적 식별자.
   */
  session_id: string;
  /**
   * AI 분석 시점 (ISO-8601).
   */
  analyzed_at: string;
  /**
   * 스키마 버전 (semver). 본 ADR-0001 / CMP-527 시점 고정값.
   */
  schema_version: "1.0.0";
  building_info: BuildingInfo;
  /**
   * 공간 객체 목록.
   */
  space_objects: SpaceObject[];
  /**
   * 벽체 객체 목록.
   */
  wall_objects: WallObject[];
  vlm_supplement?: VlmSupplement;
  /**
   * OVERLAY 가 수집한 사용자 선택 철거 대상 벽체 region_id 목록.
   */
  selected_walls: string[];
  /**
   * 사용자가 지정한 변경 희망 공간 region_id. 미지정 시 null.
   */
  target_space?: string | null;
  judgment_values: JudgmentValues;
  /**
   * RULE 진입 가능 여부. false면 CHAT/FLOW_GUARD 가 추가 정보를 수집한다.
   */
  rule_input_ready: boolean;
}
export interface BuildingInfo {
  /**
   * 도로명주소 API 가 정규화한 주소 문자열.
   */
  address_normalized: string;
  /**
   * 동 식별자.
   */
  dong?: string | null;
  /**
   * 호 식별자.
   */
  ho?: string | null;
  /**
   * 층수. 룰 평가의 1차 입력.
   */
  floor?: number | null;
  /**
   * 건물 전체 층수.
   */
  total_floors?: number | null;
  /**
   * 건물 유형.
   */
  building_type: "APARTMENT" | "OFFICETEL" | "ROW_HOUSE" | "MULTI_FAMILY" | "ETC";
  /**
   * 추정 준공년도.
   */
  approx_built_year?: number | null;
}
export interface SpaceObject {
  id: string;
  /**
   * 사람이 읽는 라벨 (예: '거실', '주방', '대피공간').
   */
  label: string;
  /**
   * 정규화된 공간 타입.
   */
  type:
    | "LIVING_ROOM"
    | "KITCHEN"
    | "BEDROOM"
    | "BATHROOM"
    | "BALCONY"
    | "EVACUATION_SPACE"
    | "STAIRWELL"
    | "CORRIDOR"
    | "ETC";
  /**
   * 공간 폴리곤 좌표.
   *
   * @minItems 3
   */
  mask_coords: [MaskCoord, MaskCoord, MaskCoord, ...MaskCoord[]];
  /**
   * 세그멘테이션 신뢰도.
   */
  confidence: number;
  /**
   * 이 객체를 생성한 엔진.
   */
  source_engine: "MASK2FORMER" | "SAM2" | "VLM" | "HITL";
}
/**
 * 도면 좌표계 위 한 점 (px or normalized).
 */
export interface MaskCoord {
  x: number;
  y: number;
}
export interface WallObject {
  id: string;
  /**
   * 벽체 종류. UNKNOWN 은 보완 루프 트리거.
   */
  wall_type: "NON_LOAD_BEARING" | "LOAD_BEARING" | "UNKNOWN";
  confidence: number;
  /**
   * 벽체 선분/폴리라인 좌표.
   *
   * @minItems 2
   */
  coords: [MaskCoord, MaskCoord, ...MaskCoord[]];
  source_engine: "MASK2FORMER" | "SAM2" | "VLM" | "HITL";
}
/**
 * VLM 재분류·주석 결과. 분석이 보류된 경우 null 또는 부재.
 */
export interface VlmSupplement {
  /**
   * VLM 프로바이더 (ADR-0001 §7 의 VLMClient 인터페이스 호환).
   */
  provider?: "OPENAI" | "ANTHROPIC" | "GOOGLE" | "OTHER";
  /**
   * 예: 'gpt-5.4-mini', 'gpt-5.5'.
   */
  model?: string;
  /**
   * VLM 자유 텍스트 주석.
   */
  notes?: string[];
  /**
   * Mask2Former 라벨을 VLM 이 교정한 결과.
   */
  reclassifications?: {
    object_id: string;
    new_label: string;
    reason: string;
  }[];
}
/**
 * CHAT 이 사용자로부터 수집한 RULE 입력 변수 모음. SDD §5.2.
 */
export interface JudgmentValues {
  /**
   * 건물 층수.
   */
  floor_count?: number | null;
  /**
   * 스프링클러 설치 여부.
   */
  has_sprinkler?: boolean | null;
  /**
   * 대피공간 존재 여부.
   */
  has_evacuation_space?: boolean | null;
  /**
   * 계단실 수.
   */
  stairwell_count?: number | null;
  /**
   * 창호 형태.
   */
  window_form?: "FIXED" | "OPENABLE" | "FOLDING" | "SLIDING" | "OTHER" | null;
  /**
   * 발코니 접합 여부.
   */
  balcony_attached?: boolean | null;
  /**
   * 기존 행위허가 이력 존재 여부.
   */
  permit_history_known?: boolean | null;
}

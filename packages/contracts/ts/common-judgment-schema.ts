/* eslint-disable */
/**
 * THIS FILE IS AUTO-GENERATED — DO NOT EDIT BY HAND.
 * Source: packages/contracts/schemas/*.schema.json
 * Regenerate: pnpm -C packages/contracts run generate
 */

/**
 * 창호 형태 어휘 — JudgmentValues.window_form 과 VlmSupplement.judgment_hints.window_form 이 공유한다(1.4.0 에서 공용 정의로 승격, 생성 바인딩의 WindowForm 심볼 보존).
 */
export type WindowForm = "FIXED" | "OPENABLE" | "FOLDING" | "SLIDING" | "OTHER";

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
   * 스키마 버전 (semver). 1.4.0: vlm_supplement 에 confidence/is_floorplan/judgment_hints(코드가 이미 영속하던 필드의 계약 정합화) + region_assessments(벽·창호 영역별 VLM 위치·구조/경계 의견 — 선택 벽 종합 판단, 창호 경계 자동 반영, 오버레이 재제공 안내에 사용) 추가(추가형, 하위호환). 1.3.0: vlm_supplement 의 null 허용을 스키마에 명문화(설명은 원래 'null 또는 부재'였으나 타입이 미인코딩 — 이번 런에 VLM 산출이 없음을 null 로 영속하는 #vlm-freshness 경로 지원). 1.1.0: window_objects/selected_windows/window_demolition_boundary 추가(추가형, 하위호환 — 창호 철거 검토 지원). 1.2.0: register_supplement 추가(추가형, 하위호환 — 건축물대장 확인 사실의 리포트 반영).
   */
  schema_version: "1.4.0";
  building_info: BuildingInfo;
  /**
   * 공간 객체 목록.
   */
  space_objects: SpaceObject[];
  /**
   * 벽체 객체 목록.
   */
  wall_objects: WallObject[];
  /**
   * 창호 객체 목록 (1.1.0 추가). 오버레이의 창호 선택(발코니-실 경계 창호 철거 검토)을 지원한다.
   */
  window_objects?: WindowObject[];
  /**
   * VLM 재분류·주석 결과. 분석이 보류됐거나 이번 런에 VLM 산출이 없으면 null 또는 부재 (1.3.0 에서 null 허용 명문화).
   */
  vlm_supplement?: VlmSupplement | null;
  register_supplement?: RegisterSupplement;
  /**
   * OVERLAY 가 수집한 사용자 선택 철거 대상 벽체 region_id 목록. 기능명세서 §2.5 의 target_wall(단수)를 대체한다 — 복수 벽 동시 선택을 지원하는 정본.
   */
  selected_walls: string[];
  /**
   * OVERLAY 가 수집한 사용자 선택 철거 검토 대상 창호 region_id 목록 (1.1.0 추가). 외기 직접 접촉 여부 판단은 JudgmentValues.window_demolition_boundary 로 위임한다.
   */
  selected_windows?: string[];
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
 * 창호 객체 1건 (1.1.0 추가). 외창/내창 구분은 세그멘테이션이 못 하므로 객체에는 두지 않고, 판단은 CHAT(LLM)+사용자 확인으로 위임한다.
 */
export interface WindowObject {
  id: string;
  confidence: number;
  /**
   * 창호 선분/폴리라인 좌표.
   *
   * @minItems 2
   */
  coords: [MaskCoord, MaskCoord, ...MaskCoord[]];
  source_engine: "MASK2FORMER" | "SAM2" | "VLM" | "HITL";
}
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
  /**
   * VLM 전체 분석 신뢰도 0~1 (1.4.0 명문화). 0.6 미만이면 ANALYSIS_LOW_CONFIDENCE 로 재확인 권장.
   */
  confidence?: number | null;
  /**
   * VLM 이 이미지를 실제 평면도로 봤는지 (1.4.0 명문화). 명시적 false 만 '평면도 아님'으로 취급한다.
   */
  is_floorplan?: boolean;
  /**
   * VLM 이 도면에서 직접 읽은 룰 입력 힌트 (1.4.0 명문화). 어휘/타입은 JudgmentValues 와 동일하며, 못 읽은 항목은 null. 우선순위: CHAT 전달값 > 이 힌트 > 룰엔진 보수적 가정.
   */
  judgment_hints?: {
    has_sprinkler?: boolean | null;
    has_evacuation_space?: boolean | null;
    stairwell_count?: number | null;
    window_form?: WindowForm | null;
    fire_zone?: boolean | null;
    balcony_attached?: boolean | null;
  };
  /**
   * VLM 의 벽·창호 영역별 위치·의견 (1.4.0 추가, #region-assessments). CHAT 이 선택 벽을 세그멘테이션 분류와 종합해 설명하고, 창호 경계(window_demolition_boundary)를 자동 반영하며, 사용자에게 어느 영역이 어디인지 안내하는 근거.
   */
  region_assessments?: {
    /**
     * 세그멘테이션 region_id (wall_objects/window_objects 의 id 와 동일).
     */
    region_id: string;
    /**
     * 영역 종류 — 서버가 region 출처로 정한다(VLM 출력 아님).
     */
    kind: "wall" | "window";
    /**
     * 비전문가용 생활어 위치 (예: '거실과 침실1 사이', '거실과 발코니 사이').
     */
    location: string;
    /**
     * 벽(kind=wall): NON_LOAD_BEARING/LOAD_BEARING/UNCERTAIN. 창호(kind=window): BALCONY_BOUNDARY(발코니-실내 경계 창)/EXTERIOR(외기 직접 접촉 창)/UNCERTAIN. kind 별 어휘 밖은 서버가 UNCERTAIN 으로 강등한다.
     */
    assessment: "NON_LOAD_BEARING" | "LOAD_BEARING" | "UNCERTAIN" | "BALCONY_BOUNDARY" | "EXTERIOR";
    /**
     * 근거 한 문장.
     */
    reason?: string;
  }[];
}
/**
 * 건축물대장 조회(read-back)에서 확인한 리포트 반영용 사실 (1.2.0 추가). 미조회 세션은 부재.
 */
export interface RegisterSupplement {
  /**
   * 위반건축물 표시 여부.
   */
  is_violation?: boolean;
  /**
   * 전유부 층 표기 (예: '3층') — floor_count 확인 근거.
   */
  unit_floor?: string | null;
  /**
   * 행위허가 관련 변동 이력(시간순 최근 일부).
   */
  permit_entries?: {
    date?: string | null;
    reason?: string | null;
    /**
     * 표시 라벨 (전유부/표제부/대장).
     */
    source?: string | null;
  }[];
  /**
   * 조회 시점 세션 주소의 내용 기반 지문 — 주소 변경 시 stale supplement 무효화 근거.
   */
  address_fingerprint?: string;
  /**
   * 조회(read-back) 시점.
   */
  checked_at?: string;
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
  window_form?: WindowForm | null;
  /**
   * 발코니 접합 여부.
   */
  balcony_attached?: boolean | null;
  /**
   * 기존 행위허가 이력 존재 여부.
   */
  permit_history_known?: boolean | null;
  /**
   * 철거 검토 대상 창호가 접한 경계 (1.1.0 추가). EXTERIOR=외기와 직접 접한 최외곽 창호(철거 불가), BALCONY_BOUNDARY=발코니와 실내(거실 등) 사이 경계 창호(철거 시 발코니 확장으로 검토). 도면 촬영 품질이 흔들려 기하 판정이 어려우므로 CHAT(LLM)이 VLM 관찰·대화로 판단해 채우고, 모르면 null(룰엔진이 HOLD 로 재확인).
   */
  window_demolition_boundary?: "EXTERIOR" | "BALCONY_BOUNDARY" | null;
}

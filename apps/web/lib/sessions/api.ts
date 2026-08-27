/**
 * 사전검토 세션 백엔드 API 호출 (CMP-DIRECT).
 *
 * `apiClient`(axios)가 `lib/auth-token` 의 Bearer 토큰을 자동 부착한다. 익명 사용자도
 * 호출 전 `ensureAnonymousSession()` 으로 세션을 보장해야 한다(leads/home-check 패턴).
 */

import { apiClient } from '@/lib/api-client';
import { setAccessToken } from '@/lib/auth-token';
import { createClient } from '@/lib/supabase/client';

/**
 * 기존 Supabase 세션 토큰을 메모리에 동기화한다(없으면 no-op) — 읽기 페이지 마운트용.
 * 익명 세션을 새로 만들지 않는다(`ensureAnonymousSession` 과 달리 explicit-intent 불필요).
 * 토큰이 없으면 이어지는 API 호출이 401 을 받고 호출부가 빈 상태로 처리한다.
 */
export async function syncExistingToken(): Promise<boolean> {
  try {
    const {
      data: { session }
    } = await createClient().auth.getSession();
    if (session?.access_token) {
      setAccessToken(session.access_token);
      return true;
    }
  } catch {
    /* getSession 실패 — 토큰 없음으로 처리 */
  }
  return false;
}

export type SessionStatus =
  | 'draft'
  | 'address_ready'
  | 'floorplan_selected'
  | 'analyzing'
  | 'awaiting_overlay'
  | 'collecting_info'
  | 'ready_for_rule'
  | 'report_ready'
  | 'handoff'
  | 'expired'
  | 'deleted';

export interface SessionResponse {
  id: string;
  user_id: string;
  status: SessionStatus;
  address_id: string | null;
  selected_floorplan_asset_id: string | null;
  judgment_schema: Record<string, unknown>;
  completion_decision: string | null;
  /** 리포트 준비 여부 — 백엔드가 verdict(rule_eval_result) 존재로 판정. */
  has_report: boolean;
  /** 도면 교체 이력(#legacy-judgment-freshness) — 단건 GET 에서만 파생(true/false),
   *  목록/생성 응답과 구 API 는 null/부재. 소비자는 `=== true` 로만 판정할 것. */
  floorplan_replaced?: boolean | null;
  last_activity_at: string;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SessionAddressPayload {
  road_address?: string | null;
  jibun_address?: string | null;
  apartment_name?: string | null;
  building_dong?: string | null;
  unit_ho?: string | null;
}

export interface FloorplanAssetPayload {
  bucket: string;
  object_key: string;
  content_type: string;
  byte_size: number;
  sha256_hex?: string | null;
}

export interface FloorplanAssetResponse {
  id: string;
  session_id: string | null;
  kind: string;
  bucket: string;
  object_key: string;
  content_type: string;
  byte_size: number;
  scan_status: string;
}

/** 계약 estimate-result.schema.json $defs/MoneyRange. */
export interface MoneyRange {
  currency: 'KRW';
  min: number;
  max: number;
  basis?: string | null;
}

/** 계약 estimate-result.schema.json $defs/EstimateItem (1.1.0). */
export interface EstimateItem {
  code: string;
  label: string;
  amount_min?: number | null;
  amount_max?: number | null;
  unit_amount?: number | null;
  unit?: string | null;
  note?: string | null;
}

/** 계약 estimate-result.schema.json (1.1.0) — REPORT-003 예상 견적 정본 shape. */
export interface EstimateResult {
  schema_version: string;
  permit_agency_fee_estimate?: MoneyRange;
  fire_panel_estimate?: MoneyRange;
  fire_glass_estimate?: MoneyRange;
  total_range: MoneyRange;
  assumptions: string[];
  policy_version: string;
  variance_notes?: string[];
  consultation_required: boolean;
  items?: EstimateItem[];
  vat_included?: boolean;
  source_url?: string;
  disclaimer?: string;
}

export interface SessionReportResponse {
  schema_version: string;
  session_id: string;
  status: SessionStatus;
  rule_eval_result: Record<string, unknown>;
  evaluated_at: string | null;
  address: Record<string, unknown> | null;
  estimate: EstimateResult | null;
}

export async function createSession(): Promise<SessionResponse> {
  const response = await apiClient.post<SessionResponse>('/sessions', {});
  return response.data;
}

export async function listSessions(): Promise<SessionResponse[]> {
  const response = await apiClient.get<SessionResponse[]>('/sessions');
  return response.data;
}

export async function getSession(id: string): Promise<SessionResponse> {
  const response = await apiClient.get<SessionResponse>(`/sessions/${id}`);
  return response.data;
}

export async function upsertSessionAddress(
  id: string,
  payload: SessionAddressPayload
): Promise<void> {
  await apiClient.put(`/sessions/${id}/address`, payload);
}

export async function createFloorplanAsset(
  id: string,
  payload: FloorplanAssetPayload
): Promise<FloorplanAssetResponse> {
  const response = await apiClient.post<FloorplanAssetResponse>(
    `/sessions/${id}/floorplan-assets`,
    payload
  );
  return response.data;
}

export async function getSessionReport(id: string): Promise<SessionReportResponse> {
  const response = await apiClient.get<SessionReportResponse>(`/sessions/${id}/report`);
  return response.data;
}

/** 발부된 PDF 리포트의 단기 서명 다운로드 링크(`POST /sessions/{id}/report/pdf`). */
export interface SessionReportPdfResponse {
  url: string;
  report_id: string;
  byte_size: number;
  generated_at: string;
  expires_in: number;
}

/**
 * 디자인된 PDF 리포트를 발부(서버 생성·Storage 보관)하고 단기 서명 URL 을 받는다.
 * 판정 미준비면 404 REPORT_NOT_READY 가 떨어진다(호출부가 안내).
 */
export async function issueSessionReportPdf(
  id: string
): Promise<SessionReportPdfResponse> {
  const response = await apiClient.post<SessionReportPdfResponse>(
    `/sessions/${id}/report/pdf`
  );
  return response.data;
}

/** 오버레이가 도면 이미지를 표시할 짧은-수명 서명 URL 을 발급받는다(렌더 시점 호출). */
export async function getFloorplanAssetSignedUrl(
  sessionId: string,
  assetId: string
): Promise<string> {
  const res = await apiClient.get<{ url: string }>(
    `/sessions/${sessionId}/floorplan-assets/${assetId}/signed-url`
  );
  return res.data.url;
}

/**
 * OVERLAY-002: 사용자가 선택한 철거 희망 비내력벽·창호 region_id 목록을 판단스키마에 기록.
 * `windowRegionIds` 를 생략하면 창호 선택은 건드리지 않는다(하위호환).
 * `assetId`(카드가 유래한 도면)를 주면 서버가 현재 선택 도면과 대조해, 도면이 교체된
 * 뒤의 옛 카드 제출을 409 로 거절한다 — region id 는 다른 도면에서도 재사용되므로
 * id 존재 검증만으로는 다른 도면의 벽이 선택될 수 있다(#overlay-asset-fingerprint).
 */
export async function updateSelectedWalls(
  sessionId: string,
  regionIds: string[],
  windowRegionIds?: string[],
  assetId?: string
): Promise<{ selected_walls: string[]; selected_windows: string[] }> {
  const res = await apiClient.patch<{
    selected_walls: string[];
    selected_windows?: string[];
  }>(`/sessions/${sessionId}/selected-walls`, {
    region_ids: regionIds,
    ...(windowRegionIds !== undefined ? { window_region_ids: windowRegionIds } : {}),
    ...(assetId !== undefined ? { asset_id: assetId } : {})
  });
  return {
    selected_walls: res.data.selected_walls,
    selected_windows: res.data.selected_windows ?? []
  };
}

/**
 * 도면 추론(HF) 엔드포인트 웨이크업 핑 — 세션 진입 1회 + 세션 활성 동안 10분 간격
 * keep-alive(SessionChat). 백엔드가 GET /health 를 보낸다: 잠들어 있으면 스케일업
 * 시작(~26초 뒤 서빙), 웜이면 idle 타이머(15분) 리셋. best-effort — 실패해도
 * 무시하고, 백엔드가 스로틀하므로 자주 불러도 안전하다.
 */
export async function warmupSegmentation(): Promise<void> {
  try {
    await apiClient.post('/sessions/agent/warmup', {});
  } catch {
    // 워밍업은 부가 기능 — 실패를 사용자에게 전파하지 않는다.
  }
}

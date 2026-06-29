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

export interface EstimateItem {
  code: string;
  label: string;
  amount_min: number | null;
  unit_amount: number | null;
  unit: string | null;
  note: string | null;
}

export interface EstimateResult {
  policy_version: string;
  currency: string;
  vat_included: boolean;
  source_url: string;
  items: EstimateItem[];
  fixed_total_min: number | null;
  has_variable_items: boolean;
  disclaimer: string;
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

/** OVERLAY-002: 사용자가 선택한 철거 희망 비내력벽 region_id 목록을 판단스키마에 기록. */
export async function updateSelectedWalls(
  sessionId: string,
  regionIds: string[]
): Promise<string[]> {
  const res = await apiClient.patch<{ selected_walls: string[] }>(
    `/sessions/${sessionId}/selected-walls`,
    { region_ids: regionIds }
  );
  return res.data.selected_walls;
}

/**
 * 세션 진입 시 HF 세그멘테이션 엔드포인트를 미리 깨운다(콜드스타트 체감 제거).
 * best-effort — 실패해도 무시하고, 백엔드가 스로틀하므로 자주 불러도 안전하다.
 */
export async function warmupSegmentation(): Promise<void> {
  try {
    await apiClient.post('/sessions/agent/warmup', {});
  } catch {
    // 워밍업은 부가 기능 — 실패를 사용자에게 전파하지 않는다.
  }
}

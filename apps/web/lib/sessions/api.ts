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

export interface SessionReportResponse {
  schema_version: string;
  session_id: string;
  status: SessionStatus;
  rule_eval_result: Record<string, unknown>;
  evaluated_at: string | null;
  address: Record<string, unknown> | null;
  disclaimer: string;
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

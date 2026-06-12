/**
 * 사전검토(에이전트) 세션 데이터 로더 (CMP-DIRECT).
 * 서버 전용 — 호출자는 requireAdminUser 게이트를 통과해야 한다.
 */

import 'server-only';

import { createServiceRoleClient } from '@/lib/supabase/service-role';

export const SESSIONS_PAGE_SIZE = 20;

export interface SessionAddress {
  road_address: string | null;
  jibun_address: string | null;
  apartment_name: string | null;
  building_dong: string | null;
  unit_ho: string | null;
  floor_no: number | null;
  exclusive_area_m2: number | null;
  size_type: string | null;
}

export interface SessionListRow {
  id: string;
  user_id: string;
  status: string;
  completion_decision: string | null;
  last_activity_at: string;
  created_at: string;
  address: SessionAddress | null;
}

export interface SessionDetail extends SessionListRow {
  judgment_schema: Record<string, unknown>;
  judgment_schema_version: string | null;
  expires_at: string | null;
  updated_at: string;
}

export interface ChatMessageRow {
  id: string;
  role: string;
  content: string;
  content_redacted: boolean;
  created_at: string;
}

export interface SessionUploadRow {
  id: string;
  status: string;
  file_name: string | null;
  created_at: string;
}

/** PostgREST 1:1 embed 가 배열/객체 어느 쪽으로 와도 단일 객체로 정규화. */
function normalizeAddress(value: unknown): SessionAddress | null {
  if (Array.isArray(value)) return (value[0] as SessionAddress) ?? null;
  return (value as SessionAddress) ?? null;
}

export async function listSessions(filter: {
  status?: string;
  page?: number;
}): Promise<{ rows: SessionListRow[]; total: number; page: number; pageSize: number }> {
  const supabase = createServiceRoleClient();
  const page = Math.max(1, filter.page ?? 1);
  const from = (page - 1) * SESSIONS_PAGE_SIZE;

  let query = supabase
    .from('sessions')
    .select(
      // sessions ↔ session_addresses 는 FK 가 양방향 2개(0008)라 embed 가 모호하다 —
      // session_addresses.session_id 경로를 FK 힌트로 명시한다.
      'id, user_id, status, completion_decision, last_activity_at, created_at, session_addresses!session_id(road_address, jibun_address, apartment_name, building_dong, unit_ho, floor_no, exclusive_area_m2, size_type)',
      { count: 'exact' }
    )
    .order('last_activity_at', { ascending: false })
    .range(from, from + SESSIONS_PAGE_SIZE - 1);

  if (filter.status) {
    query = query.eq('status', filter.status);
  }

  const { data, count, error } = await query;
  if (error) {
    throw new Error(`세션 조회 실패: ${error.message}`);
  }

  const rows = (data ?? []).map((row) => {
    const { session_addresses, ...rest } = row as Record<string, unknown>;
    return { ...rest, address: normalizeAddress(session_addresses) } as SessionListRow;
  });
  return { rows, total: count ?? 0, page, pageSize: SESSIONS_PAGE_SIZE };
}

export async function getSession(id: string): Promise<SessionDetail | null> {
  const supabase = createServiceRoleClient();
  const { data, error } = await supabase
    .from('sessions')
    .select('*, session_addresses!session_id(road_address, jibun_address, apartment_name, building_dong, unit_ho, floor_no, exclusive_area_m2, size_type)')
    .eq('id', id)
    .maybeSingle();
  if (error) {
    throw new Error(`세션 조회 실패: ${error.message}`);
  }
  if (!data) return null;
  const { session_addresses, ...rest } = data as Record<string, unknown>;
  return { ...rest, address: normalizeAddress(session_addresses) } as SessionDetail;
}

export async function getSessionMessages(sessionId: string): Promise<ChatMessageRow[]> {
  const supabase = createServiceRoleClient();
  // 최신 300건을 가져와 시간순으로 뒤집는다 — 오래된 세션에서 최근 대화가
  // limit 에 잘려 안 보이는 일이 없도록 (오름차순 + limit 은 앞쪽만 남긴다).
  const { data, error } = await supabase
    .from('chat_messages')
    .select('id, role, content, content_redacted, created_at')
    .eq('session_id', sessionId)
    .order('created_at', { ascending: false })
    .limit(300);
  if (error) return [];
  return ((data ?? []) as ChatMessageRow[]).reverse();
}

export async function getSessionUploads(sessionId: string): Promise<SessionUploadRow[]> {
  const supabase = createServiceRoleClient();
  const { data, error } = await supabase
    .from('floorplan_uploads')
    .select('id, status, file_name, created_at')
    .eq('session_id', sessionId)
    .order('created_at', { ascending: false });
  if (error) return [];
  return (data ?? []) as SessionUploadRow[];
}

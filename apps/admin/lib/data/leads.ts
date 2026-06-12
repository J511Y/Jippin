/**
 * 상담 리드 데이터 로더 (CMP-DIRECT).
 *
 * consultation_leads 는 PII — anon/authenticated grant 가 없는 service_role 전용
 * 테이블이다(0009 봉인). 본 모듈은 서버 전용이며, 호출하는 페이지/액션은 반드시
 * requireAdminUser 게이트를 통과해야 한다.
 *
 * 댓글/담당자(0012)는 마이그레이션 미적용 환경에서 테이블/컬럼이 없을 수 있으므로
 * 실패를 null 로 구분해 UI 가 안내 문구를 보여주게 한다.
 */

import 'server-only';

import { createServiceRoleClient } from '@/lib/supabase/service-role';

export const LEADS_PAGE_SIZE = 20;

export interface LeadListRow {
  id: string;
  applicant_name: string;
  applicant_phone: string;
  applicant_kind: string;
  source_form: string;
  road_addr_part1: string | null;
  status: string;
  inflow_source: string | null;
  assigned_admin_id?: string | null;
  created_at: string;
}

export interface LeadDetail extends LeadListRow {
  user_id: string | null;
  is_anonymous: boolean;
  road_addr_part2: string | null;
  road_addr_detail: string | null;
  expansion_location: string | null;
  ownership_status: string | null;
  construction_start_date: string | null;
  construction_end_date: string | null;
  message: string | null;
  assigned_at?: string | null;
  updated_at: string;
}

export interface LeadAttachment {
  id: string;
  bucket: string;
  object_path: string;
  file_name: string | null;
  content_type: string | null;
  byte_size: number | null;
  signedUrl: string | null;
}

export interface LeadComment {
  id: string;
  author_id: string | null;
  author_email: string;
  body: string;
  created_at: string;
}

export interface AdminOption {
  id: string;
  email: string;
}

export interface LeadListFilter {
  status?: string;
  q?: string;
  page?: number;
}

export async function listLeads(filter: LeadListFilter): Promise<{
  rows: LeadListRow[];
  total: number;
  page: number;
  pageSize: number;
}> {
  const supabase = createServiceRoleClient();
  const page = Math.max(1, filter.page ?? 1);
  const from = (page - 1) * LEADS_PAGE_SIZE;

  let query = supabase
    .from('consultation_leads')
    .select(
      'id, applicant_name, applicant_phone, applicant_kind, source_form, road_addr_part1, status, inflow_source, created_at',
      { count: 'exact' }
    )
    .order('created_at', { ascending: false })
    .range(from, from + LEADS_PAGE_SIZE - 1);

  if (filter.status) {
    query = query.eq('status', filter.status);
  }
  if (filter.q) {
    // PostgREST or() 인자에 들어가는 사용자 입력은 예약문자를 제거해 필터 주입을 막는다.
    const term = filter.q.replaceAll(/[,()"\\]/g, ' ').trim();
    if (term) {
      query = query.or(
        `applicant_name.ilike.*${term}*,applicant_phone.ilike.*${term}*,road_addr_part1.ilike.*${term}*`
      );
    }
  }

  const { data, count, error } = await query;
  if (error) {
    throw new Error(`상담 리드 조회 실패: ${error.message}`);
  }
  return { rows: (data ?? []) as LeadListRow[], total: count ?? 0, page, pageSize: LEADS_PAGE_SIZE };
}

export async function getLead(id: string): Promise<LeadDetail | null> {
  const supabase = createServiceRoleClient();
  const { data, error } = await supabase
    .from('consultation_leads')
    .select('*')
    .eq('id', id)
    .maybeSingle();
  if (error) {
    throw new Error(`상담 리드 조회 실패: ${error.message}`);
  }
  return (data as LeadDetail | null) ?? null;
}

export async function getLeadAttachments(leadId: string): Promise<LeadAttachment[]> {
  const supabase = createServiceRoleClient();
  const { data, error } = await supabase
    .from('consultation_lead_attachments')
    .select('id, bucket, object_path, file_name, content_type, byte_size')
    .eq('lead_id', leadId)
    .order('created_at', { ascending: true });
  if (error || !data) return [];

  return Promise.all(
    data.map(async (row) => {
      const { data: signed } = await supabase.storage
        .from(row.bucket as string)
        .createSignedUrl(row.object_path as string, 60 * 60);
      return { ...(row as Omit<LeadAttachment, 'signedUrl'>), signedUrl: signed?.signedUrl ?? null };
    })
  );
}

/** 0012 미적용 환경이면 null (UI 안내용), 적용 후엔 배열. */
export async function getLeadComments(leadId: string): Promise<LeadComment[] | null> {
  const supabase = createServiceRoleClient();
  const { data, error } = await supabase
    .from('consultation_lead_comments')
    .select('id, author_id, author_email, body, created_at')
    .eq('lead_id', leadId)
    .order('created_at', { ascending: true });
  if (error) return null;
  return (data ?? []) as LeadComment[];
}

/** 담당자 배정 후보 — 0012 RPC 미적용 환경이면 null. */
export async function listAdminOptions(): Promise<AdminOption[] | null> {
  const supabase = createServiceRoleClient();
  const { data, error } = await supabase.rpc('admin_list_admins');
  if (error || !Array.isArray(data)) return null;
  return data as AdminOption[];
}

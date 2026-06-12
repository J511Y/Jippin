/**
 * 회원 목록 데이터 로더 (CMP-DIRECT).
 *
 * 계정 SSOT 는 auth.users — 익명 세션을 제외한 전체 계정이 목록 기준이고,
 * public.users 는 앱 프로필(LEFT JOIN)로만 붙인다 (0012 admin_list_users RPC).
 * status 가 null 이면 프로필 미생성 계정(가입 미완료/관리자)이다.
 * 서버 전용 — 호출자는 requireAdminUser 게이트를 통과해야 한다.
 */

import 'server-only';

import { clampPageSize } from '@/lib/data/leads';
import { createServiceRoleClient } from '@/lib/supabase/service-role';

export const USERS_PAGE_SIZE = 20;

export interface UserListRow {
  id: string;
  email: string | null;
  display_name: string | null;
  status: string | null;
  role: string;
  last_sign_in_at: string | null;
  created_at: string;
}

export async function listUsers(filter: { q?: string; page?: number; size?: number }): Promise<{
  rows: UserListRow[];
  total: number;
  page: number;
  pageSize: number;
}> {
  const supabase = createServiceRoleClient();
  const page = Math.max(1, filter.page ?? 1);
  const pageSize = clampPageSize(filter.size, USERS_PAGE_SIZE);
  const offset = (page - 1) * pageSize;
  const term = filter.q?.trim() || null;

  // 1차: 0012 admin_list_users RPC — auth.users(익명 제외) 기준 + public.users 프로필 조인.
  const { data, error } = await supabase.rpc('admin_list_users', {
    search: term,
    page_limit: pageSize,
    page_offset: offset
  });
  if (!error && Array.isArray(data)) {
    const rows = data as Array<UserListRow & { provider: string | null; total_count: number }>;
    return {
      rows: rows.map(({ total_count: _total, provider: _provider, ...row }) => row),
      total: rows[0] ? Number(rows[0].total_count) : 0,
      page,
      pageSize
    };
  }

  // 폴백 — 0012 미적용 환경. auth.users 는 PostgREST 로 접근 불가하므로 public.users
  // 프로필만으로 근사 표시한다 (email 없음 — 0007 정리, last_login_at 을 최근 로그인으로).
  let query = supabase
    .from('users')
    .select('id, display_name, status, role, last_login_at, created_at', { count: 'exact' })
    .order('created_at', { ascending: false })
    .range(offset, offset + pageSize - 1);

  if (term) {
    const sanitized = term.replaceAll(/[,()"\\]/g, ' ').trim();
    if (sanitized) {
      query = query.ilike('display_name', `*${sanitized}*`);
    }
  }

  const { data: rows, count, error: fallbackError } = await query;
  if (fallbackError) {
    throw new Error(`회원 조회 실패: ${fallbackError.message}`);
  }
  return {
    rows: (rows ?? []).map((row) => {
      const { last_login_at, ...rest } = row as Record<string, unknown> & {
        last_login_at: string | null;
      };
      return { ...rest, email: null, last_sign_in_at: last_login_at } as UserListRow;
    }),
    total: count ?? 0,
    page,
    pageSize
  };
}

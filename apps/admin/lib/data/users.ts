/**
 * 회원 목록 데이터 로더 (CMP-DIRECT).
 *
 * 정본은 public.users — 카카오/이메일 가입을 거친 집핀 정식 회원 테이블(0005)이다.
 * (auth.users 의 익명 세션은 회원이 아니므로 포함하지 않는다.)
 * 서버 전용 — 호출자는 requireAdminUser 게이트를 통과해야 한다.
 */

import 'server-only';

import { createServiceRoleClient } from '@/lib/supabase/service-role';

export const USERS_PAGE_SIZE = 20;

export interface UserListRow {
  id: string;
  email: string | null;
  display_name: string | null;
  status: string;
  role: string;
  last_login_at: string | null;
  created_at: string;
}

export async function listUsers(filter: { q?: string; page?: number }): Promise<{
  rows: UserListRow[];
  total: number;
  page: number;
  pageSize: number;
}> {
  const supabase = createServiceRoleClient();
  const page = Math.max(1, filter.page ?? 1);
  const offset = (page - 1) * USERS_PAGE_SIZE;
  const term = filter.q?.trim() || null;

  // 1차: 0012 admin_list_users RPC — auth.users 조인으로 email 포함 + 이메일 검색.
  const { data, error } = await supabase.rpc('admin_list_users', {
    search: term,
    page_limit: USERS_PAGE_SIZE,
    page_offset: offset
  });
  if (!error && Array.isArray(data)) {
    const rows = data as Array<UserListRow & { total_count: number }>;
    return {
      rows: rows.map(({ total_count: _total, ...row }) => row),
      total: rows[0] ? Number(rows[0].total_count) : 0,
      page,
      pageSize: USERS_PAGE_SIZE
    };
  }

  // 폴백 — 0012 미적용 환경. public.users 에는 email 이 없으므로(0007 정리)
  // display_name 검색만 지원하고 email 은 비워 둔다.
  let query = supabase
    .from('users')
    .select('id, display_name, status, role, last_login_at, created_at', { count: 'exact' })
    .order('created_at', { ascending: false })
    .range(offset, offset + USERS_PAGE_SIZE - 1);

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
    rows: (rows ?? []).map((row) => ({ ...row, email: null }) as UserListRow),
    total: count ?? 0,
    page,
    pageSize: USERS_PAGE_SIZE
  };
}

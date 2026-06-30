/**
 * 대시보드 집계 데이터 로더 (CMP-DIRECT).
 *
 * 1차 경로는 migration 0012 의 admin RPC(service_role 전용). 마이그레이션이 아직
 * 배포 환경에 적용되기 전(머지 전 로컬 등)에는 RPC 가 없으므로, 실패 시 PostgREST
 * head-count / 소량 select 기반 폴백으로 동일한 모양의 데이터를 만든다.
 */

import 'server-only';

import { createServiceRoleClient } from '@/lib/supabase/service-role';

export interface DashboardStats {
  memberTotal: number | null;
  authMemberTotal: number | null;
  authAnonymousTotal: number | null;
  leadTotal: number | null;
  leadNew: number | null;
  leadInProgress: number | null;
  leadLast7d: number | null;
  sessionTotal: number | null;
  sessionActive: number | null;
}

export interface DailyLeadCount {
  day: string; // YYYY-MM-DD (KST)
  count: number;
}

export interface FunnelEntry {
  status: string;
  count: number;
}

/** 사전검토 세션 퍼널 단계 순서 (0008 status check 와 동일, 종료 상태 제외). */
export const SESSION_FUNNEL_ORDER = [
  'draft',
  'address_ready',
  'floorplan_selected',
  'analyzing',
  'awaiting_overlay',
  'collecting_info',
  'ready_for_rule',
  'report_ready',
  'handoff'
] as const;

function kstDateString(value: string | Date): string {
  return new Date(value).toLocaleDateString('sv-SE', { timeZone: 'Asia/Seoul' });
}

async function headCount(table: string): Promise<number | null> {
  const supabase = createServiceRoleClient();
  const { count, error } = await supabase
    .from(table)
    .select('id', { count: 'exact', head: true });
  return error ? null : (count ?? 0);
}

export async function getDashboardStats(): Promise<DashboardStats> {
  const supabase = createServiceRoleClient();
  const { data, error } = await supabase.rpc('admin_dashboard_stats');

  if (!error && data) {
    const d = data as Record<string, number>;
    return {
      memberTotal: d.member_total ?? null,
      authMemberTotal: d.auth_member_total ?? null,
      authAnonymousTotal: d.auth_anonymous_total ?? null,
      leadTotal: d.lead_total ?? null,
      leadNew: d.lead_new ?? null,
      leadInProgress: d.lead_in_progress ?? null,
      leadLast7d: d.lead_last_7d ?? null,
      sessionTotal: d.session_total ?? null,
      sessionActive: d.session_active ?? null
    };
  }

  // 폴백 — RPC 미적용 환경. auth.users 카운트는 PostgREST 로 접근 불가하므로 null.
  const sevenDaysAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
  const [memberTotal, leadTotal, leadNew, leadInProgress, leadLast7d, sessionTotal, sessionActive] =
    await Promise.all([
      headCount('users'),
      headCount('consultation_leads'),
      supabase
        .from('consultation_leads')
        .select('id', { count: 'exact', head: true })
        .eq('status', 'new')
        .then(({ count, error: e }) => (e ? null : (count ?? 0))),
      supabase
        .from('consultation_leads')
        .select('id', { count: 'exact', head: true })
        .in('status', ['contacted', 'in_progress'])
        .then(({ count, error: e }) => (e ? null : (count ?? 0))),
      supabase
        .from('consultation_leads')
        .select('id', { count: 'exact', head: true })
        .gte('created_at', sevenDaysAgo)
        .then(({ count, error: e }) => (e ? null : (count ?? 0))),
      headCount('sessions'),
      supabase
        .from('sessions')
        .select('id', { count: 'exact', head: true })
        .not('status', 'in', '(expired,deleted)')
        .then(({ count, error: e }) => (e ? null : (count ?? 0)))
    ]);

  return {
    memberTotal,
    authMemberTotal: null,
    authAnonymousTotal: null,
    leadTotal,
    leadNew,
    leadInProgress,
    leadLast7d,
    sessionTotal,
    sessionActive
  };
}

export async function getLeadDailyCounts(daysBack = 30): Promise<DailyLeadCount[]> {
  const supabase = createServiceRoleClient();
  const { data, error } = await supabase.rpc('admin_lead_daily_counts', { days_back: daysBack });

  if (!error && Array.isArray(data)) {
    return (data as Array<{ day: string; lead_count: number }>).map((row) => ({
      day: row.day,
      count: Number(row.lead_count)
    }));
  }

  // 폴백: 기간 내 리드 created_at 만 가져와 KST 일자로 버킷.
  const since = new Date(Date.now() - daysBack * 24 * 60 * 60 * 1000).toISOString();
  const { data: rows } = await supabase
    .from('consultation_leads')
    .select('created_at')
    .gte('created_at', since)
    .limit(5000);

  const buckets = new Map<string, number>();
  for (const row of rows ?? []) {
    const day = kstDateString(row.created_at as string);
    buckets.set(day, (buckets.get(day) ?? 0) + 1);
  }

  const out: DailyLeadCount[] = [];
  const today = new Date();
  for (let i = daysBack - 1; i >= 0; i -= 1) {
    const day = kstDateString(new Date(today.getTime() - i * 24 * 60 * 60 * 1000));
    out.push({ day, count: buckets.get(day) ?? 0 });
  }
  return out;
}

/**
 * 퍼널 폴백(RPC 미적용 환경) — `session_status_events`(0020) 이력에서 각 단계를 그 단계의
 * **실제 이벤트**를 가진 세션 수로 센다(단계별 distinct). rank 누적이 아니라 실제 도달
 * 이벤트 기준이라, 건너뛴 단계(주소 없이 도면 먼저, 상담만 한 handoff)를 부풀리지 않는다.
 * deleted 세션은 모수에서 제외. RPC 경로가 정본이며, 이 폴백은 동일 의미를 재현한다.
 */
async function getSessionFunnelFallback(
  supabase: ReturnType<typeof createServiceRoleClient>
): Promise<Map<string, number>> {
  const known = new Set<string>(SESSION_FUNNEL_ORDER);
  const counts = new Map<string, number>();
  const { data: rows, error } = await supabase
    .from('session_status_events')
    .select('session_id, to_status, sessions!inner(status)')
    .neq('sessions.status', 'deleted')
    .limit(50000);
  if (error || !rows) return counts;

  // 단계×세션 중복 제거 후, 단계별 distinct 세션 수.
  const seen = new Set<string>();
  for (const row of rows as Array<{ session_id: string; to_status: string }>) {
    if (!known.has(row.to_status)) continue;
    const key = `${row.to_status}|${row.session_id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    counts.set(row.to_status, (counts.get(row.to_status) ?? 0) + 1);
  }
  return counts;
}

export async function getSessionFunnel(): Promise<FunnelEntry[]> {
  const supabase = createServiceRoleClient();
  const { data, error } = await supabase.rpc('admin_session_funnel');

  let counts = new Map<string, number>();
  if (!error && Array.isArray(data)) {
    counts = new Map(
      (data as Array<{ status: string; session_count: number }>).map((row) => [
        row.status,
        Number(row.session_count)
      ])
    );
  } else {
    counts = await getSessionFunnelFallback(supabase);
  }

  return SESSION_FUNNEL_ORDER.map((status) => ({ status, count: counts.get(status) ?? 0 }));
}

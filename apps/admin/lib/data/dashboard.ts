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
 * 누적 퍼널 폴백(RPC 미적용 환경) — `session_status_events`(0020) 이력에서 세션별 최고
 * 도달 단계를 구해 "이 단계 이상 도달" 누적으로 센다. 단순 group-by(현재 분포)와 달리
 * 단조 감소(좁아짐)가 보장된다. deleted 세션은 모수에서 제외. RPC 경로가 정본이며, 이
 * 폴백은 동일한 누적 의미를 재현한다.
 */
async function getSessionFunnelFallback(
  supabase: ReturnType<typeof createServiceRoleClient>
): Promise<Map<string, number>> {
  const rank = new Map(
    SESSION_FUNNEL_ORDER.map((name, i): [string, number] => [name, i])
  );
  const counts = new Map<string, number>();
  const { data: rows, error } = await supabase
    .from('session_status_events')
    .select('session_id, to_status, sessions!inner(status)')
    .neq('sessions.status', 'deleted')
    .limit(50000);
  if (error || !rows) return counts;

  const handoffRank = rank.get('handoff'); // 8
  // 파이프라인(handoff 제외)의 세션별 최고 도달 rank + handoff 도달 세션 집합.
  const maxRank = new Map<string, number>();
  const handoffSessions = new Set<string>();
  for (const row of rows as Array<{ session_id: string; to_status: string }>) {
    const r = rank.get(row.to_status);
    if (r === undefined) continue;
    if (r === handoffRank) {
      handoffSessions.add(row.session_id);
      continue; // handoff 는 파이프라인 누적에 넣지 않는다.
    }
    const prev = maxRank.get(row.session_id) ?? -1;
    if (r > prev) maxRank.set(row.session_id, r);
  }
  // 파이프라인 단계(0~7): max_rank >= rank(S) 누적. handoff(8): 실제 도달 세션 수.
  for (const [, sessionMax] of maxRank) {
    for (const [stage, stageRank] of rank) {
      if (stageRank === handoffRank) continue;
      if (sessionMax >= stageRank) counts.set(stage, (counts.get(stage) ?? 0) + 1);
    }
  }
  counts.set('handoff', handoffSessions.size);
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

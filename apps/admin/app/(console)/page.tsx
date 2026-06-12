import { LeadTrendChart } from '@/components/dashboard/lead-trend-chart';
import { SessionFunnelChart } from '@/components/dashboard/session-funnel-chart';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  getDashboardStats,
  getLeadDailyCounts,
  getSessionFunnel
} from '@/lib/data/dashboard';

export const dynamic = 'force-dynamic';

function StatCard({
  label,
  value,
  hint
}: {
  label: string;
  value: number | null;
  hint?: string;
}) {
  return (
    <Card className="gap-1 py-4">
      <CardHeader className="px-4">
        <CardDescription className="text-xs">{label}</CardDescription>
      </CardHeader>
      <CardContent className="px-4">
        <p className="text-2xl font-semibold tabular-nums">
          {value === null ? '—' : value.toLocaleString('ko-KR')}
        </p>
        {hint ? <p className="text-muted-foreground mt-0.5 text-xs">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}

export default async function DashboardPage() {
  const [stats, daily, funnel] = await Promise.all([
    getDashboardStats(),
    getLeadDailyCounts(30),
    getSessionFunnel()
  ]);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold">대시보드</h1>
        <p className="text-muted-foreground mt-1 text-sm">집핀 서비스 현황 요약</p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="회원 수"
          value={stats.authMemberTotal ?? stats.memberTotal}
          hint={
            stats.authAnonymousTotal !== null
              ? `익명 세션 ${stats.authAnonymousTotal.toLocaleString('ko-KR')}개 별도`
              : undefined
          }
        />
        <StatCard label="신규 상담" value={stats.leadNew} hint="확인 대기" />
        <StatCard label="진행중 상담" value={stats.leadInProgress} hint="연락 완료 포함" />
        <StatCard
          label="최근 7일 인입"
          value={stats.leadLast7d}
          hint={stats.leadTotal !== null ? `누적 ${stats.leadTotal.toLocaleString('ko-KR')}건` : undefined}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">상담 인입량 추이</CardTitle>
            <CardDescription>최근 30일, 일자별 상담 신청 수 (KST)</CardDescription>
          </CardHeader>
          <CardContent>
            <LeadTrendChart data={daily} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">에이전트 세션 퍼널</CardTitle>
            <CardDescription>
              사전검토 세션 상태별 분포
              {stats.sessionTotal !== null
                ? ` — 총 ${stats.sessionTotal.toLocaleString('ko-KR')}개 (활성 ${
                    stats.sessionActive?.toLocaleString('ko-KR') ?? '—'
                  })`
                : ''}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {funnel.every((entry) => entry.count === 0) ? (
              <div className="text-muted-foreground flex h-64 items-center justify-center text-sm">
                아직 세션 데이터가 없습니다. 에이전트 파이프라인 가동 후 채워집니다.
              </div>
            ) : (
              <SessionFunnelChart data={funnel} />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

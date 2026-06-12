import { ChevronLeft, ChevronRight } from 'lucide-react';
import Link from 'next/link';

import { SessionStatusFilter } from '@/components/sessions/session-status-filter';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from '@/components/ui/table';
import { listSessions } from '@/lib/data/sessions';
import { SESSION_STATUS_LABELS, formatDateTime } from '@/lib/labels';

export const dynamic = 'force-dynamic';

function addressSummary(address: {
  apartment_name: string | null;
  road_address: string | null;
  building_dong: string | null;
  unit_ho: string | null;
} | null): string {
  if (!address) return '—';
  const head = address.apartment_name ?? address.road_address;
  if (!head) return '—';
  const tail = [address.building_dong, address.unit_ho].filter(Boolean).join(' ');
  return tail ? `${head} ${tail}` : head;
}

function buildPageHref(params: { status?: string }, page: number): string {
  const search = new URLSearchParams();
  if (params.status) search.set('status', params.status);
  if (page > 1) search.set('page', String(page));
  const qs = search.toString();
  return qs ? `/sessions?${qs}` : '/sessions';
}

export default async function SessionsPage({
  searchParams
}: {
  searchParams: Promise<{ status?: string; page?: string }>;
}) {
  const params = await searchParams;
  const page = Math.max(1, Number(params.page) || 1);
  const { rows, total, pageSize } = await listSessions({ status: params.status, page });
  const lastPage = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">사전검토 세션</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            에이전트 세션 {total.toLocaleString('ko-KR')}개
          </p>
        </div>
        <SessionStatusFilter status={params.status} />
      </div>

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>세션</TableHead>
              <TableHead>주소</TableHead>
              <TableHead>상태</TableHead>
              <TableHead>완료 판정</TableHead>
              <TableHead className="text-right">최근 활동</TableHead>
              <TableHead className="text-right">생성일</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-muted-foreground h-24 text-center">
                  아직 세션이 없습니다. 에이전트 파이프라인 가동 후 채워집니다.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((session) => (
                <TableRow key={session.id}>
                  <TableCell>
                    <Link
                      href={`/sessions/${session.id}`}
                      className="font-mono text-xs underline-offset-4 hover:underline"
                    >
                      {session.id.slice(0, 8)}
                    </Link>
                  </TableCell>
                  <TableCell className="max-w-64 truncate">
                    {addressSummary(session.address)}
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary" className="font-normal">
                      {SESSION_STATUS_LABELS[session.status] ?? session.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs">
                    {session.completion_decision ?? '—'}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-right text-xs tabular-nums">
                    {formatDateTime(session.last_activity_at)}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-right text-xs tabular-nums">
                    {formatDateTime(session.created_at)}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {lastPage > 1 ? (
        <div className="flex items-center justify-between">
          <p className="text-muted-foreground text-xs">
            {page} / {lastPage} 페이지
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              render={page > 1 ? <Link href={buildPageHref(params, page - 1)} /> : undefined}
            >
              <ChevronLeft className="size-3.5" /> 이전
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= lastPage}
              render={page < lastPage ? <Link href={buildPageHref(params, page + 1)} /> : undefined}
            >
              다음 <ChevronRight className="size-3.5" />
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

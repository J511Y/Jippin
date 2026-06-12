import { ChevronLeft, ChevronRight } from 'lucide-react';
import Link from 'next/link';

import { LeadFilters } from '@/components/leads/lead-filters';
import { LeadStatusSelect } from '@/components/leads/lead-status-select';
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
import { listAdminOptions, listLeads } from '@/lib/data/leads';
import {
  APPLICANT_KIND_LABELS,
  INFLOW_SOURCE_LABELS,
  SOURCE_FORM_LABELS,
  formatDateTime
} from '@/lib/labels';

export const dynamic = 'force-dynamic';

function buildPageHref(params: { status?: string; q?: string }, page: number): string {
  const search = new URLSearchParams();
  if (params.status) search.set('status', params.status);
  if (params.q) search.set('q', params.q);
  if (page > 1) search.set('page', String(page));
  const qs = search.toString();
  return qs ? `/leads?${qs}` : '/leads';
}

export default async function LeadsPage({
  searchParams
}: {
  searchParams: Promise<{ status?: string; q?: string; page?: string }>;
}) {
  const params = await searchParams;
  const page = Math.max(1, Number(params.page) || 1);
  const [{ rows, total, pageSize }, admins] = await Promise.all([
    listLeads({ status: params.status, q: params.q, page }),
    listAdminOptions()
  ]);
  const lastPage = Math.max(1, Math.ceil(total / pageSize));
  const adminNameById = new Map((admins ?? []).map((admin) => [admin.id, admin.name]));

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">상담</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            상담 신청 {total.toLocaleString('ko-KR')}건
          </p>
        </div>
        <LeadFilters status={params.status} q={params.q} />
      </div>

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>신청자</TableHead>
              <TableHead>연락처</TableHead>
              <TableHead>주소</TableHead>
              <TableHead>유입</TableHead>
              <TableHead>경로</TableHead>
              <TableHead>상태</TableHead>
              <TableHead>담당자</TableHead>
              <TableHead className="text-right">신청일</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="text-muted-foreground h-24 text-center">
                  조건에 맞는 상담 신청이 없습니다.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((lead) => (
                <TableRow key={lead.id}>
                  <TableCell>
                    <Link
                      href={`/leads/${lead.id}`}
                      className="font-medium underline-offset-4 hover:underline"
                    >
                      {lead.applicant_name}
                    </Link>
                    <span className="text-muted-foreground ml-1.5 text-xs">
                      {APPLICANT_KIND_LABELS[lead.applicant_kind] ?? lead.applicant_kind}
                    </span>
                  </TableCell>
                  <TableCell className="tabular-nums">{lead.applicant_phone}</TableCell>
                  <TableCell className="max-w-56 truncate" title={lead.road_addr_part1 ?? ''}>
                    {lead.road_addr_part1 ?? '—'}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {lead.inflow_source
                      ? (INFLOW_SOURCE_LABELS[lead.inflow_source] ?? lead.inflow_source)
                      : '—'}
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary" className="font-normal">
                      {SOURCE_FORM_LABELS[lead.source_form] ?? lead.source_form}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <LeadStatusSelect leadId={lead.id} status={lead.status} />
                  </TableCell>
                  <TableCell>
                    {lead.assigned_admin_id ? (
                      (adminNameById.get(lead.assigned_admin_id) ?? (
                        <span className="font-mono text-xs">
                          {lead.assigned_admin_id.slice(0, 8)}
                        </span>
                      ))
                    ) : (
                      <span className="text-muted-foreground">미배정</span>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-right text-xs tabular-nums">
                    {formatDateTime(lead.created_at)}
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

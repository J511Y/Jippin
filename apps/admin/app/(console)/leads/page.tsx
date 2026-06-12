import { ClickableRow } from '@/components/console/clickable-row';
import { TablePagination } from '@/components/console/table-pagination';
import { LeadFilters } from '@/components/leads/lead-filters';
import { Badge } from '@/components/ui/badge';
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
  LEAD_STATUS_DOT_CLASS,
  LEAD_STATUS_LABELS,
  formatDateTime
} from '@/lib/labels';
import { cn } from '@/lib/utils';

export const dynamic = 'force-dynamic';

export default async function LeadsPage({
  searchParams
}: {
  searchParams: Promise<{
    status?: string;
    q?: string;
    assignee?: string;
    page?: string;
    size?: string;
  }>;
}) {
  const params = await searchParams;
  const page = Math.max(1, Number(params.page) || 1);
  const [{ rows, total, pageSize }, admins] = await Promise.all([
    listLeads({
      status: params.status,
      q: params.q,
      assignee: params.assignee,
      page,
      size: Number(params.size)
    }),
    listAdminOptions()
  ]);
  const lastPage = Math.max(1, Math.ceil(total / pageSize));
  const adminNameById = new Map((admins ?? []).map((admin) => [admin.id, admin.name]));

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-xl font-semibold">상담</h1>
        <LeadFilters
          status={params.status}
          q={params.q}
          assignee={params.assignee}
          admins={admins}
        />
      </div>

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>신청자</TableHead>
              <TableHead>연락처</TableHead>
              <TableHead>주소</TableHead>
              <TableHead>담당자</TableHead>
              <TableHead className="text-right">신청일</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-muted-foreground h-24 text-center">
                  조건에 맞는 상담 신청이 없습니다.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((lead) => (
                <ClickableRow key={lead.id} href={`/leads/${lead.id}`}>
                  <TableCell>
                    <span className="flex items-center gap-2">
                      {/* 상태는 dot 으로만 표시 — 변경은 상세 페이지에서 */}
                      <span
                        className={cn(
                          'size-1.5 shrink-0 rounded-full',
                          LEAD_STATUS_DOT_CLASS[lead.status] ?? 'bg-zinc-400'
                        )}
                        title={LEAD_STATUS_LABELS[lead.status] ?? lead.status}
                      />
                      <span className="font-medium">{lead.applicant_name}</span>
                      <span className="text-muted-foreground text-xs">
                        {APPLICANT_KIND_LABELS[lead.applicant_kind] ?? lead.applicant_kind}
                      </span>
                      {lead.is_anonymous ? (
                        <Badge variant="outline" className="text-[11px] font-normal">
                          비회원
                        </Badge>
                      ) : null}
                    </span>
                  </TableCell>
                  <TableCell className="tabular-nums">{lead.applicant_phone}</TableCell>
                  <TableCell className="max-w-64 truncate" title={lead.road_addr_part1 ?? ''}>
                    {lead.road_addr_part1 ?? '—'}
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
                </ClickableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <TablePagination page={page} lastPage={lastPage} total={total} pageSize={pageSize} />
    </div>
  );
}

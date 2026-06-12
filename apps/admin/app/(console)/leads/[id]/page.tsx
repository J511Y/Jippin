import { ArrowLeft, FileImage, MessageSquare, UserRound } from 'lucide-react';
import Link from 'next/link';
import { notFound } from 'next/navigation';

import { AssigneeSelect } from '@/components/leads/assignee-select';
import { CommentForm } from '@/components/leads/comment-form';
import { LeadStatusSelect } from '@/components/leads/lead-status-select';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import {
  getLead,
  getLeadAttachments,
  getLeadComments,
  listAdminOptions
} from '@/lib/data/leads';
import {
  APPLICANT_KIND_LABELS,
  INFLOW_SOURCE_LABELS,
  OWNERSHIP_STATUS_LABELS,
  SOURCE_FORM_LABELS,
  formatDate,
  formatDateTime
} from '@/lib/labels';

export const dynamic = 'force-dynamic';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-muted-foreground text-xs">{label}</p>
      <div className="mt-0.5 text-sm">{children ?? '—'}</div>
    </div>
  );
}

function formatBytes(size: number | null): string {
  if (size === null) return '';
  if (size < 1024 * 1024) return `${Math.round(size / 1024)}KB`;
  return `${(size / (1024 * 1024)).toFixed(1)}MB`;
}

export default async function LeadDetailPage({
  params
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const lead = await getLead(id);
  if (!lead) notFound();

  const [attachments, comments, admins] = await Promise.all([
    getLeadAttachments(id),
    getLeadComments(id),
    listAdminOptions()
  ]);

  const fullAddress = [lead.road_addr_part1, lead.road_addr_part2, lead.road_addr_detail]
    .filter(Boolean)
    .join(' ');

  return (
    <div className="flex flex-col gap-5">
      <div>
        <Link
          href="/leads"
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs"
        >
          <ArrowLeft className="size-3.5" /> 상담 목록
        </Link>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold">{lead.applicant_name}</h1>
            <Badge variant="secondary" className="font-normal">
              {APPLICANT_KIND_LABELS[lead.applicant_kind] ?? lead.applicant_kind}
            </Badge>
            {lead.is_anonymous ? (
              <Badge variant="outline" className="font-normal">
                비회원 신청
              </Badge>
            ) : null}
          </div>
          <LeadStatusSelect leadId={lead.id} status={lead.status} size="default" />
        </div>
        <p className="text-muted-foreground mt-1 text-xs">
          {formatDateTime(lead.created_at)} 신청 · {SOURCE_FORM_LABELS[lead.source_form] ?? lead.source_form}
        </p>
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-3">
        <div className="flex flex-col gap-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">신청 정보</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-x-6 gap-y-4">
              <Field label="연락처">
                <span className="tabular-nums">{lead.applicant_phone}</span>
              </Field>
              <Field label="유입 경로">
                {lead.inflow_source
                  ? (INFLOW_SOURCE_LABELS[lead.inflow_source] ?? lead.inflow_source)
                  : '—'}
              </Field>
              <div className="col-span-2">
                <Field label="주소">{fullAddress || '—'}</Field>
              </div>
              <Field label="확장(발코니) 위치">{lead.expansion_location ?? '—'}</Field>
              <Field label="소유 상태">
                {lead.ownership_status
                  ? (OWNERSHIP_STATUS_LABELS[lead.ownership_status] ?? lead.ownership_status)
                  : '—'}
              </Field>
              <Field label="공사 시작 희망일">{formatDate(lead.construction_start_date)}</Field>
              <Field label="공사 종료 희망일">{formatDate(lead.construction_end_date)}</Field>
              {lead.message ? (
                <div className="col-span-2">
                  <Field label="문의 내용">
                    <p className="whitespace-pre-wrap">{lead.message}</p>
                  </Field>
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <FileImage className="size-4" /> 첨부 도면 ({attachments.length})
              </CardTitle>
            </CardHeader>
            <CardContent>
              {attachments.length === 0 ? (
                <p className="text-muted-foreground text-sm">첨부된 도면이 없습니다.</p>
              ) : (
                <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {attachments.map((file) => (
                    <li key={file.id} className="overflow-hidden rounded-md border">
                      {file.signedUrl && file.content_type?.startsWith('image/') ? (
                        <a href={file.signedUrl} target="_blank" rel="noreferrer">
                          {/* signed URL 은 1시간 만료 — 정적 최적화 대상이 아니므로 img 사용 */}
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={file.signedUrl}
                            alt={file.file_name ?? '첨부 도면'}
                            className="aspect-square w-full object-cover transition-transform hover:scale-105"
                          />
                        </a>
                      ) : (
                        <div className="bg-muted flex aspect-square items-center justify-center">
                          <FileImage className="text-muted-foreground size-8" />
                        </div>
                      )}
                      <div className="flex items-center justify-between gap-2 border-t px-2 py-1.5">
                        <p className="truncate text-xs" title={file.file_name ?? ''}>
                          {file.file_name ?? file.object_path.split('/').pop()}
                        </p>
                        <span className="text-muted-foreground shrink-0 text-[11px]">
                          {formatBytes(file.byte_size)}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <MessageSquare className="size-4" /> 댓글 {comments ? `(${comments.length})` : ''}
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              {comments === null ? (
                <p className="text-muted-foreground text-sm">
                  댓글 테이블이 아직 준비되지 않았습니다 — migration 0012 가 이 환경에 적용된 뒤
                  사용할 수 있습니다.
                </p>
              ) : (
                <>
                  {comments.length > 0 ? (
                    <ul className="flex flex-col gap-3">
                      {comments.map((comment) => (
                        <li key={comment.id} className="rounded-md border px-3 py-2.5">
                          <div className="flex items-center justify-between gap-2">
                            <p className="text-xs font-medium">{comment.author_email}</p>
                            <p className="text-muted-foreground text-[11px] tabular-nums">
                              {formatDateTime(comment.created_at)}
                            </p>
                          </div>
                          <p className="mt-1.5 text-sm whitespace-pre-wrap">{comment.body}</p>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-muted-foreground text-sm">아직 댓글이 없습니다.</p>
                  )}
                  <Separator />
                  <CommentForm leadId={lead.id} />
                </>
              )}
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <UserRound className="size-4" /> 담당
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {admins === null ? (
              <p className="text-muted-foreground text-sm">
                담당자 목록 RPC 가 아직 준비되지 않았습니다 — migration 0012 적용 후 사용할 수
                있습니다.
              </p>
            ) : (
              <Field label="담당자">
                <AssigneeSelect
                  leadId={lead.id}
                  assignedAdminId={lead.assigned_admin_id ?? null}
                  admins={admins}
                />
              </Field>
            )}
            {lead.assigned_at ? (
              <Field label="배정 일시">{formatDateTime(lead.assigned_at)}</Field>
            ) : null}
            <Separator />
            <Field label="마지막 변경">{formatDateTime(lead.updated_at)}</Field>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

import { FileImage } from 'lucide-react';
import Link from 'next/link';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  listLeadAttachmentCards,
  listSessionUploadCards
} from '@/lib/data/floorplans';
import { UPLOAD_STATUS_LABELS, formatDateTime } from '@/lib/labels';

export const dynamic = 'force-dynamic';

function formatBytes(size: number | null): string {
  if (size === null) return '';
  if (size < 1024 * 1024) return `${Math.round(size / 1024)}KB`;
  return `${(size / (1024 * 1024)).toFixed(1)}MB`;
}

export default async function FloorplansPage() {
  const [leadAttachments, sessionUploads] = await Promise.all([
    listLeadAttachmentCards(),
    listSessionUploadCards()
  ]);

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-xl font-semibold">업로드 도면</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          상담 신청 첨부와 사전검토 세션 업로드를 모아봅니다
        </p>
      </div>

      <Tabs defaultValue="leads">
        <TabsList>
          <TabsTrigger value="leads">상담 첨부 ({leadAttachments.length})</TabsTrigger>
          <TabsTrigger value="sessions">세션 업로드 ({sessionUploads.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="leads" className="mt-4">
          {leadAttachments.length === 0 ? (
            <Card>
              <CardContent className="text-muted-foreground py-12 text-center text-sm">
                상담 신청에 첨부된 도면이 없습니다.
              </CardContent>
            </Card>
          ) : (
            <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
              {leadAttachments.map((file) => (
                <li key={file.id} className="overflow-hidden rounded-lg border">
                  {file.signedUrl && file.content_type?.startsWith('image/') ? (
                    <a href={file.signedUrl} target="_blank" rel="noreferrer">
                      {/* signed URL 1시간 만료 — next/image 최적화 대상 아님 */}
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={file.signedUrl}
                        alt={file.file_name ?? '업로드 도면'}
                        className="bg-muted aspect-square w-full object-cover transition-transform hover:scale-105"
                        loading="lazy"
                      />
                    </a>
                  ) : (
                    <div className="bg-muted flex aspect-square items-center justify-center">
                      <FileImage className="text-muted-foreground size-8" />
                    </div>
                  )}
                  <div className="border-t px-3 py-2">
                    <p className="truncate text-xs font-medium" title={file.file_name ?? ''}>
                      {file.file_name ?? '이름 없음'}
                    </p>
                    <div className="text-muted-foreground mt-1 flex items-center justify-between gap-2 text-[11px]">
                      <Link href={`/leads/${file.lead_id}`} className="truncate hover:underline">
                        {file.applicant_name ?? '상담 보기'}
                      </Link>
                      <span className="shrink-0">
                        {formatBytes(file.byte_size)}
                      </span>
                    </div>
                    <p className="text-muted-foreground mt-0.5 text-[11px] tabular-nums">
                      {formatDateTime(file.created_at)}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </TabsContent>

        <TabsContent value="sessions" className="mt-4">
          {sessionUploads.length === 0 ? (
            <Card>
              <CardContent className="text-muted-foreground py-12 text-center text-sm">
                세션에서 업로드된 도면이 없습니다. 에이전트 파이프라인 가동 후 채워집니다.
              </CardContent>
            </Card>
          ) : (
            <ul className="flex flex-col gap-2">
              {sessionUploads.map((upload) => (
                <li
                  key={upload.id}
                  className="flex items-center justify-between rounded-md border px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm">{upload.file_name ?? upload.id}</p>
                    <Link
                      href={`/sessions/${upload.session_id}`}
                      className="text-muted-foreground font-mono text-[11px] hover:underline"
                    >
                      세션 {upload.session_id.slice(0, 8)}
                    </Link>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <Badge variant="secondary" className="font-normal">
                      {UPLOAD_STATUS_LABELS[upload.status] ?? upload.status}
                    </Badge>
                    <span className="text-muted-foreground text-xs tabular-nums">
                      {formatDateTime(upload.created_at)}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

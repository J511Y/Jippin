import { ArrowLeft, Bot, FileImage, MapPin, MessageCircle } from 'lucide-react';
import Link from 'next/link';
import { notFound } from 'next/navigation';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  getSession,
  getSessionMessages,
  getSessionUploads
} from '@/lib/data/sessions';
import { SESSION_STATUS_LABELS, UPLOAD_STATUS_LABELS, formatDateTime } from '@/lib/labels';
import { cn } from '@/lib/utils';

export const dynamic = 'force-dynamic';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-muted-foreground text-xs">{label}</p>
      <div className="mt-0.5 text-sm">{children ?? '—'}</div>
    </div>
  );
}

const ROLE_LABELS: Record<string, string> = {
  user: '사용자',
  assistant: '에이전트',
  system: '시스템',
  tool: '도구'
};

export default async function SessionDetailPage({
  params
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const session = await getSession(id);
  if (!session) notFound();

  const [messages, uploads] = await Promise.all([
    getSessionMessages(id),
    getSessionUploads(id)
  ]);

  const address = session.address;

  return (
    <div className="flex flex-col gap-5">
      <div>
        <Link
          href="/sessions"
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs"
        >
          <ArrowLeft className="size-3.5" /> 세션 목록
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="font-mono text-lg font-semibold">{session.id.slice(0, 8)}</h1>
          <Badge variant="secondary" className="font-normal">
            {SESSION_STATUS_LABELS[session.status] ?? session.status}
          </Badge>
          {session.completion_decision ? (
            <Badge variant="outline" className="font-mono text-[11px] font-normal">
              {session.completion_decision}
            </Badge>
          ) : null}
        </div>
        <p className="text-muted-foreground mt-1 text-xs">
          {formatDateTime(session.created_at)} 생성 · 최근 활동 {formatDateTime(session.last_activity_at)}
        </p>
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-3">
        <div className="flex flex-col gap-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <MessageCircle className="size-4" /> 대화 내용 ({messages.length})
              </CardTitle>
            </CardHeader>
            <CardContent>
              {messages.length === 0 ? (
                <p className="text-muted-foreground text-sm">대화 기록이 없습니다.</p>
              ) : (
                <ul className="flex max-h-[32rem] flex-col gap-3 overflow-y-auto pr-1">
                  {messages.map((message) => (
                    <li
                      key={message.id}
                      className={cn(
                        'max-w-[85%] rounded-lg border px-3 py-2',
                        message.role === 'user' ? 'self-end' : 'self-start',
                        message.role === 'assistant' && 'bg-secondary/50',
                        (message.role === 'system' || message.role === 'tool') &&
                          'border-dashed opacity-80'
                      )}
                    >
                      <div className="flex items-center gap-2">
                        {message.role === 'assistant' ? <Bot className="size-3" /> : null}
                        <p className="text-muted-foreground text-[11px]">
                          {ROLE_LABELS[message.role] ?? message.role} ·{' '}
                          {formatDateTime(message.created_at)}
                          {message.content_redacted ? ' · 마스킹됨' : ''}
                        </p>
                      </div>
                      <p className="mt-1 text-sm whitespace-pre-wrap">{message.content}</p>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <FileImage className="size-4" /> 세션 업로드 도면 ({uploads.length})
              </CardTitle>
            </CardHeader>
            <CardContent>
              {uploads.length === 0 ? (
                <p className="text-muted-foreground text-sm">업로드된 도면이 없습니다.</p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {uploads.map((upload) => (
                    <li
                      key={upload.id}
                      className="flex items-center justify-between rounded-md border px-3 py-2"
                    >
                      <p className="truncate text-sm">{upload.file_name ?? upload.id}</p>
                      <div className="flex items-center gap-3">
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
            </CardContent>
          </Card>
        </div>

        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <MapPin className="size-4" /> 대상 주소
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {address ? (
                <>
                  <Field label="단지/도로명">
                    {address.apartment_name ?? address.road_address ?? '—'}
                  </Field>
                  <Field label="동/호">
                    {[address.building_dong, address.unit_ho].filter(Boolean).join(' / ') || '—'}
                  </Field>
                  <Field label="층">{address.floor_no ?? '—'}</Field>
                  <Field label="전용면적">
                    {address.exclusive_area_m2 ? `${address.exclusive_area_m2}㎡` : '—'}
                  </Field>
                  <Field label="평형 타입">{address.size_type ?? '—'}</Field>
                </>
              ) : (
                <p className="text-muted-foreground text-sm">주소 입력 전입니다.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">세션 메타</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <Field label="세션 ID">
                <span className="font-mono text-xs break-all">{session.id}</span>
              </Field>
              <Field label="사용자 ID">
                <span className="font-mono text-xs break-all">{session.user_id}</span>
              </Field>
              <Field label="판정 스키마 버전">{session.judgment_schema_version ?? '—'}</Field>
              <Field label="만료 예정">{formatDateTime(session.expires_at)}</Field>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

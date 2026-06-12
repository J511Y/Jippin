'use client';

import { SearchIcon, XIcon } from 'lucide-react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';
import type { AdminOption } from '@/lib/data/leads';
import { LEAD_STATUSES, LEAD_STATUS_DOT_CLASS, LEAD_STATUS_LABELS } from '@/lib/labels';
import { cn } from '@/lib/utils';

const ALL = 'all';
const UNASSIGNED = 'none';

function StatusOption({ status }: { status?: string }) {
  if (!status) return <>모든 상태</>;
  return (
    <span className="flex items-center gap-2">
      <span className={cn('size-1.5 rounded-full', LEAD_STATUS_DOT_CLASS[status])} />
      {LEAD_STATUS_LABELS[status] ?? status}
    </span>
  );
}

/**
 * 상담 리스트 필터 바 — 상태(dot)·담당자·검색어를 URL searchParams 로 유지 (CMP-DIRECT).
 * 담당자 필터는 0012 적용 환경에서만 노출된다(admins null 이면 숨김).
 */
export function LeadFilters({
  status,
  q,
  assignee,
  admins
}: {
  status?: string;
  q?: string;
  assignee?: string;
  admins: AdminOption[] | null;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [term, setTerm] = useState(q ?? '');

  function apply(patch: Record<string, string | undefined>) {
    const params = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(patch)) {
      if (value) params.set(key, value);
      else params.delete(key);
    }
    params.delete('page'); // 필터 변경 시 1페이지로
    router.replace(params.size ? `${pathname}?${params.toString()}` : pathname);
  }

  function onSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    apply({ q: term.trim() || undefined });
  }

  const assigneeLabel =
    assignee === UNASSIGNED
      ? '미배정'
      : (admins?.find((admin) => admin.id === assignee)?.name ?? '모든 담당자');

  return (
    <div className="flex flex-wrap items-center gap-2">
      <form onSubmit={onSearch} className="relative">
        <SearchIcon className="text-muted-foreground absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
        <Input
          value={term}
          onChange={(event) => setTerm(event.target.value)}
          placeholder="이름·전화번호·주소 검색"
          className="h-8 w-72 pl-8"
        />
      </form>
      <Select
        value={status ?? ALL}
        onValueChange={(next) => apply({ status: next === ALL ? undefined : (next ?? undefined) })}
      >
        <SelectTrigger size="sm" className="w-32">
          <SelectValue>
            <StatusOption status={status} />
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>모든 상태</SelectItem>
          {LEAD_STATUSES.map((entry) => (
            <SelectItem key={entry} value={entry}>
              <StatusOption status={entry} />
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {admins ? (
        <Select
          value={assignee ?? ALL}
          onValueChange={(next) =>
            apply({ assignee: next === ALL ? undefined : (next ?? undefined) })
          }
        >
          <SelectTrigger size="sm" className="w-36">
            <SelectValue>{assigneeLabel}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>모든 담당자</SelectItem>
            <SelectItem value={UNASSIGNED}>미배정</SelectItem>
            {admins.map((admin) => (
              <SelectItem key={admin.id} value={admin.id}>
                {admin.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : null}
      {status || q || assignee ? (
        <Button
          variant="ghost"
          size="sm"
          className="text-muted-foreground"
          onClick={() => {
            setTerm('');
            apply({ q: undefined, status: undefined, assignee: undefined });
          }}
        >
          <XIcon data-icon="inline-start" />
          초기화
        </Button>
      ) : null}
    </div>
  );
}

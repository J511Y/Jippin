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
import { LEAD_STATUSES, LEAD_STATUS_LABELS } from '@/lib/labels';

const ALL = 'all';

/** 상담 리스트 필터 바 — 상태 + 검색어를 URL searchParams 로 유지 (CMP-DIRECT). */
export function LeadFilters({ status, q }: { status?: string; q?: string }) {
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
            {status ? (LEAD_STATUS_LABELS[status] ?? status) : '모든 상태'}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>모든 상태</SelectItem>
          {LEAD_STATUSES.map((entry) => (
            <SelectItem key={entry} value={entry}>
              {LEAD_STATUS_LABELS[entry]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {status || q ? (
        <Button
          variant="ghost"
          size="sm"
          className="text-muted-foreground"
          onClick={() => {
            setTerm('');
            apply({ q: undefined, status: undefined });
          }}
        >
          <XIcon className="size-3.5" />
          초기화
        </Button>
      ) : null}
    </div>
  );
}

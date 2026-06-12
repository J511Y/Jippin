'use client';

import { usePathname, useRouter, useSearchParams } from 'next/navigation';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';
import { SESSION_STATUS_LABELS } from '@/lib/labels';

const ALL = 'all';

/** 세션 상태 필터 (CMP-DIRECT). */
export function SessionStatusFilter({ status }: { status?: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  function onChange(next: string | null) {
    const params = new URLSearchParams(searchParams.toString());
    if (!next || next === ALL) params.delete('status');
    else params.set('status', next);
    params.delete('page');
    router.replace(params.size ? `${pathname}?${params.toString()}` : pathname);
  }

  return (
    <Select value={status ?? ALL} onValueChange={onChange}>
      <SelectTrigger size="sm" className="w-40">
        <SelectValue>
          {status ? (SESSION_STATUS_LABELS[status] ?? status) : '모든 상태'}
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>모든 상태</SelectItem>
        {Object.entries(SESSION_STATUS_LABELS).map(([value, label]) => (
          <SelectItem key={value} value={value}>
            {label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

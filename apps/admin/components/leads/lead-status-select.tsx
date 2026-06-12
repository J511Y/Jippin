'use client';

import { useRouter } from 'next/navigation';
import { useState, useTransition } from 'react';
import { toast } from 'sonner';

import { updateLeadStatus } from '@/app/(console)/leads/actions';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';
import { cn } from '@/lib/utils';
import { LEAD_STATUSES, LEAD_STATUS_DOT_CLASS, LEAD_STATUS_LABELS } from '@/lib/labels';

/** 상담 상태 인라인 변경 셀렉트 — 리스트/상세 공용 (CMP-DIRECT). */
export function LeadStatusSelect({
  leadId,
  status,
  size = 'sm'
}: {
  leadId: string;
  status: string;
  size?: 'sm' | 'default';
}) {
  const router = useRouter();
  const [value, setValue] = useState(status);
  const [pending, startTransition] = useTransition();

  function onChange(next: string | null) {
    if (!next || next === value) return;
    const prev = value;
    setValue(next);
    startTransition(async () => {
      const result = await updateLeadStatus(leadId, next);
      if (!result.ok) {
        setValue(prev);
        toast.error(result.error ?? '상태 변경에 실패했습니다.');
        return;
      }
      toast.success(`상태를 '${LEAD_STATUS_LABELS[next] ?? next}'(으)로 변경했습니다.`);
      router.refresh();
    });
  }

  return (
    <Select value={value} onValueChange={onChange} disabled={pending}>
      <SelectTrigger
        size={size === 'sm' ? 'sm' : 'default'}
        className="w-32"
        onClick={(event) => event.stopPropagation()}
      >
        <SelectValue>
          <span className="flex items-center gap-2">
            <span className={cn('size-1.5 rounded-full', LEAD_STATUS_DOT_CLASS[value])} />
            {LEAD_STATUS_LABELS[value] ?? value}
          </span>
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        {LEAD_STATUSES.map((entry) => (
          <SelectItem key={entry} value={entry}>
            <span className="flex items-center gap-2">
              <span className={cn('size-1.5 rounded-full', LEAD_STATUS_DOT_CLASS[entry])} />
              {LEAD_STATUS_LABELS[entry]}
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

'use client';

import { useRouter } from 'next/navigation';
import { useState, useTransition } from 'react';
import { toast } from 'sonner';

import { assignLead } from '@/app/(console)/leads/actions';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';
import type { AdminOption } from '@/lib/data/leads';

const UNASSIGNED = 'unassigned';

/** 상담 담당자 배정 셀렉트 (CMP-DIRECT). */
export function AssigneeSelect({
  leadId,
  assignedAdminId,
  admins
}: {
  leadId: string;
  assignedAdminId: string | null;
  admins: AdminOption[];
}) {
  const router = useRouter();
  const [value, setValue] = useState(assignedAdminId ?? UNASSIGNED);
  const [pending, startTransition] = useTransition();

  const currentLabel =
    value === UNASSIGNED
      ? '미배정'
      : (admins.find((admin) => admin.id === value)?.email ?? value);

  function onChange(next: string | null) {
    if (!next || next === value) return;
    const prev = value;
    setValue(next);
    startTransition(async () => {
      const result = await assignLead(leadId, next === UNASSIGNED ? null : next);
      if (!result.ok) {
        setValue(prev);
        toast.error(result.error ?? '담당자 배정에 실패했습니다.');
        return;
      }
      toast.success(
        next === UNASSIGNED
          ? '담당자 배정을 해제했습니다.'
          : `담당자를 배정했습니다: ${admins.find((admin) => admin.id === next)?.email ?? ''}`
      );
      router.refresh();
    });
  }

  return (
    <Select value={value} onValueChange={onChange} disabled={pending}>
      <SelectTrigger size="sm" className="w-56">
        <SelectValue>{currentLabel}</SelectValue>
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={UNASSIGNED}>미배정</SelectItem>
        {admins.map((admin) => (
          <SelectItem key={admin.id} value={admin.id}>
            {admin.email}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

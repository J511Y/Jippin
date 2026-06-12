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

/**
 * 상담 담당자 배정 셀렉트 (CMP-DIRECT).
 * 배정 시 고객에게 SOLAPI 담당자 배정 알림톡이 발송된다(백엔드 위임) — 발송 결과를
 * 토스트로 구분해 알린다. 배정 저장과 발송은 분리돼 있어 발송 실패가 배정을 되돌리지 않는다.
 */
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
      : (admins.find((admin) => admin.id === value)?.name ?? value);

  function onChange(next: string | null) {
    if (!next || next === value) return;
    const prev = value;
    setValue(next);
    startTransition(async () => {
      const assignee = next === UNASSIGNED ? null : admins.find((admin) => admin.id === next);
      // 담당자명·자격 검증은 서버 액션이 admin_list_admins 로 다시 수행한다.
      const result = await assignLead(leadId, next === UNASSIGNED ? null : next);
      if (!result.ok) {
        setValue(prev);
        toast.error(result.error ?? '담당자 배정에 실패했습니다.');
        return;
      }
      if (next === UNASSIGNED) {
        toast.success('담당자 배정을 해제했습니다.');
      } else if (result.notified) {
        toast.success(`${assignee?.name ?? ''} 배정 완료 — 고객에게 알림톡을 발송했습니다.`);
      } else {
        toast.warning(
          `배정은 저장됐지만 알림톡 발송에 실패했습니다${
            result.notifyError ? `: ${result.notifyError}` : '.'
          }`
        );
      }
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
            <span className="flex flex-col">
              <span>{admin.name}</span>
              <span className="text-muted-foreground text-[11px]">{admin.email}</span>
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

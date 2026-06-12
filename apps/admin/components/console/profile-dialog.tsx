'use client';

import { useRouter } from 'next/navigation';
import { useState, useTransition, type FormEvent } from 'react';
import { toast } from 'sonner';

import { updateProfile } from '@/app/(console)/profile-actions';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

/**
 * 사이드바 하단 프로필 버튼 + 수정 모달 (CMP-DIRECT).
 *
 * 이름은 담당자 배정 표시명·알림톡 #{담당자명} 으로도 쓰이므로(0012
 * admin_list_admins) 실명 입력을 안내한다.
 */
export function ProfileDialog({
  name,
  email,
  company,
  phone
}: {
  name: string;
  email: string;
  company: string;
  phone: string;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [pending, startTransition] = useTransition();

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    startTransition(async () => {
      const result = await updateProfile({
        name: String(form.get('name') ?? ''),
        company: String(form.get('company') ?? ''),
        phone: String(form.get('phone') ?? '')
      });
      if (!result.ok) {
        toast.error(result.error ?? '프로필 저장에 실패했습니다.');
        return;
      }
      toast.success('프로필을 저장했습니다.');
      setOpen(false);
      router.refresh();
    });
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        className="hover:bg-secondary/60 flex min-w-0 flex-1 items-center gap-2 rounded-md px-1.5 py-1 text-left transition-colors"
        title="프로필 수정"
      >
        <span className="bg-secondary text-foreground flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold">
          {name.slice(0, 1).toUpperCase()}
        </span>
        <span className="min-w-0">
          <span className="block truncate text-xs font-medium">{name}</span>
          <span className="text-muted-foreground block truncate text-[11px]">
            {company || email}
          </span>
        </span>
      </DialogTrigger>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>프로필 수정</DialogTitle>
          <DialogDescription>
            이름은 상담 담당자 표시와 고객 알림톡의 담당자명으로 사용됩니다.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="profile-email">이메일</Label>
            <Input id="profile-email" value={email} disabled />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="profile-name">이름</Label>
            <Input
              id="profile-name"
              name="name"
              defaultValue={name}
              maxLength={40}
              required
              placeholder="홍길동"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="profile-company">회사명</Label>
            <Input
              id="profile-company"
              name="company"
              defaultValue={company}
              maxLength={60}
              placeholder="(주)신너테크"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="profile-phone">연락처</Label>
            <Input
              id="profile-phone"
              name="phone"
              type="tel"
              defaultValue={phone}
              maxLength={20}
              placeholder="010-0000-0000"
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={pending}>
              {pending ? '저장 중…' : '저장'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

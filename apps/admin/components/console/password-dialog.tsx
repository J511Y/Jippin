'use client';

import { useState, useTransition, type FormEvent } from 'react';
import { toast } from 'sonner';

import { updatePassword } from '@/app/(console)/profile-actions';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

/**
 * 비밀번호 변경 모달 (CMP-DIRECT).
 *
 * 프로필 모달과 겹치지 않도록 controlled 형제 모달로 둔다 — 열림/닫힘은
 * `ProfileDialog` 가 소유하고, 닫히면 프로필 모달이 다시 열린다.
 *
 * Supabase 프로젝트는 비밀번호 변경 시 현재 비밀번호 확인을 요구한다
 * (GoTrue `UpdatePasswordRequireCurrentPassword`) — 현재 비밀번호 입력 필수.
 */
export function PasswordDialog({
  open,
  onOpenChange
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const form = new FormData(event.currentTarget);
    const currentPassword = String(form.get('current') ?? '');
    const newPassword = String(form.get('password') ?? '');
    const confirm = String(form.get('confirm') ?? '');
    if (newPassword !== confirm) {
      setError('비밀번호 확인이 일치하지 않습니다.');
      return;
    }
    startTransition(async () => {
      const result = await updatePassword({ currentPassword, newPassword });
      if (!result.ok) {
        setError(result.error ?? '비밀번호 변경에 실패했습니다.');
        return;
      }
      toast.success('비밀번호를 변경했습니다.');
      onOpenChange(false);
    });
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) setError(null);
      }}
    >
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>비밀번호 변경</DialogTitle>
          <DialogDescription>
            현재 비밀번호 확인 후 8자 이상의 새 비밀번호로 변경합니다.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="current-password">현재 비밀번호</Label>
            <Input
              id="current-password"
              name="current"
              type="password"
              autoComplete="current-password"
              maxLength={72}
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="new-password">새 비밀번호</Label>
            <Input
              id="new-password"
              name="password"
              type="password"
              autoComplete="new-password"
              minLength={8}
              maxLength={72}
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="confirm-password">새 비밀번호 확인</Label>
            <Input
              id="confirm-password"
              name="confirm"
              type="password"
              autoComplete="new-password"
              minLength={8}
              maxLength={72}
              required
            />
          </div>
          {error ? <p className="text-destructive text-sm">{error}</p> : null}
          <DialogFooter>
            <Button type="submit" disabled={pending}>
              {pending ? '변경 중…' : '변경'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

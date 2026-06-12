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
  DialogTitle,
  DialogTrigger
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

/** 비밀번호 변경 모달 — 프로필 모달 푸터에서 중첩 Dialog 로 연다 (CMP-DIRECT). */
export function PasswordDialog() {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const form = new FormData(event.currentTarget);
    const password = String(form.get('password') ?? '');
    const confirm = String(form.get('confirm') ?? '');
    if (password !== confirm) {
      setError('비밀번호 확인이 일치하지 않습니다.');
      return;
    }
    startTransition(async () => {
      const result = await updatePassword(password);
      if (!result.ok) {
        setError(result.error ?? '비밀번호 변경에 실패했습니다.');
        return;
      }
      toast.success('비밀번호를 변경했습니다.');
      setOpen(false);
    });
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setError(null);
      }}
    >
      <DialogTrigger
        render={
          <Button type="button" variant="outline">
            비밀번호 변경
          </Button>
        }
      />
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>비밀번호 변경</DialogTitle>
          <DialogDescription>8자 이상의 새 비밀번호를 입력해 주세요.</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
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

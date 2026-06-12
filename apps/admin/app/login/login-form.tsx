'use client';

import Image from 'next/image';
import { useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

/**
 * 관리자 로그인 폼 (CMP-DIRECT).
 *
 * 비밀번호는 서버측 Route Handler(`/auth/login`)로만 전송하고 클라이언트
 * 스토리지에 남기지 않는다 (apps/web password-login 과 동일 원칙).
 */
export function LoginForm({ next }: { next?: string }) {
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);

    const form = new FormData(event.currentTarget);
    try {
      const res = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: form.get('email'),
          password: form.get('password'),
          next
        })
      });
      const body = (await res.json()) as { redirect?: string; error?: string };
      if (!res.ok || !body.redirect) {
        setError(body.error ?? '로그인에 실패했습니다. 잠시 후 다시 시도해 주세요.');
        return;
      }
      window.location.assign(body.redirect);
    } catch {
      setError('로그인에 실패했습니다. 잠시 후 다시 시도해 주세요.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="w-90">
      <CardHeader>
        <Image
          src="/logo.png"
          alt="집핀"
          width={32}
          height={32}
          className="mb-2"
          priority
          unoptimized
        />
        <CardTitle>집핀 관리자</CardTitle>
        <CardDescription>관리자 계정으로 로그인하세요</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email">이메일</Label>
            <Input id="email" name="email" type="email" autoComplete="username" required />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="password">비밀번호</Label>
            <Input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
            />
          </div>
          {error ? <p className="text-destructive text-sm">{error}</p> : null}
          <Button type="submit" disabled={submitting} className="mt-1 w-full">
            {submitting ? '로그인 중…' : '로그인'}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

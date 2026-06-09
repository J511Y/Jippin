'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { Alert, Button, PasswordInput, Stack, TextInput } from '@mantine/core';
import { useState } from 'react';
import { useForm } from 'react-hook-form';

import { loginSchema, type LoginValues } from '@/lib/auth/validation';

/**
 * 이메일/비밀번호 로그인 폼 (CMP-DIRECT).
 *
 * react-hook-form + zod(`mode: onTouched`)로 focus-out 시점 검증을 표준화한다. 같은 origin
 * Route Handler `/auth/password-login` 에 자격증명을 POST 하며, 비밀번호는 서버측에서만 다룬다.
 */

export function EmailLoginForm({ nextPath }: { nextPath: string }) {
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting }
  } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    mode: 'onTouched',
    defaultValues: { email: '', password: '' }
  });

  async function onSubmit(values: LoginValues) {
    setServerError(null);
    try {
      const res = await fetch('/auth/password-login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: values.email.trim(), password: values.password, next: nextPath })
      });
      const data = (await res.json().catch(() => null)) as
        | { redirect?: string; error?: string }
        | null;
      if (!res.ok) {
        setServerError(data?.error ?? '로그인에 실패했습니다.');
        return;
      }
      window.location.assign(data?.redirect ?? nextPath);
    } catch {
      setServerError('로그인 처리 중 오류가 발생했습니다.');
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate>
      <Stack gap="sm">
        <TextInput
          label="이메일"
          placeholder="you@example.com"
          inputMode="email"
          autoComplete="email"
          error={errors.email?.message}
          {...register('email')}
        />
        <PasswordInput
          label="비밀번호"
          placeholder="비밀번호"
          autoComplete="current-password"
          error={errors.password?.message}
          {...register('password')}
        />
        {serverError ? (
          <Alert color="red" variant="light" py="xs">
            {serverError}
          </Alert>
        ) : null}
        <Button type="submit" color="jippin" size="md" radius="md" loading={isSubmitting} fullWidth>
          로그인
        </Button>
      </Stack>
    </form>
  );
}

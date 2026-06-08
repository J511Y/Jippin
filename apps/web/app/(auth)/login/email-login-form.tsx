'use client';

import { Alert, Button, PasswordInput, Stack, TextInput } from '@mantine/core';
import { useState } from 'react';

/**
 * 이메일/비밀번호 로그인 폼 (CMP-DIRECT).
 *
 * 같은 origin Route Handler `/auth/password-login` 에 자격증명을 POST 한다. 비밀번호는
 * 서버측에서만 다루며, 성공 시 응답의 redirect 로 이동한다.
 */

export function EmailLoginForm({ nextPath }: { nextPath: string }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!email.trim() || !password) {
      setError('이메일과 비밀번호를 입력해 주세요.');
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetch('/auth/password-login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), password, next: nextPath })
      });
      const data = (await res.json().catch(() => null)) as
        | { redirect?: string; error?: string }
        | null;
      if (!res.ok) {
        setError(data?.error ?? '로그인에 실패했습니다.');
        setSubmitting(false);
        return;
      }
      window.location.assign(data?.redirect ?? nextPath);
    } catch {
      setError('로그인 처리 중 오류가 발생했습니다.');
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      <Stack gap="sm">
        <TextInput
          label="이메일"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.currentTarget.value)}
          inputMode="email"
          autoComplete="email"
          required
        />
        <PasswordInput
          label="비밀번호"
          placeholder="비밀번호"
          value={password}
          onChange={(e) => setPassword(e.currentTarget.value)}
          autoComplete="current-password"
          required
        />
        {error ? (
          <Alert color="red" variant="light" py="xs">
            {error}
          </Alert>
        ) : null}
        <Button type="submit" color="jippin" size="md" radius="md" loading={submitting} fullWidth>
          로그인
        </Button>
      </Stack>
    </form>
  );
}

'use client';

import {
  Alert,
  Anchor,
  Button,
  Checkbox,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  Title
} from '@mantine/core';
import { useState } from 'react';

import { AccountApiError, signup } from '@/lib/auth/account-api';
import { PhoneVerification } from '@/components/auth/PhoneVerification';

/**
 * 이메일/비밀번호 회원가입 폼 (CMP-DIRECT).
 *
 * 이름·이메일·연락처(문자 인증)·비밀번호를 받아 Supabase Auth 계정을 만든다(백엔드
 * `/auth/signup`). 가입 직후 같은 origin Route Handler `/auth/password-login` 으로 세션을
 * 발급받아 `next` 로 이동한다.
 */

const MIN_PASSWORD = 6;
const HAS_LETTER = /[A-Za-z]/;
const HAS_DIGIT = /\d/;

function passwordError(pw: string): string | null {
  if (pw.length < MIN_PASSWORD) return `비밀번호는 최소 ${MIN_PASSWORD}자 이상이어야 합니다.`;
  if (!HAS_LETTER.test(pw) || !HAS_DIGIT.test(pw)) return '비밀번호는 영문과 숫자를 모두 포함해야 합니다.';
  return null;
}

export function SignupForm({ nextPath }: { nextPath: string }) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [phoneToken, setPhoneToken] = useState<string | null>(null);
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [agreed, setAgreed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (!name.trim()) return setError('이름을 입력해 주세요.');
    if (!email.trim()) return setError('이메일을 입력해 주세요.');
    if (!phoneToken) return setError('휴대폰 인증을 완료해 주세요.');
    const pwErr = passwordError(password);
    if (pwErr) return setError(pwErr);
    if (password !== confirm) return setError('비밀번호가 일치하지 않습니다.');
    if (!agreed) return setError('이용약관 및 개인정보처리방침에 동의해 주세요.');

    setSubmitting(true);
    try {
      await signup({
        name: name.trim(),
        email: email.trim(),
        phone,
        password,
        phone_token: phoneToken,
        agreed_to_terms: agreed
      });

      const res = await fetch('/auth/password-login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), password, next: nextPath })
      });
      if (!res.ok) {
        // 계정은 생성됐으나 자동 로그인 실패 — 로그인 페이지로 안내.
        window.location.assign('/login?registered=1');
        return;
      }
      const data = (await res.json()) as { redirect?: string };
      window.location.assign(data.redirect ?? nextPath);
    } catch (err) {
      if (err instanceof AccountApiError && err.code === 'PHONE_TOKEN_INVALID') {
        setPhoneToken(null);
      }
      setError(err instanceof AccountApiError ? err.message : '회원가입에 실패했습니다.');
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      <Stack gap="md">
        <Stack gap={4}>
          <Title order={1} fz="h2">
            회원가입
          </Title>
          <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
            이름, 이메일, 휴대폰 인증, 비밀번호로 집핀 계정을 만듭니다.
          </Text>
        </Stack>

        <TextInput
          label="이름"
          placeholder="홍길동"
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
          autoComplete="name"
          required
        />
        <TextInput
          label="이메일"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.currentTarget.value)}
          inputMode="email"
          autoComplete="email"
          required
        />

        <PhoneVerification
          phone={phone}
          onPhoneChange={setPhone}
          onVerifiedChange={setPhoneToken}
          disabled={submitting}
        />

        <PasswordInput
          label="비밀번호"
          description="6자 이상, 영문과 숫자 포함"
          placeholder="비밀번호"
          value={password}
          onChange={(e) => setPassword(e.currentTarget.value)}
          autoComplete="new-password"
          required
        />
        <PasswordInput
          label="비밀번호 확인"
          placeholder="비밀번호 재입력"
          value={confirm}
          onChange={(e) => setConfirm(e.currentTarget.value)}
          autoComplete="new-password"
          required
        />

        <Checkbox
          checked={agreed}
          onChange={(e) => setAgreed(e.currentTarget.checked)}
          label={
            <Text size="sm" style={{ wordBreak: 'keep-all' }}>
              <Anchor href="/terms" target="_blank" c="var(--jippin-brand-primary)">
                이용약관
              </Anchor>
              과{' '}
              <Anchor href="/privacy" target="_blank" c="var(--jippin-brand-primary)">
                개인정보처리방침
              </Anchor>
              에 동의합니다. (필수)
            </Text>
          }
        />

        {error ? (
          <Alert color="red" variant="light">
            {error}
          </Alert>
        ) : null}

        <Button type="submit" color="jippin" size="md" radius="md" loading={submitting} fullWidth>
          가입하기
        </Button>

        <Text size="sm" c="dimmed" ta="center">
          이미 계정이 있으신가요?{' '}
          <Anchor href="/login" c="var(--jippin-brand-primary)">
            로그인
          </Anchor>
        </Text>
      </Stack>
    </form>
  );
}

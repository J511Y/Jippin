'use client';

import { Alert, Button, PasswordInput, Stack, Text, TextInput, Title } from '@mantine/core';
import { useState } from 'react';

import { AccountApiError, resetPassword } from '@/lib/auth/account-api';
import { PhoneVerification } from '@/components/auth/PhoneVerification';

/**
 * 비밀번호 찾기(재설정) 폼 (CMP-DIRECT).
 *
 * 이메일 + 휴대폰 문자 인증으로 본인 확인 후 새 비밀번호로 재설정한다(이메일 발송 의존 없음).
 */

const MIN_PASSWORD = 6;
const HAS_LETTER = /[A-Za-z]/;
const HAS_DIGIT = /\d/;

function passwordError(pw: string): string | null {
  if (pw.length < MIN_PASSWORD) return `비밀번호는 최소 ${MIN_PASSWORD}자 이상이어야 합니다.`;
  if (!HAS_LETTER.test(pw) || !HAS_DIGIT.test(pw)) return '비밀번호는 영문과 숫자를 모두 포함해야 합니다.';
  return null;
}

export function FindPasswordForm() {
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [phoneToken, setPhoneToken] = useState<string | null>(null);
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!email.trim()) return setError('이메일을 입력해 주세요.');
    if (!phoneToken) return setError('휴대폰 인증을 완료해 주세요.');
    const pwErr = passwordError(password);
    if (pwErr) return setError(pwErr);
    if (password !== confirm) return setError('비밀번호가 일치하지 않습니다.');

    setLoading(true);
    try {
      await resetPassword({
        email: email.trim(),
        phone,
        phone_token: phoneToken,
        new_password: password
      });
      setDone(true);
    } catch (err) {
      if (err instanceof AccountApiError && err.code === 'PHONE_TOKEN_INVALID') {
        setPhoneToken(null);
      }
      setError(err instanceof AccountApiError ? err.message : '비밀번호 재설정에 실패했습니다.');
      setLoading(false);
    }
  }

  if (done) {
    return (
      <Stack gap="md">
        <Title order={1} fz="h2">
          비밀번호 재설정 완료
        </Title>
        <Alert color="teal" variant="light">
          비밀번호가 변경되었습니다. 새 비밀번호로 로그인해 주세요.
        </Alert>
        <Button component="a" href="/login" color="jippin" radius="md" fullWidth>
          로그인하러 가기
        </Button>
      </Stack>
    );
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      <Stack gap="md">
        <Stack gap={4}>
          <Title order={1} fz="h2">
            비밀번호 찾기
          </Title>
          <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
            가입 이메일과 휴대폰 인증으로 본인 확인 후 새 비밀번호를 설정합니다.
          </Text>
        </Stack>

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
          disabled={loading}
        />

        <PasswordInput
          label="새 비밀번호"
          description="6자 이상, 영문과 숫자 포함"
          placeholder="새 비밀번호"
          value={password}
          onChange={(e) => setPassword(e.currentTarget.value)}
          autoComplete="new-password"
          required
        />
        <PasswordInput
          label="새 비밀번호 확인"
          placeholder="새 비밀번호 재입력"
          value={confirm}
          onChange={(e) => setConfirm(e.currentTarget.value)}
          autoComplete="new-password"
          required
        />

        {error ? (
          <Alert color="red" variant="light">
            {error}
          </Alert>
        ) : null}

        <Button
          type="submit"
          color="jippin"
          radius="md"
          fullWidth
          loading={loading}
          disabled={!phoneToken}
        >
          비밀번호 재설정
        </Button>
      </Stack>
    </form>
  );
}

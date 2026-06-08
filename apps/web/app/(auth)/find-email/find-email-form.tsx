'use client';

import { Alert, Anchor, Button, Card, Stack, Text, Title } from '@mantine/core';
import { useState } from 'react';

import { AccountApiError, findEmail, type FoundEmail } from '@/lib/auth/account-api';
import { PhoneVerification } from '@/components/auth/PhoneVerification';

/**
 * 아이디(이메일) 찾기 폼 (CMP-DIRECT).
 *
 * 휴대폰 문자 인증 후, 해당 번호로 가입된 이메일(마스킹)을 조회한다.
 */

export function FindEmailForm() {
  const [phone, setPhone] = useState('');
  const [phoneToken, setPhoneToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<FoundEmail[] | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!phoneToken) {
      setError('휴대폰 인증을 완료해 주세요.');
      return;
    }
    setLoading(true);
    try {
      const { emails } = await findEmail(phone, phoneToken);
      setResults(emails);
      setPhoneToken(null); // 토큰 1회 소비됨.
    } catch (err) {
      setError(err instanceof AccountApiError ? err.message : '조회에 실패했습니다.');
    } finally {
      setLoading(false);
    }
  }

  if (results !== null) {
    return (
      <Stack gap="md">
        <Title order={1} fz="h2">
          아이디 찾기 결과
        </Title>
        {results.length === 0 ? (
          <Alert color="gray" variant="light">
            해당 휴대폰 번호로 가입된 이메일 계정이 없습니다. 카카오로 가입하셨을 수 있어요.
          </Alert>
        ) : (
          <Card withBorder radius="lg" padding="lg">
            <Stack gap="sm">
              {results.map((item) => (
                <Stack key={item.email_masked} gap={2}>
                  <Text fw={600}>{item.email_masked}</Text>
                  <Text size="xs" c="dimmed">
                    {item.created_at.slice(0, 10)} 가입
                  </Text>
                </Stack>
              ))}
            </Stack>
          </Card>
        )}
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
            아이디 찾기
          </Title>
          <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
            가입 시 등록한 휴대폰 번호로 인증하면 이메일(아이디)을 알려드려요.
          </Text>
        </Stack>

        <PhoneVerification
          phone={phone}
          onPhoneChange={setPhone}
          onVerifiedChange={setPhoneToken}
          disabled={loading}
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
          아이디 찾기
        </Button>

        <Text size="sm" c="dimmed" ta="center">
          비밀번호가 기억나지 않으세요?{' '}
          <Anchor href="/find-password" c="var(--jippin-brand-primary)">
            비밀번호 찾기
          </Anchor>
        </Text>
      </Stack>
    </form>
  );
}

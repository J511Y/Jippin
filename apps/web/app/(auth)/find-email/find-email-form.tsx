'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { Alert, Anchor, Button, Card, Stack, Text, Title } from '@mantine/core';
import { useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';

import { AccountApiError, findEmail, type FoundEmail } from '@/lib/auth/account-api';
import { findEmailSchema, type FindEmailValues } from '@/lib/auth/validation';
import { PhoneVerification } from '@/components/auth/PhoneVerification';

/**
 * 아이디(이메일) 찾기 폼 (CMP-DIRECT).
 *
 * 휴대폰 문자 인증 후, 해당 번호로 가입된 이메일(마스킹)을 조회한다.
 * react-hook-form + zod 로 focus-out 검증을 표준화한다.
 */

export function FindEmailForm() {
  const [serverError, setServerError] = useState<string | null>(null);
  const [results, setResults] = useState<FoundEmail[] | null>(null);
  const {
    handleSubmit,
    control,
    setValue,
    trigger,
    formState: { errors, isSubmitting }
  } = useForm<FindEmailValues>({
    resolver: zodResolver(findEmailSchema),
    mode: 'onTouched',
    defaultValues: { phone: '', phoneToken: '' }
  });

  const phone = useWatch({ control, name: 'phone' });

  async function onSubmit(values: FindEmailValues) {
    setServerError(null);
    try {
      const { emails } = await findEmail(values.phone, values.phoneToken);
      setResults(emails);
      setValue('phoneToken', ''); // 토큰 1회 소비됨.
    } catch (err) {
      setServerError(err instanceof AccountApiError ? err.message : '조회에 실패했습니다.');
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
    <form onSubmit={handleSubmit(onSubmit)} noValidate>
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
          onPhoneChange={(v) => setValue('phone', v, { shouldDirty: true })}
          onVerifiedChange={(token) => setValue('phoneToken', token ?? '', { shouldValidate: true })}
          onBlur={() => void trigger('phone')}
          fieldError={errors.phone?.message ?? errors.phoneToken?.message}
          disabled={isSubmitting}
        />

        {serverError ? (
          <Alert color="red" variant="light">
            {serverError}
          </Alert>
        ) : null}

        <Button type="submit" color="jippin" radius="md" fullWidth loading={isSubmitting}>
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

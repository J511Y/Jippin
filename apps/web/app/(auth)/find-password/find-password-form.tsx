'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { Alert, Button, PasswordInput, Stack, Text, TextInput, Title } from '@mantine/core';
import { useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';

import { AccountApiError, resetPassword } from '@/lib/auth/account-api';
import { findPasswordSchema, type FindPasswordValues } from '@/lib/auth/validation';
import { PhoneVerification } from '@/components/auth/PhoneVerification';

/**
 * 비밀번호 찾기(재설정) 폼 (CMP-DIRECT).
 *
 * 이메일 + 휴대폰 문자 인증으로 본인 확인 후 새 비밀번호로 재설정한다(이메일 발송 의존 없음).
 * react-hook-form + zod 로 focus-out 검증을 표준화한다.
 */

export function FindPasswordForm() {
  const [serverError, setServerError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const {
    register,
    handleSubmit,
    control,
    setValue,
    trigger,
    formState: { errors, isSubmitting }
  } = useForm<FindPasswordValues>({
    resolver: zodResolver(findPasswordSchema),
    mode: 'onTouched',
    defaultValues: { email: '', phone: '', phoneToken: '', password: '', confirm: '' }
  });

  const phone = useWatch({ control, name: 'phone' });
  const phoneToken = useWatch({ control, name: 'phoneToken' });

  async function onSubmit(values: FindPasswordValues) {
    setServerError(null);
    try {
      await resetPassword({
        email: values.email.trim(),
        phone: values.phone,
        phone_token: values.phoneToken,
        new_password: values.password
      });
      setDone(true);
    } catch (err) {
      if (err instanceof AccountApiError && err.code === 'PHONE_TOKEN_INVALID') {
        setValue('phoneToken', '', { shouldValidate: true });
      }
      setServerError(err instanceof AccountApiError ? err.message : '비밀번호 재설정에 실패했습니다.');
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
    <form onSubmit={handleSubmit(onSubmit)} noValidate>
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
          inputMode="email"
          autoComplete="email"
          error={errors.email?.message}
          {...register('email')}
        />

        <PhoneVerification
          phone={phone}
          onPhoneChange={(v) => setValue('phone', v, { shouldDirty: true })}
          onVerifiedChange={(token) => setValue('phoneToken', token ?? '', { shouldValidate: true })}
          onBlur={() => void trigger('phone')}
          fieldError={errors.phone?.message ?? errors.phoneToken?.message}
          verified={Boolean(phoneToken)}
          disabled={isSubmitting}
        />

        <PasswordInput
          label="새 비밀번호"
          description="6자 이상, 영문과 숫자 포함"
          placeholder="새 비밀번호"
          autoComplete="new-password"
          error={errors.password?.message}
          {...register('password')}
        />
        <PasswordInput
          label="새 비밀번호 확인"
          placeholder="새 비밀번호 재입력"
          autoComplete="new-password"
          error={errors.confirm?.message}
          {...register('confirm')}
        />

        {serverError ? (
          <Alert color="red" variant="light">
            {serverError}
          </Alert>
        ) : null}

        <Button type="submit" color="jippin" radius="md" fullWidth loading={isSubmitting}>
          비밀번호 재설정
        </Button>
      </Stack>
    </form>
  );
}

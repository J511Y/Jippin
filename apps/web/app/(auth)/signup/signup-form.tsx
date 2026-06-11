'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import {
  Alert,
  Anchor,
  Button,
  Checkbox,
  Divider,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  Title
} from '@mantine/core';
import { useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';

import { AccountApiError, signup } from '@/lib/auth/account-api';
import { signupSchema, type SignupValues } from '@/lib/auth/validation';
import { PhoneVerification } from '@/components/auth/PhoneVerification';

/**
 * 이메일/비밀번호 회원가입 폼 (CMP-DIRECT).
 *
 * react-hook-form + zod(`mode: onTouched`)로 focus-out 검증을 표준화한다. 휴대폰 인증
 * 토큰은 `phoneToken` 필드로 폼에 반영되어 zod 가 함께 검증한다. 가입 직후 같은 origin
 * Route Handler `/auth/password-login` 으로 세션을 발급받아 `next` 로 이동한다.
 */

export function SignupForm({ nextPath }: { nextPath: string }) {
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    control,
    setValue,
    trigger,
    formState: { errors, isSubmitting }
  } = useForm<SignupValues>({
    resolver: zodResolver(signupSchema),
    mode: 'onTouched',
    defaultValues: {
      name: '',
      email: '',
      phone: '',
      phoneToken: '',
      password: '',
      confirm: '',
      agreed: false,
      over14: false,
      marketing: false
    }
  });

  const phone = useWatch({ control, name: 'phone' });
  const phoneToken = useWatch({ control, name: 'phoneToken' });

  async function onSubmit(values: SignupValues) {
    setServerError(null);
    try {
      await signup({
        name: values.name.trim(),
        email: values.email.trim(),
        phone: values.phone,
        password: values.password,
        phone_token: values.phoneToken,
        agreed_to_terms: values.agreed,
        age_over_14: values.over14,
        marketing_consent: values.marketing
      });

      const res = await fetch('/auth/password-login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: values.email.trim(), password: values.password, next: nextPath })
      });
      if (!res.ok) {
        window.location.assign('/login?registered=1');
        return;
      }
      const data = (await res.json()) as { redirect?: string };
      window.location.assign(data.redirect ?? nextPath);
    } catch (err) {
      if (err instanceof AccountApiError && err.code === 'PHONE_TOKEN_INVALID') {
        setValue('phoneToken', '', { shouldValidate: true });
      }
      setServerError(err instanceof AccountApiError ? err.message : '회원가입에 실패했습니다.');
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate>
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
          autoComplete="name"
          error={errors.name?.message}
          {...register('name')}
        />
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
          label="비밀번호"
          description="6자 이상, 영문과 숫자 포함"
          placeholder="비밀번호"
          autoComplete="new-password"
          error={errors.password?.message}
          {...register('password')}
        />
        <PasswordInput
          label="비밀번호 확인"
          placeholder="비밀번호 재입력"
          autoComplete="new-password"
          error={errors.confirm?.message}
          {...register('confirm')}
        />

        <Checkbox
          error={errors.agreed?.message}
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
          {...register('agreed')}
        />

        <Checkbox
          error={errors.over14?.message}
          label={
            <Text size="sm" style={{ wordBreak: 'keep-all' }}>
              만 14세 이상입니다. (필수)
            </Text>
          }
          {...register('over14')}
        />

        {/* 선택 동의 — 필수 동의와 시각적으로 분리(정보통신망법 §50 광고성 정보 수신). */}
        <Divider />

        <Checkbox
          label={
            <Text size="sm" style={{ wordBreak: 'keep-all' }}>
              이벤트·혜택 등 광고성 정보(SMS 등) 수신에 동의합니다. (선택)
            </Text>
          }
          {...register('marketing')}
        />

        {serverError ? (
          <Alert color="red" variant="light">
            {serverError}
          </Alert>
        ) : null}

        <Button type="submit" color="jippin" size="md" radius="md" loading={isSubmitting} fullWidth>
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

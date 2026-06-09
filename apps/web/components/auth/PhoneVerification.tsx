'use client';

import { Button, Group, Stack, Text, TextInput } from '@mantine/core';
import { IconCheck } from '@tabler/icons-react';
import { useCallback, useEffect, useRef, useState } from 'react';

import { normalizeKoreanPhone } from '@/lib/leads/validation';
import { AccountApiError, sendPhoneCode, verifyPhoneCode } from '@/lib/auth/account-api';

/**
 * 휴대폰 문자(SMS) 본인인증 위젯 (CMP-DIRECT).
 *
 * 일반적인 전화번호 인증 프로세스: 번호 입력 → 인증번호 발송 → 6자리 입력 → 확인.
 * 인증 성공 시 부모에 `phone_token` 을 올려보내고, 번호를 다시 수정하면 인증을 무효화한다.
 * 휴대폰(01x)만 허용한다 — 문자 수신이 가능한 번호여야 한다.
 */

const RESEND_COOLDOWN_SECONDS = 30;

function isMobile(raw: string): boolean {
  const normalized = normalizeKoreanPhone(raw);
  return normalized !== null && normalized.startsWith('01');
}

type Props = {
  phone: string;
  onPhoneChange: (value: string) => void;
  onVerifiedChange: (token: string | null) => void;
  disabled?: boolean;
  /** RHF 등 외부 폼의 필드 에러 메시지. */
  fieldError?: string | null;
  /** 인증 완료 여부(부모가 보유한 phoneToken 유무). 입력 잠금/해제의 단일 원천. */
  verified?: boolean;
  /** 휴대폰 입력 focus-out 시 외부 폼 검증 트리거. */
  onBlur?: () => void;
};

export function PhoneVerification({
  phone,
  onPhoneChange,
  onVerifiedChange,
  disabled = false,
  fieldError = null,
  verified = false,
  onBlur
}: Props) {
  const [code, setCode] = useState('');
  const [sent, setSent] = useState(false);
  const [sending, setSending] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const startCooldown = useCallback(() => {
    setCooldown(RESEND_COOLDOWN_SECONDS);
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      setCooldown((prev) => {
        if (prev <= 1) {
          if (timerRef.current) clearInterval(timerRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }, []);

  function handlePhoneChange(value: string) {
    onPhoneChange(value);
    if (verified) {
      // 번호를 바꾸면 부모의 인증 토큰을 무효화한다(부모가 verified 상태의 원천).
      onVerifiedChange(null);
    }
    setSent(false);
    setCode('');
    setError(null);
    setInfo(null);
  }

  async function handleSend() {
    if (!isMobile(phone)) {
      setError('휴대폰 번호 형식이 올바르지 않습니다. 예: 010-1234-5678');
      return;
    }
    setSending(true);
    setError(null);
    setInfo(null);
    try {
      await sendPhoneCode(phone);
      setSent(true);
      startCooldown();
      setInfo('인증번호를 발송했습니다. 문자를 확인해 주세요.');
    } catch (err) {
      setError(err instanceof AccountApiError ? err.message : '인증번호 발송에 실패했습니다.');
    } finally {
      setSending(false);
    }
  }

  async function handleVerify() {
    setVerifying(true);
    setError(null);
    setInfo(null);
    try {
      const { phone_token } = await verifyPhoneCode(phone, code.trim());
      // 부모가 phoneToken 을 보유하면 verified=true 로 내려와 입력이 잠긴다(상태 원천=부모).
      onVerifiedChange(phone_token);
      setInfo('인증되었습니다.');
    } catch (err) {
      setError(err instanceof AccountApiError ? err.message : '인증에 실패했습니다.');
    } finally {
      setVerifying(false);
    }
  }

  const lockInputs = disabled || verified;

  return (
    <Stack gap="xs">
      <Group gap="xs" align="flex-end" wrap="nowrap">
        <TextInput
          label="휴대폰 번호"
          placeholder="010-1234-5678"
          value={phone}
          onChange={(e) => handlePhoneChange(e.currentTarget.value)}
          onBlur={onBlur}
          error={fieldError ?? undefined}
          disabled={lockInputs}
          inputMode="tel"
          autoComplete="tel"
          style={{ flex: 1 }}
          rightSection={
            verified ? <IconCheck size={18} color="var(--mantine-color-teal-6)" /> : undefined
          }
        />
        <Button
          type="button"
          variant="light"
          color="jippin"
          onClick={() => void handleSend()}
          loading={sending}
          disabled={lockInputs || cooldown > 0}
        >
          {cooldown > 0 ? `재발송 ${cooldown}s` : sent ? '재발송' : '인증번호 받기'}
        </Button>
      </Group>

      {sent && !verified ? (
        <Group gap="xs" align="flex-end" wrap="nowrap">
          <TextInput
            label="인증번호"
            placeholder="6자리 숫자"
            value={code}
            onChange={(e) => setCode(e.currentTarget.value.replace(/[^\d]/g, ''))}
            inputMode="numeric"
            maxLength={6}
            style={{ flex: 1 }}
          />
          <Button
            type="button"
            color="jippin"
            onClick={() => void handleVerify()}
            loading={verifying}
            disabled={code.trim().length < 4}
          >
            확인
          </Button>
        </Group>
      ) : null}

      {error ? (
        <Text size="sm" c="red">
          {error}
        </Text>
      ) : null}
      {!error && info ? (
        <Text size="sm" c={verified ? 'teal' : 'dimmed'}>
          {info}
        </Text>
      ) : null}
    </Stack>
  );
}

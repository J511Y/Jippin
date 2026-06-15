'use client';

import { Alert, Button, Card, Group, Image, Stack, Text, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useState } from 'react';

import { parseApiError } from '@/lib/api/error';
import { continueHomeCheck, type HomeCheckJob } from '@/lib/home-check/api';

type NeedsInput = NonNullable<HomeCheckJob['needs_input']>;

/**
 * needs_input 폴백 UI (CMP-DIRECT, ADR-0008).
 *
 *  - kind==='dong_ho' : 동·호 자동매칭 실패 → 사용자가 동·호를 재입력해 재개.
 *  - kind==='secure_no': 세움터 보안문자 입력 필요 → 보안문자 입력해 재개.
 *
 * 제출은 `POST /home-check/{id}/continue`. 성공하면 상위(폴링 화면)가 다시 폴링하도록
 * onResumed(갱신된 잡)를 호출한다.
 */
export function HomeCheckNeedsInput({
  checkId,
  needsInput,
  secureImageUrl,
  onResumed
}: {
  checkId: string;
  needsInput: NeedsInput;
  /** 보안문자 이미지가 있으면 표시(백엔드가 needs_input 응답에 별도 제공 시). */
  secureImageUrl?: string | null;
  onResumed: (job: HomeCheckJob) => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const form = useForm<{ dong: string; ho: string; secure_no: string }>({
    initialValues: { dong: '', ho: '', secure_no: '' },
    validate:
      needsInput.kind === 'secure_no'
        ? { secure_no: (v) => (v.trim() ? null : '보안문자를 입력해 주세요.') }
        : { ho: (v) => (v.trim() ? null : '호를 입력해 주세요.') }
  });

  const handleSubmit = form.onSubmit(async (values) => {
    setSubmitting(true);
    setServerError(null);
    try {
      const payload =
        needsInput.kind === 'secure_no'
          ? { secure_no: values.secure_no.trim() }
          : { dong: values.dong.trim() || undefined, ho: values.ho.trim() };
      const job = await continueHomeCheck(checkId, payload);
      onResumed(job);
    } catch (error) {
      setServerError(parseApiError(error).message);
      setSubmitting(false);
    }
  });

  return (
    <Card withBorder radius="lg" padding="lg" component="form" onSubmit={handleSubmit}>
      <Stack gap="md">
        <Alert color="yellow" variant="light" radius="md" title="추가 입력이 필요해요">
          <Text size="sm" style={{ wordBreak: 'keep-all' }}>
            {needsInput.message}
          </Text>
        </Alert>

        {needsInput.kind === 'dong_ho' ? (
          <Group grow align="flex-start">
            <TextInput
              label="동"
              placeholder="예: 101 (없으면 비워두세요)"
              {...form.getInputProps('dong')}
            />
            <TextInput label="호" withAsterisk placeholder="예: 1502" {...form.getInputProps('ho')} />
          </Group>
        ) : (
          <Stack gap="xs">
            {secureImageUrl ? (
              <Image
                src={secureImageUrl}
                alt="보안문자 이미지"
                radius="md"
                fit="contain"
                h={80}
                w="auto"
              />
            ) : null}
            <TextInput
              label="보안문자"
              withAsterisk
              placeholder="이미지에 표시된 문자를 입력하세요"
              {...form.getInputProps('secure_no')}
            />
          </Stack>
        )}

        {serverError ? (
          <Alert color="red" variant="light" py="xs">
            {serverError}
          </Alert>
        ) : null}

        <Button type="submit" color="coral" radius="md" fullWidth loading={submitting}>
          다시 조회하기
        </Button>
      </Stack>
    </Card>
  );
}

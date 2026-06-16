'use client';

import { Alert, Button, Card, Group, Image, Select, Stack, Text, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useState } from 'react';

import { parseApiError } from '@/lib/api/error';
import { continueHomeCheck, type HomeCheckJob } from '@/lib/home-check/api';

type NeedsInput = NonNullable<HomeCheckJob['needs_input']>;
type NeedsInputOption = NonNullable<NeedsInput['options']>[number];

const FIELD_LABEL: Record<string, string> = {
  address: '주소',
  dong: '동',
  ho: '호'
};

/** 후보 1건을 드롭다운 표시 라벨로. 호는 면적을 같이 보여줘 같은 번호를 구분하게 한다. */
function optionLabel(field: string | null | undefined, option: NeedsInputOption): string {
  if (field === 'ho' && option.area) {
    return `${option.label} · ${option.area}㎡`;
  }
  return option.label;
}

/**
 * needs_input 폴백 UI (CMP-DIRECT, ADR-0008).
 *
 *  - kind==='dong_ho' + options : CODEF 가 돌려준 주소/동/호 후보를 드롭다운으로 제시 →
 *    사용자가 골라(selection) 재개한다. 같은 번호의 호는 면적으로 구분한다.
 *  - kind==='dong_ho' (options 없음): 하위호환 — 동·호 자유입력으로 재개.
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

  const options = needsInput.options ?? [];
  const hasOptions = needsInput.kind === 'dong_ho' && options.length > 0;
  const fieldLabel = FIELD_LABEL[needsInput.field ?? ''] ?? '항목';

  const form = useForm<{ selection: string; dong: string; ho: string; secure_no: string }>({
    initialValues: { selection: '', dong: '', ho: '', secure_no: '' },
    validate:
      needsInput.kind === 'secure_no'
        ? { secure_no: (v) => (v.trim() ? null : '보안문자를 입력해 주세요.') }
        : hasOptions
          ? { selection: (v) => (v ? null : `${fieldLabel}을(를) 선택해 주세요.`) }
          : { ho: (v) => (v.trim() ? null : '호를 입력해 주세요.') }
  });

  const handleSubmit = form.onSubmit(async (values) => {
    setSubmitting(true);
    setServerError(null);
    try {
      const payload =
        needsInput.kind === 'secure_no'
          ? { secure_no: values.secure_no.trim() }
          : hasOptions
            ? { selection: values.selection }
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

        {needsInput.kind === 'secure_no' ? (
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
        ) : hasOptions ? (
          <Select
            label={`${fieldLabel} 선택`}
            withAsterisk
            searchable
            placeholder={`${fieldLabel}을(를) 선택하세요`}
            nothingFoundMessage="일치하는 항목이 없어요"
            maxDropdownHeight={280}
            data={options.map((opt) => ({ value: opt.value, label: optionLabel(needsInput.field, opt) }))}
            {...form.getInputProps('selection')}
          />
        ) : (
          <Group grow align="flex-start">
            <TextInput
              label="동"
              placeholder="예: 101 (없으면 비워두세요)"
              {...form.getInputProps('dong')}
            />
            <TextInput label="호" withAsterisk placeholder="예: 1502" {...form.getInputProps('ho')} />
          </Group>
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

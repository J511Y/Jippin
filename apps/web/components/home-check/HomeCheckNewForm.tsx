'use client';

import { Alert, Button, Card, Group, Stack, Text, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { IconSearch } from '@tabler/icons-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { parseApiError } from '@/lib/api/error';
import { createHomeCheck } from '@/lib/home-check/api';
import { ensureAnonymousSession } from '@/lib/leads/ensure-anonymous-session';
import { openJusoAddressPopup } from '@/lib/leads/juso-popup';

interface HomeCheckFormValues {
  road_addr: string;
  jibun_addr: string;
  dong: string;
  ho: string;
}

const INITIAL_VALUES: HomeCheckFormValues = {
  road_addr: '',
  jibun_addr: '',
  dong: '',
  ho: ''
};

/**
 * 우리집 체크 시작 폼 (CMP-DIRECT, ADR-0008).
 *
 * leads 와 동일한 도로명주소 팝업을 재사용해 건물 주소를 받고, 집합건물 세대 식별을 위해
 * 동·호를 추가로 입력받는다. 제출 시 `POST /home-check` → 받은 jobId 의 상세(`/home-check/[id]`)로
 * 이동한다. 익명(비로그인)도 허용한다(ensureAnonymousSession).
 */
export function HomeCheckNewForm() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);

  const form = useForm<HomeCheckFormValues>({
    initialValues: INITIAL_VALUES,
    validate: {
      road_addr: (value) => (value.trim() ? null : '주소를 검색해 선택해 주세요.'),
      ho: (value) => (value.trim() ? null : '호를 입력해 주세요.')
    }
  });

  async function openAddressPopup() {
    // juso 팝업이 도로명 기본주소(part1)+부가정보(part2)를 돌려준다. 우리집 체크는 건물
    // 주소만 필요하므로 두 조각을 합쳐 road_addr 로 쓴다(상세주소는 동·호 필드로 받는다).
    const result = await openJusoAddressPopup();
    const roadAddr = [result.roadAddrPart1, result.roadAddrPart2].filter(Boolean).join(' ').trim();
    form.setFieldValue('road_addr', roadAddr);
    form.clearFieldError('road_addr');
  }

  const handleSubmit = form.onSubmit(async (values) => {
    setSubmitting(true);
    try {
      // 세션 보장: apiClient 가 Bearer 를 부착한다(익명 세션 허용).
      await ensureAnonymousSession();
      const job = await createHomeCheck({
        road_addr: values.road_addr.trim(),
        jibun_addr: values.jibun_addr.trim() || null,
        dong: values.dong.trim(),
        ho: values.ho.trim()
      });
      router.push(`/home-check/${job.id}`);
    } catch (error) {
      notifications.show({
        color: 'red',
        title: '조회 요청에 실패했어요',
        message: parseApiError(error).message
      });
      setSubmitting(false);
    }
  });

  return (
    <Card withBorder padding="md" component="form" onSubmit={handleSubmit}>
      <Stack gap="md">
        <Stack gap="xs">
          <Group justify="space-between" align="center" wrap="nowrap">
            <Text size="sm" fw={600}>
              건물 주소 <Text component="span" c="red">*</Text>
            </Text>
            <Button
              type="button"
              variant="light"
              color="jippin"
              size="xs"
              leftSection={<IconSearch size={16} aria-hidden />}
              onClick={() => void openAddressPopup()}
            >
              주소 검색
            </Button>
          </Group>
          <TextInput
            placeholder="주소 검색을 눌러 도로명주소를 선택하세요"
            readOnly
            value={form.values.road_addr}
            error={form.errors.road_addr}
          />
        </Stack>

        <Group grow align="flex-start">
          <TextInput
            label="동"
            placeholder="예: 101 (없으면 비워두세요)"
            {...form.getInputProps('dong')}
          />
          <TextInput
            label="호"
            withAsterisk
            placeholder="예: 1502"
            {...form.getInputProps('ho')}
          />
        </Group>

        <Alert color="jippin" variant="light" radius="md">
          <Text size="xs" style={{ wordBreak: 'keep-all' }}>
            건축물대장 조회는 외부 시스템 스크래핑을 거쳐 수십 초가 걸릴 수 있어요. 조회
            중에는 화면을 닫지 말고 잠시 기다려 주세요.
          </Text>
        </Alert>

        <Button type="submit" size="md" color="coral" radius="md" fullWidth loading={submitting}>
          내 집 체크하기
        </Button>
      </Stack>
    </Card>
  );
}

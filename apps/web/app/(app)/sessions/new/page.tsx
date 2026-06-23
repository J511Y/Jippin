'use client';

import { Button, Card, FileInput, Stack, Text, TextInput, Title } from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { IconUpload } from '@tabler/icons-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { parseApiError } from '@/lib/api/error';
import { ensureAnonymousSession } from '@/lib/leads/ensure-anonymous-session';
import {
  createFloorplanAsset,
  createSession,
  upsertSessionAddress
} from '@/lib/sessions/api';
import { deleteSessionFloorplan, uploadSessionFloorplan } from '@/lib/sessions/upload';

const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

export default function NewSessionPage() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [floorplan, setFloorplan] = useState<File | null>(null);

  const form = useForm({
    initialValues: { road_address: '', building_dong: '', unit_ho: '' },
    validate: {
      road_address: (v) => (v.trim().length === 0 ? '대상 주소를 입력해 주세요.' : null)
    }
  });

  const handleSubmit = form.onSubmit(async (values) => {
    if (floorplan && floorplan.size > MAX_UPLOAD_BYTES) {
      notifications.show({
        color: 'red',
        title: '도면 파일이 너무 큽니다',
        message: '최대 50MB 까지 업로드할 수 있어요.'
      });
      return;
    }
    setSubmitting(true);
    try {
      // 세션 보장: apiClient 가 Bearer 를 부착한다(익명 세션 허용).
      await ensureAnonymousSession();
      const session = await createSession();
      await upsertSessionAddress(session.id, {
        road_address: values.road_address.trim(),
        building_dong: values.building_dong.trim() || null,
        unit_ho: values.unit_ho.trim() || null
      });
      if (floorplan) {
        const uploaded = await uploadSessionFloorplan(session.id, floorplan);
        try {
          await createFloorplanAsset(session.id, uploaded);
        } catch (assetError) {
          // 업로드는 됐는데 메타 등록이 실패하면 방금 올린 도면을 정리(orphan PII 방지).
          await deleteSessionFloorplan(uploaded.object_key);
          throw assetError;
        }
      }
      router.push(`/sessions/${session.id}`);
    } catch (error) {
      notifications.show({
        color: 'red',
        title: '사전검토 시작에 실패했어요',
        message: parseApiError(error).message
      });
      setSubmitting(false);
    }
  });

  return (
    <Stack gap="lg">
      <Stack gap="xs">
        <Title order={1}>새 사전검토 시작</Title>
        <Text c="dimmed" size="sm" style={{ wordBreak: 'keep-all' }}>
          철거할 벽의 주소와 도면 한 장만 있으면 됩니다. 로그인 없이 익명으로 시작할
          수 있어요.
        </Text>
      </Stack>

      <Card withBorder padding="md" component="form" onSubmit={handleSubmit}>
        <Stack gap="md">
          <TextInput
            label="대상 주소"
            placeholder="예: 서울 강남구 테헤란로 12"
            withAsterisk
            {...form.getInputProps('road_address')}
          />
          <TextInput
            label="동 (선택)"
            placeholder="예: 101"
            {...form.getInputProps('building_dong')}
          />
          <TextInput
            label="호 (선택)"
            placeholder="예: 1502"
            {...form.getInputProps('unit_ho')}
          />
          <FileInput
            label="도면 파일 (선택)"
            description="이미지 파일만 지원합니다(JPG/PNG 등, PDF 미지원). 지금 없으면 대화 중에 올려도 됩니다."
            placeholder="도면 이미지를 선택하세요"
            accept="image/*"
            leftSection={<IconUpload size={16} aria-hidden />}
            clearable
            value={floorplan}
            onChange={setFloorplan}
          />
          <Button
            type="submit"
            size="md"
            color="jippin"
            radius="md"
            fullWidth
            loading={submitting}
          >
            사전검토 시작
          </Button>
        </Stack>
      </Card>

      <Button
        component="a"
        href="/sessions"
        variant="subtle"
        color="jippin"
        radius="md"
        w="fit-content"
      >
        내 세션 보기 →
      </Button>
    </Stack>
  );
}

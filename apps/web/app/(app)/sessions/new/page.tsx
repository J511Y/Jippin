import {
  Alert,
  Button,
  Card,
  Stack,
  Text,
  TextInput,
  Title
} from '@mantine/core';
import { IconInfoCircle } from '@tabler/icons-react';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '새 사전검토 시작'
};

export default function NewSessionPage() {
  return (
    <Stack gap="lg">
      <Stack gap="xs">
        <Title order={1}>새 사전검토 시작</Title>
        <Text c="dimmed" size="sm" style={{ wordBreak: 'keep-all' }}>
          철거할 벽의 주소와 도면 한 장만 있으면 됩니다. 로그인 없이 익명으로 시작할
          수 있어요.
        </Text>
      </Stack>

      <Alert
        color="jippin"
        variant="light"
        radius="md"
        icon={<IconInfoCircle size={18} aria-hidden />}
        title="아직 placeholder 입니다"
      >
        실제 도면 업로드와 세션 생성 API 는 후속 이슈에서 연결됩니다. 입력해도 저장되지
        않아요.
      </Alert>

      <Card withBorder radius="md" padding="md">
        <Stack gap="md">
          <TextInput
            label="대상 주소"
            placeholder="예: 서울 강남구 ○○로 12"
            disabled
          />
          <TextInput
            label="도면 파일"
            placeholder="이미지 또는 PDF (placeholder)"
            disabled
          />
          <Button
            size="md"
            color="jippin"
            radius="md"
            fullWidth
            disabled
            title="후속 이슈에서 활성화됩니다"
          >
            사전검토 시작
          </Button>
        </Stack>
      </Card>

      <Stack gap="xs">
        <Text size="sm" c="dimmed">
          이미 진행 중인 세션이 있나요?
        </Text>
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
    </Stack>
  );
}

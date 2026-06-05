import {
  Alert,
  Button,
  Card,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title
} from '@mantine/core';
import { IconInfoCircle } from '@tabler/icons-react';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '상담 신청서 작성'
};

export default function NewLeadPage() {
  return (
    <Stack gap="lg">
      <Stack gap="xs">
        <Title order={1}>상담 신청서</Title>
        <Text c="dimmed" size="sm" style={{ wordBreak: 'keep-all' }}>
          담당자가 영업일 기준 1일 이내에 연락드려요. 사전검토 리포트가 있으면
          자동으로 첨부됩니다.
        </Text>
      </Stack>

      <Alert
        color="jippin"
        variant="light"
        radius="md"
        icon={<IconInfoCircle size={18} aria-hidden />}
        title="아직 placeholder 입니다"
      >
        실제 상담 신청 API 는 후속 이슈에서 연결됩니다. 입력해도 저장되지 않아요.
      </Alert>

      <Card withBorder radius="md" padding="md">
        <Stack gap="md">
          <TextInput label="연락 가능한 이름" placeholder="예: 홍길동" disabled />
          <TextInput
            label="연락처"
            placeholder="010-0000-0000 또는 이메일"
            disabled
          />
          <TextInput
            label="대상 주소"
            placeholder="예: 서울 강남구 ○○로 12"
            disabled
          />
          <Textarea
            label="상담 메모"
            placeholder="어떤 부분이 궁금하신가요?"
            minRows={4}
            disabled
          />
          <Button
            size="md"
            color="coral"
            radius="md"
            fullWidth
            disabled
            title="후속 이슈에서 활성화됩니다"
          >
            상담 신청하기
          </Button>
        </Stack>
      </Card>
    </Stack>
  );
}

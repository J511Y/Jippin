import { Center, Stack } from '@mantine/core';

import { FindPasswordForm } from './find-password-form';

export const metadata = {
  title: '비밀번호 찾기'
};

export default function FindPasswordPage() {
  return (
    <Center mih="68vh" py="xl">
      <Stack gap="lg" w="100%" maw={420}>
        <FindPasswordForm />
      </Stack>
    </Center>
  );
}

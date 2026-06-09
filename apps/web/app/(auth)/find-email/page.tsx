import { Center, Stack } from '@mantine/core';

import { FindEmailForm } from './find-email-form';

export const metadata = {
  title: '아이디 찾기'
};

export default function FindEmailPage() {
  return (
    <Center mih="68vh" py="xl">
      <Stack gap="lg" w="100%" maw={420}>
        <FindEmailForm />
      </Stack>
    </Center>
  );
}

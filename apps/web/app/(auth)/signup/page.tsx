import { Center, Stack } from '@mantine/core';

import { isSafeNext } from '@/lib/safe-redirect';

import { SignupForm } from './signup-form';

/**
 * 회원가입 페이지 (CMP-DIRECT).
 *
 * 로그인 페이지에서 진입한다. `next` 는 SSR 에서 한 차례 검증해 가입 후 이동 경로로 쓴다.
 * 헤더(SiteShell)는 `(auth)/layout.tsx` 가 제공한다.
 */

export const metadata = {
  title: '회원가입'
};

type PageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

function pickNext(value: string | string[] | undefined): string {
  const candidate = Array.isArray(value) ? value[0] : value;
  if (candidate && isSafeNext(candidate)) return candidate;
  return '/';
}

export default async function SignupPage({ searchParams }: PageProps) {
  const resolved = (await searchParams) ?? {};
  const nextPath = pickNext(resolved.next);

  return (
    <Center mih="68vh" py="xl">
      <Stack gap="lg" w="100%" maw={420}>
        <SignupForm nextPath={nextPath} />
      </Stack>
    </Center>
  );
}

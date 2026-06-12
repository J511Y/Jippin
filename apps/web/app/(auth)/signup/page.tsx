import { Center, Divider, Stack } from '@mantine/core';

import { isSafeNext } from '@/lib/safe-redirect';

import { LoginButtons } from '../login/login-buttons';
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

        {/* 로그인 페이지와 대칭 — 카카오 간편가입도 같은 진입점에서 시작할 수 있게 한다.
            OAuth 신규 가입의 약관 동의는 기존 /auth/terms 온보딩 흐름이 받는다. */}
        <Divider label="또는" labelPosition="center" />
        <LoginButtons nextPath={nextPath} />
      </Stack>
    </Center>
  );
}

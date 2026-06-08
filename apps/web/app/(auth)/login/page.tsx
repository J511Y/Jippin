import { Anchor, Center, Divider, Stack, Text } from '@mantine/core';

import { isSafeNext } from '@/lib/safe-redirect';

import { LoginButtons } from './login-buttons';

/**
 * 간편가입 로그인 페이지 (CMP-557, CMP-564).
 *
 * - 정책: 자체 가입 / 아이디 찾기 / 비밀번호 찾기 UI 는 제공하지 않는다.
 *   소셜 OAuth provider 만 노출한다.
 * - `/login?next=/app/foo` 형태로 들어오면 `next` 경로를 OAuth start 의 `return_url` 로 전달한다.
 *   `next` 는 `isSafeNext` 로 SSR 단계에서 한 차례 검증한다. (CMP-582 / runbook §11 R11)
 * - 헤더(SiteShell)는 `(auth)/layout.tsx` 가 제공한다. 헤더 로고가 홈 진입점이므로
 *   카드 내부에는 브랜드 로고/홈 링크를 중복 노출하지 않는다.
 *
 * 주: 서버 컴포넌트이므로 내부 링크는 `component={Link}` 대신 네이티브 `<a>`(Anchor 기본)를 쓴다.
 */

export const metadata = {
  title: '로그인'
};

type LoginPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

function pickNext(value: string | string[] | undefined): string | null {
  const candidate = Array.isArray(value) ? value[0] : value;
  if (candidate === undefined || candidate === null) return null;
  return isSafeNext(candidate) ? candidate : null;
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const resolved = (await searchParams) ?? {};
  const nextPath = pickNext(resolved.next);

  return (
    <Center mih="68vh">
      <Stack gap="lg">
        <Stack gap={6} ta="center">
          <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
            소셜 계정으로 빠르게 시작하세요.
          </Text>
        </Stack>

        <LoginButtons nextPath={nextPath} />

        <Divider />

        <Text size="xs" c="dimmed" ta="center" style={{ wordBreak: 'keep-all' }}>
          계속 진행하면{' '}
          <Anchor href="/terms" size="xs" c="var(--jippin-brand-primary)">
            이용약관
          </Anchor>
          과{' '}
          <Anchor href="/privacy" size="xs" c="var(--jippin-brand-primary)">
            개인정보처리방침
          </Anchor>
          에 동의하는 것으로 간주됩니다.
        </Text>
      </Stack>
    </Center>
  );
}

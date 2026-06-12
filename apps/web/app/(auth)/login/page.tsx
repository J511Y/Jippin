import { Anchor, Center, Divider, Group, Stack, Text, Title } from '@mantine/core';

import { DEFAULT_NEXT, isSafeNext, resolveSafeNext } from '@/lib/safe-redirect';

import { EmailLoginForm } from './email-login-form';
import { LoginButtons } from './login-buttons';

/**
 * 로그인 페이지 (CMP-DIRECT — 이메일/비밀번호 + 카카오 간편 로그인).
 *
 * 정책 변경: 운영자 결정(2026-06-08)으로 이메일/비밀번호 가입·로그인이 허용된다. 비밀번호는
 * Supabase Auth(auth.users)가 단독 관리하며 우리 테이블에는 저장하지 않는다(AGENTS §4.7 #3
 * 의 "우리 테이블에 password 컬럼 금지"는 유지). 따라서 이전의 "자체 가입/아이디·비번 찾기
 * UI 없음" 문구는 본 결정으로 supersede 된다.
 *
 * 구성: 이메일+비밀번호 → '또는' divider → 카카오 간편 로그인. 하단에 회원가입/아이디 찾기/
 * 비밀번호 찾기 링크. `next` 는 SSR 에서 한 차례 검증한다.
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

function withNext(path: string, nextPath: string | null): string {
  if (!nextPath) return path;
  return `${path}?next=${encodeURIComponent(nextPath)}`;
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const resolved = (await searchParams) ?? {};
  const nextPath = pickNext(resolved.next);
  const safeNext = resolveSafeNext(nextPath, DEFAULT_NEXT);
  const registered = resolved.registered !== undefined;

  return (
    <Center mih="68vh" py="xl">
      <Stack gap="lg" w="100%" maw={400}>
        {/* 회원가입 페이지와 같은 타이틀 블록 — 필드부터 시작하지 않도록 한다. */}
        <Stack gap={4}>
          <Title order={1} fz="h2">
            로그인
          </Title>
          <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
            집핀 계정으로 상담 진행 상황을 확인하세요.
          </Text>
        </Stack>

        {registered ? (
          <Text size="sm" c="success.6" ta="center" style={{ wordBreak: 'keep-all' }}>
            가입이 완료되었습니다. 가입한 이메일과 비밀번호로 로그인해 주세요.
          </Text>
        ) : null}

        <EmailLoginForm nextPath={safeNext} />

        <Group justify="center" gap="xs">
          <Anchor href={withNext('/signup', nextPath)} size="sm" c="var(--jippin-brand-primary)">
            회원가입
          </Anchor>
          <Text size="sm" c="dimmed">
            ·
          </Text>
          <Anchor href="/find-email" size="sm" c="dimmed">
            아이디 찾기
          </Anchor>
          <Text size="sm" c="dimmed">
            ·
          </Text>
          <Anchor href="/find-password" size="sm" c="dimmed">
            비밀번호 찾기
          </Anchor>
        </Group>

        <Divider label="또는" labelPosition="center" />

        <LoginButtons nextPath={nextPath} />

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

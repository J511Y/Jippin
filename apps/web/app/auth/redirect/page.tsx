'use client';

import { Button, Card, Group, Loader, Stack, Text, Title } from '@mantine/core';
import Link from 'next/link';
import { Suspense, useEffect, useMemo, type ReactNode } from 'react';
import { useSearchParams } from 'next/navigation';

import { isSafeOAuthHandoff } from '@/lib/safe-redirect';
import { PageColumn } from '@/components/ui';

// /auth/redirect — OAuth 진입 단계 small client page (CMP-577 runbook §4.6, line ~1032).
//
// 흐름:
//   /auth/oauth/start (Web BFF) ──302──> /auth/redirect?to=<oauth_url>
//                                              │
//                                              │ (1) sessionStorage.jippin_oauth_in_progress='1' set
//                                              │ (2) window.location.assign(to)
//                                              ▼
//                                       <Supabase OAuth start URL>
//
// 본 page 의 책임은 `?to=` 파라미터가 open redirect 의 진입점이 되지 않도록 차단하는 것.
// SSOT 는 lib/safe-redirect.ts 의 `isSafeOAuthHandoff` — `to` 는 절대 URL 이며
// scheme + origin 이 NEXT_PUBLIC_SUPABASE_URL 와 정확히 일치해야 통과한다.
//
// 검증 실패 시:
//   - sessionStorage flag 를 set 하지 않는다.
//   - window.location.assign 을 호출하지 않는다.
//   - 사용자에게 명시적 에러 카드 + /login 복귀 링크를 노출한다.

type RedirectDecision =
  | { kind: 'invalid_config' }
  | { kind: 'invalid_target' }
  | { kind: 'navigate'; to: string };

function decide(to: string | null, supabaseUrl: string | undefined): RedirectDecision {
  if (!supabaseUrl) return { kind: 'invalid_config' };
  if (!isSafeOAuthHandoff(to, supabaseUrl)) return { kind: 'invalid_target' };
  return { kind: 'navigate', to: to as string };
}

// SiteShell(헤더) 없는 독립 레이아웃 — 폭은 인증 폼 표준(form 560)을 따르고 가로
// 패딩(px)을 자체 부담한다. 세 상태(설정 오류/차단/이동 중)가 같은 프레임을 공유한다.
function RedirectFrame({ children }: { children: ReactNode }) {
  return (
    <PageColumn width="form" px="md" py={48}>
      {children}
    </PageColumn>
  );
}

// 이동 중 안내 한 줄 — 본문 + 로더. 복귀 링크가 없는 순간적 화면이다.
function RedirectPending() {
  return (
    <RedirectFrame>
      <Group gap="xs">
        <Loader size="sm" color="jippin" />
        <Text size="sm" c="dimmed">
          소셜 로그인 화면으로 이동 중…
        </Text>
      </Group>
    </RedirectFrame>
  );
}

function RedirectRunner() {
  const sp = useSearchParams();
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;

  // Pure derivation — validation must NOT call setState from inside an effect (React 19 rule).
  const decision = useMemo<RedirectDecision>(
    () => decide(sp.get('to'), supabaseUrl),
    [sp, supabaseUrl],
  );

  useEffect(() => {
    if (decision.kind !== 'navigate') return;
    try {
      window.sessionStorage.setItem('jippin_oauth_in_progress', '1');
    } catch {
      // private mode / storage disabled — guard 가 set 되지 않더라도 OAuth 자체는 진행한다.
      // §4.1.1 SessionProvider 의 10분 stale 안전망이 정리 책임을 진다.
    }
    window.location.assign(decision.to);
  }, [decision]);

  if (decision.kind === 'invalid_config') {
    return (
      <RedirectFrame>
        <Stack gap="md">
          <Title order={1}>로그인 설정 오류</Title>
          <Card withBorder>
            <Stack gap="md" align="flex-start">
              <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
                OAuth 진입 URL 을 검증할 수 있는 설정이 없습니다. 운영자에게 문의해 주세요.
              </Text>
              <Button component={Link} href="/login" variant="light" color="jippin" size="md" mih={44}>
                로그인 화면으로 돌아가기
              </Button>
            </Stack>
          </Card>
        </Stack>
      </RedirectFrame>
    );
  }

  if (decision.kind === 'invalid_target') {
    return (
      <RedirectFrame>
        <Stack gap="md">
          <Title order={1}>잘못된 로그인 요청</Title>
          <Card withBorder>
            <Stack gap="md" align="flex-start">
              <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
                허용되지 않은 외부 주소로 이동을 시도했습니다. 안전을 위해 진행을 중단했어요.
              </Text>
              <Button component={Link} href="/login" variant="light" color="jippin" size="md" mih={44}>
                로그인 화면으로 돌아가기
              </Button>
            </Stack>
          </Card>
        </Stack>
      </RedirectFrame>
    );
  }

  return <RedirectPending />;
}

export default function AuthRedirectPage() {
  // useSearchParams 는 Suspense boundary 가 필요하다 (Next.js App Router).
  return (
    <Suspense fallback={<RedirectPending />}>
      <RedirectRunner />
    </Suspense>
  );
}

'use client';

import { Button, Stack, Text } from '@mantine/core';
import { useState } from 'react';

import { DEFAULT_NEXT, resolveSafeNext } from '@/lib/safe-redirect';

/**
 * 간편가입 OAuth 시작 버튼 (CMP-557, CMP-564).
 *
 * - 자체 가입/아이디 찾기/비밀번호 찾기 UI 는 정책상 존재하지 않는다.
 * - 흐름: 버튼 클릭 → Web BFF `GET /auth/oauth/start?provider=<id>&intent=signin&next=<path>` 로
 *   브라우저를 이동시킨다. BFF 는 Supabase PKCE cookie 를 보존한 뒤 provider authorization URL 로 302 한다.
 * - `next` 는 lib/safe-redirect 의 `isSafeNext` SSOT 를 거친 상대 경로만 전달한다.
 *
 * ★ intent 는 항상 `signin` 이다 (ADR-0003 — 자동 identity 병합 금지, linkIdentity 는 회원이
 *   명시적으로 호출하는 경로에서만 사용). 익명 세션에 카카오를 자동 link 하면 auth.users 에
 *   '익명' 유저로 남아 대시보드/탈퇴/연동해제가 깨지므로, "카카오로 시작하기" 는 언제나
 *   signInWithOAuth 로 first-class 카카오 계정을 생성/로그인한다.
 */

const PROVIDERS = [{ id: 'kakao', label: '카카오로 시작하기' }] as const;

/**
 * 카카오 공식 심볼(채팅 말풍선). 디자인 가이드(developers.kakao.com)상 노란 버튼 위
 * 검은색(#191919) 심볼로 사용한다. 모양/비율/색은 임의 변경하지 않는다.
 */
function KakaoIcon({ size = 18 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 18 18"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M9 0.5C4.029 0.5 0 3.694 0 7.628c0 2.504 1.632 4.706 4.107 5.985-.182.661-.659 2.402-.754 2.775-.118.464.17.458.358.333.147-.097 2.346-1.593 3.299-2.241.643.094 1.305.143 1.99.143 4.971 0 9-3.194 9-7.628C18 3.694 13.971 0.5 9 0.5z"
        fill="#191919"
      />
    </svg>
  );
}

type ProviderId = (typeof PROVIDERS)[number]['id'];

type LoginButtonsProps = {
  nextPath: string | null;
};

function safeNextPath(nextPath: string | null): string | null {
  return resolveSafeNext(nextPath, DEFAULT_NEXT);
}

export function LoginButtons({ nextPath }: LoginButtonsProps) {
  const [pendingProvider, setPendingProvider] = useState<ProviderId | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  function startOAuth(provider: ProviderId) {
    setPendingProvider(provider);
    setErrorMessage(null);

    try {
      const url = new URL('/auth/oauth/start', window.location.origin);
      url.searchParams.set('provider', provider);
      url.searchParams.set('intent', 'signin');
      const next = safeNextPath(nextPath);
      if (next) {
        url.searchParams.set('next', next);
      }
      window.location.assign(url.toString());
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : '로그인을 시작하지 못했습니다.'
      );
      setPendingProvider(null);
    }
  }

  return (
    <Stack gap="sm">
      {PROVIDERS.map((provider) => (
        <Button
          key={provider.id}
          type="button"
          onClick={() => startOAuth(provider.id)}
          loading={pendingProvider === provider.id}
          disabled={pendingProvider !== null && pendingProvider !== provider.id}
          size="lg"
          radius="md"
          fullWidth
          leftSection={<KakaoIcon size={18} />}
          style={{ backgroundColor: '#FEE500', color: '#191919' }}
        >
          {provider.label}
        </Button>
      ))}
      {errorMessage ? (
        <Text size="sm" c="red" ta="center">
          {errorMessage}
        </Text>
      ) : null}
    </Stack>
  );
}

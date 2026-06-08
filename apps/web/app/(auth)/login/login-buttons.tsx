'use client';

import { Button, Stack, Text } from '@mantine/core';
import { useState } from 'react';

import { DEFAULT_NEXT, resolveSafeNext } from '@/lib/safe-redirect';
import { createClient } from '@/lib/supabase/client';

/**
 * 간편가입 OAuth 시작 버튼 (CMP-557, CMP-564).
 *
 * - 자체 가입/아이디 찾기/비밀번호 찾기 UI 는 정책상 존재하지 않는다.
 * - 흐름: 버튼 클릭 → Web BFF `GET /auth/oauth/start?provider=<id>&intent=<signin|link>&next=<path>` 로
 *   브라우저를 이동시킨다. BFF 는 Supabase PKCE cookie 를 보존한 뒤 provider authorization URL 로 302 한다.
 * - `next` 는 lib/safe-redirect 의 `isSafeNext` SSOT 를 거친 상대 경로만 전달한다.
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
type OAuthIntent = 'signin' | 'link';

type LoginButtonsProps = {
  nextPath: string | null;
};

function safeNextPath(nextPath: string | null): string | null {
  return resolveSafeNext(nextPath, DEFAULT_NEXT);
}

async function resolveOAuthIntent(): Promise<OAuthIntent> {
  const supabase = createClient();
  const { data } = await supabase.auth.getSession();
  const user = data.session?.user as
    | {
        is_anonymous?: boolean;
        app_metadata?: {
          provider?: string;
          providers?: string[];
        };
      }
    | undefined;
  if (user?.is_anonymous === true) {
    return 'link';
  }
  const providers = user?.app_metadata?.providers ?? [];
  if (
    user?.app_metadata?.provider === 'anonymous'
    && providers.every((provider) => provider === 'anonymous')
  ) {
    return 'link';
  }
  return 'signin';
}

export function LoginButtons({ nextPath }: LoginButtonsProps) {
  const [pendingProvider, setPendingProvider] = useState<ProviderId | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function startOAuth(provider: ProviderId) {
    setPendingProvider(provider);
    setErrorMessage(null);

    try {
      const url = new URL('/auth/oauth/start', window.location.origin);
      url.searchParams.set('provider', provider);
      url.searchParams.set('intent', await resolveOAuthIntent());
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
          onClick={() => void startOAuth(provider.id)}
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

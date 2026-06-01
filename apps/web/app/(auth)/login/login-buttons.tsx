'use client';

import { useState } from 'react';

import { getOrCreateAnonymousUserId } from '@/lib/anonymous-user';
import { DEFAULT_NEXT, resolveSafeNext } from '@/lib/safe-redirect';

/**
 * 간편가입 OAuth 시작 버튼 (CMP-557, CMP-564).
 *
 * - 자체 가입/아이디 찾기/비밀번호 찾기 UI 는 정책상 존재하지 않는다.
 * - 흐름: 버튼 클릭 → Web BFF `GET /auth/oauth/start?provider=<id>&intent=signin&next=<path>` 로
 *   브라우저를 이동시킨다. BFF 는 Supabase PKCE cookie 를 보존한 뒤 provider authorization URL 로 302 한다.
 * - `next` 는 lib/safe-redirect 의 `isSafeNext` SSOT 를 거친 상대 경로만 전달한다.
 */

const PROVIDERS = [
  { id: 'kakao', label: '카카오로 시작하기' },
  { id: 'naver', label: '네이버로 시작하기' },
  { id: 'google', label: 'Google 로 시작하기' }
] as const;

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

  async function startOAuth(provider: ProviderId) {
    setPendingProvider(provider);
    setErrorMessage(null);

    try {
      const url = new URL('/auth/oauth/start', window.location.origin);
      url.searchParams.set('provider', provider);
      url.searchParams.set('intent', 'signin');
      url.searchParams.set('anonymous_user_id', await getOrCreateAnonymousUserId());
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
    <>
      <ul className="grid gap-2">
        {PROVIDERS.map((provider) => (
          <li key={provider.id}>
            <button
              type="button"
              onClick={() => void startOAuth(provider.id)}
              disabled={pendingProvider !== null}
              className="block w-full rounded-md border border-slate-300 px-4 py-3 text-center text-sm font-medium hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {pendingProvider === provider.id ? '로그인 준비 중...' : provider.label}
            </button>
          </li>
        ))}
      </ul>
      {errorMessage ? <p className="text-sm text-red-600">{errorMessage}</p> : null}
    </>
  );
}

'use client';

import { useState } from 'react';

const ANON_USER_ID_KEY = 'jippin_anonymous_user_id';
const ANON_USER_ID_HEADER = 'x-jippin-anon-id';

const PROVIDERS = [
  { id: 'kakao', label: '카카오로 로그인' },
  { id: 'google', label: 'Google 로 로그인' },
  { id: 'naver', label: '네이버로 로그인' }
] as const;

type ProviderId = (typeof PROVIDERS)[number]['id'];

type OAuthStartResponse = {
  authorize_url?: string;
};

function getOrCreateAnonymousUserId(): string {
  const stored = window.localStorage.getItem(ANON_USER_ID_KEY);
  if (stored) {
    return stored;
  }

  if (!window.crypto?.randomUUID) {
    throw new Error('이 브라우저에서는 익명 세션을 만들 수 없습니다.');
  }

  const generated = window.crypto.randomUUID();
  window.localStorage.setItem(ANON_USER_ID_KEY, generated);
  return generated;
}

type LoginButtonsProps = {
  apiBase: string;
};

export function LoginButtons({ apiBase }: LoginButtonsProps) {
  const [pendingProvider, setPendingProvider] = useState<ProviderId | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function startOAuth(provider: ProviderId) {
    setPendingProvider(provider);
    setErrorMessage(null);

    try {
      const anonymousUserId = getOrCreateAnonymousUserId();
      const response = await fetch(`${apiBase}/auth/${provider}/start`, {
        method: 'POST',
        headers: {
          [ANON_USER_ID_HEADER]: anonymousUserId
        }
      });

      if (!response.ok) {
        throw new Error('로그인 시작 요청에 실패했습니다.');
      }

      const data = (await response.json()) as OAuthStartResponse;
      if (!data.authorize_url) {
        throw new Error('로그인 이동 주소를 받지 못했습니다.');
      }

      window.location.assign(data.authorize_url);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '로그인을 시작하지 못했습니다.');
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

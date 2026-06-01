'use client';

import { useState } from 'react';

import { apiBaseUrl } from '@/lib/api-base-url';
import { getOrCreateAnonymousUserId } from '@/lib/anonymous-user';
import { ALLOWED_PROVIDERS, type AllowedProvider } from '@/lib/oauth-providers';

/**
 * 간편가입 OAuth 시작 버튼 (CMP-557, CMP-564, CMP-584).
 *
 * - 자체 가입/아이디 찾기/비밀번호 찾기 UI 는 정책상 존재하지 않는다 (runbook §4.x).
 * - provider 화이트리스트 SSOT 는 `@/lib/oauth-providers` 의 `ALLOWED_PROVIDERS`.
 * - 흐름: 버튼 클릭 → `GET /auth/{provider}/start?return_url=<absolute>&anonymous_user_id=<id>` 로
 *   브라우저를 이동시킨다. 백엔드는 302 로 provider authorization URL 까지 곧장 보낸다.
 * - return_url 은 `/login?next=...` 로 들어온 경로를 절대 URL 로 변환해 그대로 전달한다.
 */

const PROVIDER_LABELS: Record<AllowedProvider, string> = {
  kakao: '카카오로 시작하기',
  naver: '네이버로 시작하기',
  google: 'Google 로 시작하기'
};

const UI_ORDER: readonly AllowedProvider[] = ['kakao', 'naver', 'google'];

const PROVIDERS = UI_ORDER.filter((id) =>
  (ALLOWED_PROVIDERS as readonly string[]).includes(id)
).map((id) => ({
  id,
  label: PROVIDER_LABELS[id]
})) satisfies ReadonlyArray<{ id: AllowedProvider; label: string }>;

type ProviderId = AllowedProvider;

type LoginButtonsProps = {
  nextPath: string | null;
};

function resolveReturnUrl(nextPath: string | null): string {
  const origin = window.location.origin;
  if (!nextPath || !nextPath.startsWith('/')) {
    return `${origin}/`;
  }
  return `${origin}${nextPath}`;
}

export function LoginButtons({ nextPath }: LoginButtonsProps) {
  const [pendingProvider, setPendingProvider] = useState<ProviderId | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function startOAuth(provider: ProviderId) {
    setPendingProvider(provider);
    setErrorMessage(null);

    try {
      const anonymousUserId = await getOrCreateAnonymousUserId();
      const returnUrl = resolveReturnUrl(nextPath);
      const url = new URL(`${apiBaseUrl()}/auth/${provider}/start`);
      url.searchParams.set('return_url', returnUrl);
      url.searchParams.set('anonymous_user_id', anonymousUserId);
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

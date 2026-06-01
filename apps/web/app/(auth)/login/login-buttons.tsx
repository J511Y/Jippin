'use client';

import { useState } from 'react';

import { getOrCreateAnonymousUserId } from '@/lib/anonymous-user';
import { ALLOWED_PROVIDERS, type AllowedProvider } from '@/lib/oauth-providers';

/**
 * 간편가입 OAuth 시작 버튼 (CMP-557, CMP-564, CMP-584).
 *
 * - 자체 가입/아이디 찾기/비밀번호 찾기 UI 는 정책상 존재하지 않는다 (runbook §4.x).
 * - provider 화이트리스트 SSOT 는 `@/lib/oauth-providers` 의 `ALLOWED_PROVIDERS`.
 * - **흐름 (round-5 봉인):** 버튼 클릭 → same-origin `/auth/oauth/start?provider=<id>&return_url=...&anonymous_user_id=...`
 *   BFF (`apps/web/app/auth/oauth/start/route.ts`) 로 navigation. BFF 가 화이트리스트
 *   가드 + `publicApiBaseUrl()` (`API_PUBLIC_BASE_URL` SSOT) 를 적용한 뒤 backend 로
 *   302. 클라이언트 코드는 `NEXT_PUBLIC_API_BASE_URL` 를 직접 사용하지 않으므로
 *   compose 의 `http://api:8000` 같은 server-only host 가 브라우저 코드에 bake 되어도
 *   사용자 navigation 에 영향이 없다.
 * - return_url 은 `/login?next=...` 로 들어온 경로를 절대 URL 로 변환해 그대로 BFF 에 전달한다.
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
      const url = new URL('/auth/oauth/start', window.location.origin);
      url.searchParams.set('provider', provider);
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

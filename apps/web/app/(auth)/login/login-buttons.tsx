'use client';

import { useState } from 'react';

import { apiBaseUrl } from '@/lib/api-base-url';
import { getOrCreateAnonymousUserId } from '@/lib/anonymous-user';
import { DEFAULT_NEXT, resolveSafeNext } from '@/lib/safe-redirect';

/**
 * 간편가입 OAuth 시작 버튼 (CMP-557, CMP-564).
 *
 * - 자체 가입/아이디 찾기/비밀번호 찾기 UI 는 정책상 존재하지 않는다.
 * - 흐름: 버튼 클릭 → `GET /auth/{provider}/start?return_url=<absolute>&anonymous_user_id=<id>` 로
 *   브라우저를 이동시킨다. 백엔드는 302 로 provider authorization URL 까지 곧장 보낸다.
 * - return_url 은 `/login?next=...` 로 들어온 경로를 절대 URL 로 변환해 그대로 전달한다.
 *   `next` 는 lib/safe-redirect 의 `isSafeNext` SSOT 를 거쳐 open-redirect (`//evil.com` 등) 를
 *   원천 차단한 뒤 origin 에 붙인다. (CMP-582 / runbook §11 R11)
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

function resolveReturnUrl(nextPath: string | null): string {
  const origin = window.location.origin;
  // `nextPath` 가 isSafeNext 를 통과한 경우에만 동일 origin 의 absolute URL 로 끌어올린다.
  // 실패하면 DEFAULT_NEXT 로 fallback — `//evil.com` 같은 schema-relative 값이 그대로
  // `<origin>//evil.com` 으로 합쳐져 외부로 빠지는 사고를 차단한다.
  const safeNext = resolveSafeNext(nextPath, DEFAULT_NEXT);
  return `${origin}${safeNext}`;
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

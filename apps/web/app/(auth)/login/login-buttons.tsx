'use client';

import { useState } from 'react';

import { getOrCreateAnonymousUserId } from '@/lib/anonymous-user';
import { isSafeNext } from '@/lib/safe-redirect';
import { createBrowserSupabaseClient } from '@/lib/supabase/browser';
import type { UiProvider } from '@/lib/supabase/providers';

import { IdentityAlreadyExistsModal } from './identity-already-exists-modal';

/**
 * 간편가입 OAuth 시작 버튼 (CMP-557, CMP-564).
 *
 * - 자체 가입/아이디 찾기/비밀번호 찾기 UI 는 정책상 존재하지 않는다.
 * - 흐름: 버튼 클릭 → Supabase 현재 user 확인 → `/auth/oauth/start` BFF 로 이동.
 * - Phase 1 동안 기존 anonymous-user dual-write 는 유지한다.
 */

const PROVIDERS = [
  { id: 'kakao', label: '카카오로 시작하기' },
  { id: 'naver', label: '네이버로 시작하기' },
  { id: 'google', label: 'Google 로 시작하기' }
] as const satisfies readonly { id: UiProvider; label: string }[];

type LoginButtonsProps = {
  nextPath: string | null;
};

function resolveNext(nextPath: string | null): string {
  return nextPath && isSafeNext(nextPath) ? nextPath : '/';
}

function isAnonymousUser(user: { is_anonymous?: boolean; app_metadata?: unknown } | null): boolean {
  if (!user) return false;
  if (user.is_anonymous === true) return true;
  const metadata = user.app_metadata;
  return (
    typeof metadata === 'object' &&
    metadata !== null &&
    'provider' in metadata &&
    metadata.provider === 'anonymous'
  );
}

export function LoginButtons({ nextPath }: LoginButtonsProps) {
  const [pendingProvider, setPendingProvider] = useState<UiProvider | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function startOAuth(provider: UiProvider) {
    setPendingProvider(provider);
    setErrorMessage(null);

    try {
      const anonymousUserId = await getOrCreateAnonymousUserId();
      const supabase = createBrowserSupabaseClient();
      const {
        data: { user },
      } = await supabase.auth.getUser();
      const intent = isAnonymousUser(user) ? 'link' : 'signin';

      try {
        window.sessionStorage.setItem('jippin_oauth_in_progress', '1');
      } catch {
        // OAuth can continue without the guard in storage-disabled browsers.
      }

      const url = new URL('/auth/oauth/start', window.location.origin);
      url.searchParams.set('provider', provider);
      url.searchParams.set('intent', intent);
      url.searchParams.set('next', resolveNext(nextPath));
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
      <IdentityAlreadyExistsModal open={false} nextPath={nextPath} />
    </>
  );
}

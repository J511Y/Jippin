'use client';

import { useCallback, useEffect, useState } from 'react';

import { apiBaseUrl } from '@/lib/api-base-url';
import {
  ANONYMOUS_USER_ID_STORAGE_KEY,
  getOrCreateAnonymousUserId,
  readStoredAnonymousUserId
} from '@/lib/anonymous-user';

/**
 * `/auth/test` 의 클라이언트 측 본체.
 *
 * - 페이지 진입 시: anonymous ID 발급 + `/auth/me` 조회.
 * - 모든 백엔드 호출은 `credentials: 'include'` 로 `jippin_session` 쿠키를 동반한다.
 * - 약관 동의 폼은 `/auth/me` 응답의 `missing_required_terms` 를 기반으로 동적으로 렌더링한다.
 */

const PROVIDERS = ['kakao'] as const;
type Provider = (typeof PROVIDERS)[number];

type AuthMeUser = {
  id: string;
  email?: string | null;
  display_name?: string | null;
  profile_image_url?: string | null;
  role?: string | null;
};

type AuthMeResponse = {
  user?: AuthMeUser | null;
  providers?: string[];
  signup_complete?: boolean;
  missing_required_terms?: string[];
};

type FetchState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'authenticated'; data: AuthMeResponse }
  | { kind: 'anonymous' }
  | { kind: 'error'; message: string };

function buildOAuthUrl(provider: Provider, anonymousUserId: string | null): string {
  const url = new URL(`${apiBaseUrl()}/auth/${provider}/start`);
  url.searchParams.set('return_url', `${window.location.origin}/auth/test`);
  if (anonymousUserId) {
    url.searchParams.set('anonymous_user_id', anonymousUserId);
  }
  return url.toString();
}

export function AuthTestPanel() {
  const [anonymousUserId, setAnonymousUserId] = useState<string | null>(null);
  const [authMe, setAuthMe] = useState<FetchState>({ kind: 'idle' });
  const [statusLine, setStatusLine] = useState<string | null>(null);

  const refreshAuthMe = useCallback(async () => {
    setAuthMe({ kind: 'loading' });
    try {
      const response = await fetch(`${apiBaseUrl()}/auth/me`, {
        method: 'GET',
        credentials: 'include',
        headers: { accept: 'application/json' }
      });
      if (response.status === 401) {
        setAuthMe({ kind: 'anonymous' });
        return;
      }
      if (!response.ok) {
        setAuthMe({
          kind: 'error',
          message: `/auth/me 호출 실패 (${response.status})`
        });
        return;
      }
      const data = (await response.json()) as AuthMeResponse;
      setAuthMe({ kind: 'authenticated', data });
    } catch (error) {
      setAuthMe({
        kind: 'error',
        message: error instanceof Error ? error.message : '/auth/me 호출 실패'
      });
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const id = await getOrCreateAnonymousUserId();
        if (!cancelled) setAnonymousUserId(id);
      } catch (error) {
        if (!cancelled) {
          setStatusLine(
            error instanceof Error
              ? `anonymous-user 발급 실패: ${error.message}`
              : 'anonymous-user 발급 실패'
          );
          setAnonymousUserId(readStoredAnonymousUserId());
        }
      }
      void refreshAuthMe();
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshAuthMe]);

  async function handleLogout() {
    setStatusLine(null);
    try {
      const response = await fetch(`${apiBaseUrl()}/auth/logout`, {
        method: 'POST',
        credentials: 'include'
      });
      setStatusLine(`logout 응답: ${response.status}`);
      await refreshAuthMe();
    } catch (error) {
      setStatusLine(
        error instanceof Error ? `로그아웃 실패: ${error.message}` : '로그아웃 실패'
      );
    }
  }

  async function handleLinkProvider(provider: Provider) {
    setStatusLine(null);
    try {
      const url = new URL(`${apiBaseUrl()}/auth/sso-accounts/${provider}/link`);
      url.searchParams.set('return_url', `${window.location.origin}/auth/test`);
      url.searchParams.set('mode', 'json');
      const response = await fetch(url.toString(), {
        method: 'POST',
        credentials: 'include',
        headers: { accept: 'application/json' }
      });
      if (!response.ok) {
        setStatusLine(`provider link 실패 (${response.status})`);
        return;
      }
      const data = (await response.json()) as { authorization_url?: string };
      if (!data.authorization_url) {
        setStatusLine('provider link 응답에 authorization_url 이 없습니다.');
        return;
      }
      window.location.assign(data.authorization_url);
    } catch (error) {
      setStatusLine(
        error instanceof Error ? error.message : 'provider link 호출 실패'
      );
    }
  }

  function handleStartProvider(provider: Provider) {
    window.location.assign(buildOAuthUrl(provider, anonymousUserId));
  }

  return (
    <section className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-12">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">인증 흐름 검증 (`/auth/test`)</h1>
        <p className="text-sm text-slate-600">
          CMP-557 통합 검증용. 비회원 ID, OAuth start, /auth/me, provider link, 약관 동의,
          로그아웃을 한 화면에서 확인합니다.
        </p>
        {statusLine ? (
          <p className="rounded bg-slate-50 px-3 py-2 text-xs text-slate-700">{statusLine}</p>
        ) : null}
      </header>

      <AnonymousIdSection
        anonymousUserId={anonymousUserId}
        onReissue={async () => {
          try {
            const id = await getOrCreateAnonymousUserId();
            setAnonymousUserId(id);
          } catch (error) {
            setStatusLine(
              error instanceof Error ? error.message : 'anonymous-user 재요청 실패'
            );
          }
        }}
      />

      <ProviderStartSection onStart={handleStartProvider} />

      <AuthMeSection
        state={authMe}
        onRefresh={() => void refreshAuthMe()}
        onLogout={() => void handleLogout()}
        onLinkProvider={handleLinkProvider}
        onTermsSubmitted={() => void refreshAuthMe()}
      />
    </section>
  );
}

function AnonymousIdSection({
  anonymousUserId,
  onReissue
}: {
  anonymousUserId: string | null;
  onReissue: () => Promise<void>;
}) {
  return (
    <section className="grid gap-3 rounded-md border border-slate-200 p-4">
      <h2 className="text-base font-semibold">1. 비회원 ID</h2>
      <p className="text-xs text-slate-600">
        키: <code>{ANONYMOUS_USER_ID_STORAGE_KEY}</code>. 새로고침 후에도 동일 ID 가 유지되어야 합니다.
      </p>
      <code className="break-all rounded bg-slate-50 px-3 py-2 text-xs">
        {anonymousUserId ?? '(아직 발급되지 않음)'}
      </code>
      <button
        type="button"
        onClick={() => void onReissue()}
        className="self-start rounded border border-slate-300 px-3 py-1.5 text-xs hover:bg-slate-50"
      >
        anonymous-users API 재호출
      </button>
    </section>
  );
}

function ProviderStartSection({
  onStart
}: {
  onStart: (provider: Provider) => void;
}) {
  return (
    <section className="grid gap-3 rounded-md border border-slate-200 p-4">
      <h2 className="text-base font-semibold">2. OAuth start</h2>
      <p className="text-xs text-slate-600">
        각 버튼은 <code>GET /auth/{'{provider}'}/start</code> 로 직접 이동합니다. 백엔드가
        provider authorization URL 로 302 합니다.
      </p>
      <ul className="grid gap-2 sm:grid-cols-3">
        {PROVIDERS.map((provider) => (
          <li key={provider}>
            <button
              type="button"
              onClick={() => onStart(provider)}
              className="block w-full rounded border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50"
            >
              {provider} start
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function AuthMeSection({
  state,
  onRefresh,
  onLogout,
  onLinkProvider,
  onTermsSubmitted
}: {
  state: FetchState;
  onRefresh: () => void;
  onLogout: () => void;
  onLinkProvider: (provider: Provider) => Promise<void>;
  onTermsSubmitted: () => void;
}) {
  return (
    <section className="grid gap-3 rounded-md border border-slate-200 p-4">
      <header className="flex items-center justify-between gap-2">
        <h2 className="text-base font-semibold">3. 세션 상태 (/auth/me)</h2>
        <button
          type="button"
          onClick={onRefresh}
          className="rounded border border-slate-300 px-3 py-1 text-xs hover:bg-slate-50"
        >
          새로고침
        </button>
      </header>
      <AuthMeBody state={state} />
      {state.kind === 'authenticated' ? (
        <AuthenticatedExtras
          data={state.data}
          onLogout={onLogout}
          onLinkProvider={onLinkProvider}
          onTermsSubmitted={onTermsSubmitted}
        />
      ) : null}
    </section>
  );
}

function AuthMeBody({ state }: { state: FetchState }) {
  if (state.kind === 'loading') {
    return <p className="text-xs text-slate-500">로딩 중...</p>;
  }
  if (state.kind === 'anonymous') {
    return <p className="text-xs text-slate-500">비로그인 상태 (401)</p>;
  }
  if (state.kind === 'error') {
    return <p className="text-xs text-red-600">{state.message}</p>;
  }
  if (state.kind === 'authenticated') {
    return (
      <pre className="overflow-x-auto rounded bg-slate-900 p-3 text-xs text-slate-100">
        {JSON.stringify(state.data, null, 2)}
      </pre>
    );
  }
  return null;
}

function AuthenticatedExtras({
  data,
  onLogout,
  onLinkProvider,
  onTermsSubmitted
}: {
  data: AuthMeResponse;
  onLogout: () => void;
  onLinkProvider: (provider: Provider) => Promise<void>;
  onTermsSubmitted: () => void;
}) {
  const linkedProviders = new Set(data.providers ?? []);
  const missingTerms = data.missing_required_terms ?? [];
  return (
    <div className="grid gap-4 border-t border-slate-200 pt-3">
      <div className="grid gap-2">
        <h3 className="text-sm font-semibold">다른 provider 연결</h3>
        <ul className="grid gap-2 sm:grid-cols-3">
          {PROVIDERS.map((provider) => {
            const linked = linkedProviders.has(provider);
            return (
              <li key={provider}>
                <button
                  type="button"
                  disabled={linked}
                  onClick={() => void onLinkProvider(provider)}
                  className="block w-full rounded border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {linked ? `${provider} 연결됨` : `${provider} 연결`}
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      {missingTerms.length > 0 ? (
        <TermsAcceptForm missingTerms={missingTerms} onSubmitted={onTermsSubmitted} />
      ) : (
        <p className="text-xs text-slate-500">필수 약관 동의 미충족 없음.</p>
      )}

      <div>
        <button
          type="button"
          onClick={onLogout}
          className="rounded border border-red-300 px-3 py-2 text-sm text-red-700 hover:bg-red-50"
        >
          로그아웃
        </button>
      </div>
    </div>
  );
}

function TermsAcceptForm({
  missingTerms,
  onSubmitted
}: {
  missingTerms: string[];
  onSubmitted: () => void;
}) {
  const [agreed, setAgreed] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit() {
    setError(null);
    setSubmitting(true);
    try {
      const response = await fetch(`${apiBaseUrl()}/auth/terms/accept`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          consents: missingTerms.map((termId) => ({
            term_id: termId,
            agreed: Boolean(agreed[termId])
          }))
        })
      });
      if (!response.ok) {
        setError(`/auth/terms/accept 실패 (${response.status})`);
        return;
      }
      onSubmitted();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '약관 동의 실패');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      className="grid gap-2 rounded border border-amber-300 bg-amber-50 p-3"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <h3 className="text-sm font-semibold">내부 약관 동의</h3>
      <ul className="grid gap-1 text-xs">
        {missingTerms.map((termId) => (
          <li key={termId}>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={Boolean(agreed[termId])}
                onChange={(event) =>
                  setAgreed((prev) => ({ ...prev, [termId]: event.target.checked }))
                }
              />
              term_id {termId}
            </label>
          </li>
        ))}
      </ul>
      {error ? <p className="text-xs text-red-600">{error}</p> : null}
      <button
        type="submit"
        disabled={submitting}
        className="self-start rounded border border-amber-500 px-3 py-1.5 text-xs hover:bg-amber-100 disabled:opacity-60"
      >
        {submitting ? '제출 중...' : '동의 후 제출'}
      </button>
    </form>
  );
}

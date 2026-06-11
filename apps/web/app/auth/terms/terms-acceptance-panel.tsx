'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';

import { apiBaseUrl } from '@/lib/api-base-url';

type AuthMeResponse = {
  signup_complete?: boolean;
  missing_required_terms?: string[];
};

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; missingTerms: string[] }
  | { kind: 'unauthenticated' }
  | { kind: 'error'; message: string };

type TermsAcceptancePanelProps = {
  nextPath: string;
};

// 서버(missing_required_terms)가 내려주는 term_id 의 사용자 노출 문구.
// age_over_14 는 법정 자기확인(개인정보보호법)이라 OAuth 가입 경로에서도 항상 필수이며
// signup form(apps/web/app/(auth)/signup/signup-form.tsx)과 동일한 문구를 쓴다.
export const TERM_LABELS: Record<string, string> = {
  service_terms: '이용약관에 동의합니다. (필수)',
  privacy_policy: '개인정보처리방침에 동의합니다. (필수)',
  age_over_14: '만 14세 이상입니다. (필수)'
};

export function termLabel(termId: string): string {
  return TERM_LABELS[termId] ?? termId;
}

export function TermsAcceptancePanel({ nextPath }: TermsAcceptancePanelProps) {
  const router = useRouter();
  const [state, setState] = useState<LoadState>({ kind: 'loading' });
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const readTermsState = useCallback(async (): Promise<LoadState | { kind: 'complete' }> => {
    try {
      const response = await fetch(`${apiBaseUrl()}/auth/me`, {
        method: 'GET',
        credentials: 'include',
        headers: { accept: 'application/json' }
      });
      if (response.status === 401) {
        return { kind: 'unauthenticated' };
      }
      if (!response.ok) {
        return { kind: 'error', message: `세션 확인 실패 (${response.status})` };
      }
      const data = (await response.json()) as AuthMeResponse;
      const missingTerms = data.missing_required_terms ?? [];
      if (data.signup_complete !== false && missingTerms.length === 0) {
        return { kind: 'complete' };
      }
      return { kind: 'ready', missingTerms };
    } catch (error) {
      return {
        kind: 'error',
        message: error instanceof Error ? error.message : '세션 확인 실패'
      };
    }
  }, []);

  const applyTermsState = useCallback((nextState: LoadState | { kind: 'complete' }) => {
    if (nextState.kind === 'complete') {
      router.replace(nextPath);
      return;
    }
    if (nextState.kind === 'ready') {
      setChecked(Object.fromEntries(nextState.missingTerms.map((termId) => [termId, false])));
    }
    setState(nextState);
  }, [nextPath, router]);

  const loadTerms = useCallback(async () => {
    setSubmitError(null);
    applyTermsState(await readTermsState());
  }, [applyTermsState, readTermsState]);

  useEffect(() => {
    let cancelled = false;
    void readTermsState().then((nextState) => {
      if (!cancelled) {
        applyTermsState(nextState);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [applyTermsState, readTermsState]);

  const allChecked = useMemo(() => {
    return (
      state.kind === 'ready'
      && state.missingTerms.length > 0
      && state.missingTerms.every((termId) => checked[termId])
    );
  }, [checked, state]);

  async function submitTerms() {
    if (state.kind !== 'ready' || !allChecked) {
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const response = await fetch(`${apiBaseUrl()}/auth/terms/accept`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          consents: state.missingTerms.map((termId) => ({
            term_id: termId,
            agreed: true
          }))
        })
      });
      if (!response.ok) {
        setSubmitError(`약관 동의 실패 (${response.status})`);
        return;
      }
      router.replace(nextPath);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : '약관 동의 실패');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="mx-auto flex max-w-lg flex-col gap-6 px-6 py-16">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">필수 약관 동의</h1>
        <p className="text-sm text-slate-600">
          계정 생성을 완료하려면 아래 필수 약관에 동의해 주세요.
        </p>
      </header>

      {state.kind === 'loading' ? <p className="text-sm text-slate-500">확인 중...</p> : null}

      {state.kind === 'unauthenticated' ? (
        <div className="grid gap-3 rounded-md border border-slate-200 p-4">
          <p className="text-sm text-slate-700">로그인 세션이 만료되었습니다.</p>
          <button
            type="button"
            onClick={() => router.replace(`/login?next=${encodeURIComponent(nextPath)}`)}
            className="self-start rounded-md border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-50"
          >
            다시 로그인
          </button>
        </div>
      ) : null}

      {state.kind === 'error' ? (
        <div className="grid gap-3 rounded-md border border-red-200 bg-red-50 p-4">
          <p className="text-sm text-red-700">{state.message}</p>
          <button
            type="button"
            onClick={() => {
              setState({ kind: 'loading' });
              void loadTerms();
            }}
            className="self-start rounded-md border border-red-300 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-100"
          >
            다시 시도
          </button>
        </div>
      ) : null}

      {state.kind === 'ready' ? (
        <form
          className="grid gap-4 rounded-md border border-slate-200 p-4"
          onSubmit={(event) => {
            event.preventDefault();
            void submitTerms();
          }}
        >
          <ul className="grid gap-3">
            {state.missingTerms.map((termId) => (
              <li key={termId}>
                <label className="flex items-center gap-3 text-sm text-slate-800">
                  <input
                    type="checkbox"
                    checked={Boolean(checked[termId])}
                    onChange={(event) =>
                      setChecked((current) => ({
                        ...current,
                        [termId]: event.target.checked
                      }))
                    }
                    className="size-4 rounded border-slate-300"
                  />
                  <span>{termLabel(termId)}</span>
                </label>
              </li>
            ))}
          </ul>
          {submitError ? <p className="text-sm text-red-600">{submitError}</p> : null}
          <button
            type="submit"
            disabled={!allChecked || submitting}
            className="rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? '저장 중...' : '동의하고 계속'}
          </button>
        </form>
      ) : null}
    </section>
  );
}

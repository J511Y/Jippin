'use client';

import { type FormEvent, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';

import { apiBaseUrl } from '@/lib/api-base-url';
import { isSafeNext } from '@/lib/safe-redirect';
import { createBrowserSupabaseClient } from '@/lib/supabase/browser';

type TermsGateProps = {
  nextPath: string | null;
};

const REQUIRED_TERMS = [
  { id: 'service_terms', label: '서비스 이용약관에 동의합니다' },
  { id: 'privacy_policy', label: '개인정보 처리방침에 동의합니다' },
] as const;

function resolveNext(value: string | null): string {
  return value && isSafeNext(value) ? value : '/auth/success';
}

function termsAcceptEnabled(): boolean {
  return process.env.NEXT_PUBLIC_AUTH_TERMS_ACCEPT_ENABLED === 'true';
}

function clearTermsPendingCookie(): void {
  document.cookie = 'jippin_terms_pending=; Max-Age=0; Path=/; SameSite=Lax';
}

export function TermsGate({ nextPath }: TermsGateProps) {
  const router = useRouter();
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const safeNext = useMemo(() => resolveNext(nextPath), [nextPath]);
  const allChecked = REQUIRED_TERMS.every((term) => checked[term.id]);
  const canSubmitTerms = termsAcceptEnabled();

  async function submitTerms() {
    setError(null);
    setSubmitting(true);
    try {
      const {
        data: { session },
      } = await createBrowserSupabaseClient().auth.getSession();
      if (!session?.access_token) {
        setError('로그인 세션을 확인할 수 없습니다. 다시 로그인해 주세요.');
        return;
      }

      const response = await fetch(`${apiBaseUrl()}/auth/terms/accept`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'content-type': 'application/json',
          authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({
          consents: REQUIRED_TERMS.map((term) => ({
            term_id: term.id,
            agreed: true,
          })),
        }),
      });

      if (!response.ok) {
        setError(`약관 동의 저장에 실패했습니다. (${response.status})`);
        return;
      }

      clearTermsPendingCookie();
      router.replace(safeNext);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '약관 동의 저장에 실패했습니다.');
    } finally {
      setSubmitting(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!allChecked || !canSubmitTerms || submitting) return;
    void submitTerms();
  }

  return (
    <main className="mx-auto max-w-md px-6 py-20">
      <form className="flex flex-col gap-6" onSubmit={handleSubmit}>
        <header className="space-y-2">
          <h1 className="text-2xl font-semibold text-slate-950">약관 동의가 필요합니다</h1>
          <p className="text-sm leading-6 text-slate-600">
            Google 또는 네이버 계정으로 처음 시작하는 경우 집핀 내부 약관 동의 후
            계속할 수 있습니다.
          </p>
        </header>

        <div className="space-y-3">
          {REQUIRED_TERMS.map((term) => (
            <label key={term.id} className="flex items-center gap-3 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={checked[term.id] === true}
                onChange={(event) =>
                  setChecked((current) => ({
                    ...current,
                    [term.id]: event.target.checked,
                  }))
                }
                className="h-4 w-4"
              />
              {term.label}
            </label>
          ))}
        </div>

        {!canSubmitTerms ? (
          <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            약관 동의 저장 API가 Supabase 세션을 검증하도록 준비된 뒤 계속할 수 있습니다.
          </p>
        ) : null}

        {error ? (
          <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={!allChecked || !canSubmitTerms || submitting}
          className="w-fit rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          {submitting
            ? '동의 저장 중...'
            : canSubmitTerms
              ? `동의하고 ${safeNext}로 이동`
              : '동의 저장 API 준비 중'}
        </button>
      </form>
    </main>
  );
}

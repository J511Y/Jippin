'use client';

import { useMemo, useState } from 'react';

import { isSafeNext } from '@/lib/safe-redirect';

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

export function TermsGate({ nextPath }: TermsGateProps) {
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const safeNext = useMemo(() => resolveNext(nextPath), [nextPath]);
  const allChecked = REQUIRED_TERMS.every((term) => checked[term.id]);
  const canSubmitTerms = termsAcceptEnabled();

  return (
    <main className="mx-auto flex max-w-md flex-col gap-6 px-6 py-20">
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

      <button
        type="button"
        disabled={!allChecked || !canSubmitTerms}
        className="w-fit rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
      >
        {canSubmitTerms ? `동의하고 ${safeNext}로 이동` : '동의 저장 API 준비 중'}
      </button>
    </main>
  );
}

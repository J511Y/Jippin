import { Suspense } from 'react';

import { TermsGate } from './terms-gate';

export const metadata = {
  title: '약관 동의',
};

type TermsPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

function pickNext(value: string | string[] | undefined): string | null {
  if (Array.isArray(value)) {
    return value[0] ?? null;
  }
  return value ?? null;
}

export default async function TermsPage({ searchParams }: TermsPageProps) {
  const resolved = (await searchParams) ?? {};
  return (
    <Suspense
      fallback={
        <main className="mx-auto flex max-w-md flex-col gap-4 px-6 py-20">
          <p className="text-sm text-slate-600">약관 동의 화면을 준비하는 중...</p>
        </main>
      }
    >
      <TermsGate nextPath={pickNext(resolved.next)} />
    </Suspense>
  );
}

'use client';

import { Suspense, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

import { isSafeNext } from '@/lib/safe-redirect';

const DEFAULT_NEXT = process.env.NEXT_PUBLIC_FRONTEND_AUTH_SUCCESS_URL ?? '/';
const OAUTH_GUARD_KEY = 'jippin_oauth_in_progress';

function clearOAuthGuard(): void {
  try {
    window.sessionStorage.removeItem(OAUTH_GUARD_KEY);
  } catch {
    // Storage can be disabled in private browsing. Navigation should still continue.
  }
}

function CallbackDoneRunner(): null {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    clearOAuthGuard();
    if (searchParams.get('merge') === 'failed') {
      try {
        window.sessionStorage.setItem('jippin_merge_hint', 'failed');
      } catch {
        // Best-effort hint for the destination page.
      }
    }

    const nextRaw = searchParams.get('next');
    router.replace(nextRaw && isSafeNext(nextRaw) ? nextRaw : DEFAULT_NEXT);
  }, [router, searchParams]);

  return null;
}

export default function CallbackDonePage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto flex max-w-md flex-col gap-4 px-6 py-20">
          <p className="text-sm text-slate-600">로그인 완료 처리 중...</p>
        </main>
      }
    >
      <CallbackDoneRunner />
    </Suspense>
  );
}

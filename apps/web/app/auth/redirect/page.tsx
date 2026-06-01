'use client';

import { Suspense, useEffect, useMemo } from 'react';
import { useSearchParams } from 'next/navigation';

import { isSafeOAuthHandoff } from '@/lib/safe-redirect';

// /auth/redirect — OAuth 진입 단계 small client page (CMP-577 runbook §4.6, line ~1032).
//
// 흐름:
//   /auth/oauth/start (Web BFF) ──302──> /auth/redirect?to=<oauth_url>
//                                              │
//                                              │ (1) sessionStorage.jippin_oauth_in_progress='1' set
//                                              │ (2) window.location.assign(to)
//                                              ▼
//                                       <Supabase OAuth start URL>
//
// 본 page 의 책임은 `?to=` 파라미터가 open redirect 의 진입점이 되지 않도록 차단하는 것.
// SSOT 는 lib/safe-redirect.ts 의 `isSafeOAuthHandoff` — `to` 는 절대 URL 이며
// scheme + origin 이 NEXT_PUBLIC_SUPABASE_URL 와 정확히 일치해야 통과한다.
//
// 검증 실패 시:
//   - sessionStorage flag 를 set 하지 않는다.
//   - window.location.assign 을 호출하지 않는다.
//   - 사용자에게 명시적 에러 카드 + /login 복귀 링크를 노출한다.

type RedirectDecision =
  | { kind: 'invalid_config' }
  | { kind: 'invalid_target' }
  | { kind: 'navigate'; to: string };

function decide(to: string | null, supabaseUrl: string | undefined): RedirectDecision {
  if (!supabaseUrl) return { kind: 'invalid_config' };
  if (!isSafeOAuthHandoff(to, supabaseUrl)) return { kind: 'invalid_target' };
  return { kind: 'navigate', to: to as string };
}

function RedirectRunner() {
  const sp = useSearchParams();
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;

  // Pure derivation — validation must NOT call setState from inside an effect (React 19 rule).
  const decision = useMemo<RedirectDecision>(
    () => decide(sp.get('to'), supabaseUrl),
    [sp, supabaseUrl],
  );

  useEffect(() => {
    if (decision.kind !== 'navigate') return;
    try {
      window.sessionStorage.setItem('jippin_oauth_in_progress', '1');
    } catch {
      // private mode / storage disabled — guard 가 set 되지 않더라도 OAuth 자체는 진행한다.
      // §4.1.1 SessionProvider 의 10분 stale 안전망이 정리 책임을 진다.
    }
    window.location.assign(decision.to);
  }, [decision]);

  if (decision.kind === 'invalid_config') {
    return (
      <main className="mx-auto flex max-w-md flex-col gap-4 px-6 py-20">
        <h1 className="text-xl font-semibold">로그인 설정 오류</h1>
        <p className="text-sm text-slate-600">
          OAuth 진입 URL 을 검증할 수 있는 설정이 없습니다. 운영자에게 문의해 주세요.
        </p>
        <a href="/login" className="text-sm underline underline-offset-2">
          로그인 화면으로 돌아가기
        </a>
      </main>
    );
  }

  if (decision.kind === 'invalid_target') {
    return (
      <main className="mx-auto flex max-w-md flex-col gap-4 px-6 py-20">
        <h1 className="text-xl font-semibold">잘못된 로그인 요청</h1>
        <p className="text-sm text-slate-600">
          허용되지 않은 외부 주소로 이동을 시도했습니다. 안전을 위해 진행을 중단했어요.
        </p>
        <a href="/login" className="text-sm underline underline-offset-2">
          로그인 화면으로 돌아가기
        </a>
      </main>
    );
  }

  return (
    <main className="mx-auto flex max-w-md flex-col gap-4 px-6 py-20">
      <p className="text-sm text-slate-600">소셜 로그인 화면으로 이동 중…</p>
    </main>
  );
}

export default function AuthRedirectPage() {
  // useSearchParams 는 Suspense boundary 가 필요하다 (Next.js App Router).
  return (
    <Suspense
      fallback={
        <main className="mx-auto flex max-w-md flex-col gap-4 px-6 py-20">
          <p className="text-sm text-slate-600">소셜 로그인 화면으로 이동 중…</p>
        </main>
      }
    >
      <RedirectRunner />
    </Suspense>
  );
}

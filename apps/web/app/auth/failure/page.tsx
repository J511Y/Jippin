'use client';

import Link from 'next/link';
import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';

import { IdentityAlreadyExistsModal } from '@/app/(auth)/login/identity-already-exists-modal';
import { isSafeNext } from '@/lib/safe-redirect';
import { isUiProvider, type UiProvider } from '@/lib/supabase/providers';

const OAUTH_GUARD_KEY = 'jippin_oauth_in_progress';

const REASON_COPY: Record<string, { title: string; body: string }> = {
  access_denied: {
    title: '로그인이 취소되었습니다',
    body: '소셜 로그인 화면에서 동의를 완료하지 않아 집핀 계정 연결을 중단했습니다.',
  },
  identity_already_exists: {
    title: '이미 가입된 계정이 있습니다',
    body: '현재 비회원 검토 데이터를 기존 계정으로 옮긴 뒤 계속할 수 있습니다.',
  },
  missing_code: {
    title: '로그인 응답이 올바르지 않습니다',
    body: 'OAuth 인증 코드가 없어 세션을 만들 수 없습니다. 다시 시도해 주세요.',
  },
  exchange_failed: {
    title: '로그인을 완료하지 못했습니다',
    body: '소셜 로그인 세션 교환에 실패했습니다. 잠시 후 다시 시도해 주세요.',
  },
  oauth_error: {
    title: '로그인을 시작할 수 없습니다',
    body: '소셜 로그인 처리 중 오류가 발생했습니다. 다시 시도해 주세요.',
  },
  oauth_init_failed: {
    title: '로그인 URL을 만들지 못했습니다',
    body: '소셜 로그인 주소를 생성하지 못했습니다. 잠시 후 다시 시도해 주세요.',
  },
  oauth_guard_stale: {
    title: '로그인 시간이 만료되었습니다',
    body: '소셜 로그인 요청이 만료되었습니다. 로그인 화면에서 다시 시작해 주세요.',
  },
  merge_commit_failed: {
    title: '이전 데이터를 옮기지 못했습니다',
    body: '로그인은 완료되었지만 비회원 검토 데이터를 기존 계정으로 옮기지 못했습니다. 다시 시도해 주세요.',
  },
  merge_unavailable: {
    title: '이전 기능을 준비 중입니다',
    body: '기존 계정으로 비회원 검토 데이터를 옮기는 서버 기능이 아직 준비되지 않았습니다.',
  },
  kakao_sync_unavailable: {
    title: '카카오 약관 확인이 필요합니다',
    body: '카카오 Sync 동의 저장 경로가 준비되지 않아 로그인을 완료할 수 없습니다. 잠시 후 다시 시도해 주세요.',
  },
};

function clearOAuthGuard(): void {
  try {
    window.sessionStorage.removeItem(OAUTH_GUARD_KEY);
  } catch {
    // Storage can be disabled. The failure page should still render.
  }
}

type AuthFailureViewProps = {
  reason: string | null;
  provider?: string | null;
  nextPath?: string | null;
};

function normalizeProvider(value: string | null | undefined): UiProvider {
  return isUiProvider(value) ? value : 'kakao';
}

function normalizeNext(value: string | null | undefined): string {
  return value && isSafeNext(value) ? value : '/';
}

export function AuthFailureView({ reason, provider, nextPath }: AuthFailureViewProps) {
  const normalized = reason && REASON_COPY[reason] ? reason : 'oauth_error';
  const copy = REASON_COPY[normalized] ?? {
    title: '로그인을 시작할 수 없습니다',
    body: '소셜 로그인 처리 중 오류가 발생했습니다. 다시 시도해 주세요.',
  };
  const canRetryMerge = normalized === 'identity_already_exists' || normalized === 'merge_commit_failed';
  const [modalOpen, setModalOpen] = useState(canRetryMerge);
  const initialProvider = normalizeProvider(provider);
  const safeNext = normalizeNext(nextPath);

  useEffect(() => {
    clearOAuthGuard();
  }, []);

  return (
    <main className="mx-auto flex max-w-md flex-col gap-6 px-6 py-20">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold text-slate-950">{copy.title}</h1>
        <p className="text-sm leading-6 text-slate-600">{copy.body}</p>
      </header>

      <div className="flex flex-wrap gap-2">
        {canRetryMerge ? (
          <button
            type="button"
            onClick={() => setModalOpen(true)}
            className="rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white"
          >
            기존 계정으로 옮기기
          </button>
        ) : null}
        <Link
          href="/login"
          className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium"
        >
          다시 로그인
        </Link>
      </div>

      <IdentityAlreadyExistsModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        initialProvider={initialProvider}
        nextPath={safeNext}
      />
    </main>
  );
}

function AuthFailureReader() {
  const searchParams = useSearchParams();
  return (
    <AuthFailureView
      reason={searchParams.get('reason')}
      provider={searchParams.get('provider')}
      nextPath={searchParams.get('next')}
    />
  );
}

export default function AuthFailurePage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto flex max-w-md flex-col gap-4 px-6 py-20">
          <p className="text-sm text-slate-600">로그인 오류를 확인하는 중...</p>
        </main>
      }
    >
      <AuthFailureReader />
    </Suspense>
  );
}

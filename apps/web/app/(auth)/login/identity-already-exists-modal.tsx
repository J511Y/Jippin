'use client';

import * as Dialog from '@radix-ui/react-dialog';
import { useMemo, useState } from 'react';

import { getOrCreateAnonymousUserId } from '@/lib/anonymous-user';
import { isSafeNext } from '@/lib/safe-redirect';
import { UI_PROVIDERS, type UiProvider } from '@/lib/supabase/providers';

type IdentityAlreadyExistsModalProps = {
  open: boolean;
  onOpenChange?: (open: boolean) => void;
  initialProvider?: UiProvider;
  nextPath?: string | null;
};

const PROVIDER_LABEL: Record<UiProvider, string> = {
  kakao: '카카오',
  naver: '네이버',
  google: 'Google',
};

function resolveNext(nextPath: string | null | undefined): string {
  return nextPath && isSafeNext(nextPath) ? nextPath : '/';
}

function mergeIntentEnabled(): boolean {
  return process.env.NEXT_PUBLIC_AUTH_MERGE_INTENTS_ENABLED === 'true';
}

export function IdentityAlreadyExistsModal({
  open,
  onOpenChange,
  initialProvider = 'kakao',
  nextPath,
}: IdentityAlreadyExistsModalProps) {
  const [provider, setProvider] = useState<UiProvider>(initialProvider);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const safeNext = useMemo(() => resolveNext(nextPath), [nextPath]);
  const canMerge = mergeIntentEnabled();

  async function continueWithMerge() {
    if (!canMerge) return;
    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      const anonymousUserId = await getOrCreateAnonymousUserId();
      try {
        window.sessionStorage.setItem('jippin_oauth_in_progress', '1');
      } catch {
        // OAuth 자체는 계속 진행한다.
      }

      const url = new URL('/auth/oauth/start', window.location.origin);
      url.searchParams.set('provider', provider);
      url.searchParams.set('intent', 'link-merge');
      url.searchParams.set('anonymous_user_id', anonymousUserId);
      url.searchParams.set('next', safeNext);
      window.location.assign(url.toString());
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : '기존 계정 연결을 시작하지 못했습니다.',
      );
      setIsSubmitting(false);
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/30" />
        <Dialog.Content className="fixed left-1/2 top-1/2 flex w-[min(92vw,28rem)] -translate-x-1/2 -translate-y-1/2 flex-col gap-5 rounded-lg bg-white p-6 shadow-xl">
          <div className="space-y-2">
            <Dialog.Title className="text-lg font-semibold text-slate-950">
              이미 가입된 계정이 있습니다
            </Dialog.Title>
            <Dialog.Description className="text-sm leading-6 text-slate-600">
              선택한 소셜 계정은 기존 집핀 계정에 연결되어 있습니다. 현재 비회원
              검토 데이터를 기존 계정으로 옮긴 뒤 로그인하시겠습니까?
            </Dialog.Description>
          </div>

          <label className="flex flex-col gap-2 text-sm font-medium text-slate-700">
            이동할 계정
            <select
              value={provider}
              onChange={(event) => setProvider(event.target.value as UiProvider)}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm"
            >
              {UI_PROVIDERS.map((item) => (
                <option key={item} value={item}>
                  {PROVIDER_LABEL[item]}
                </option>
              ))}
            </select>
          </label>

          {errorMessage ? <p className="text-sm text-red-600">{errorMessage}</p> : null}
          {!canMerge ? (
            <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
              기존 계정으로 데이터 이전 기능은 서버 API 준비 후 활성화됩니다. 지금은 다른
              계정으로 로그인하거나 잠시 후 다시 시도해 주세요.
            </p>
          ) : null}

          <div className="flex justify-end gap-2">
            <Dialog.Close asChild>
              <button
                type="button"
                className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium"
                disabled={isSubmitting}
              >
                아니오
              </button>
            </Dialog.Close>
            <button
              type="button"
              onClick={() => void continueWithMerge()}
              disabled={isSubmitting || !canMerge}
              className="rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              {isSubmitting ? '준비 중...' : '예, 옮기고 로그인'}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

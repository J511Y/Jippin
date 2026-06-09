'use client';

import { useEffect } from 'react';

import { createClient } from '@/lib/supabase/client';
import { claimPendingAnonymousLeads } from '@/lib/leads/claim-anonymous-after-login';

/**
 * 카카오 OAuth 로그인 직후 익명 상담 리드를 새 계정으로 이관하는 전역 트리거.
 * 루트 레이아웃에 마운트되어 모든 진입 페이지에서 한 번 시도한다(stash 없으면 즉시 no-op).
 * 콜백 redirect 직후 세션 hydration 타이밍을 대비해 auth 상태 변화에서도 재시도한다.
 */
export function AnonymousLeadClaimer() {
  useEffect(() => {
    void claimPendingAnonymousLeads();

    const supabase = createClient();
    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session?.user && session.user.is_anonymous !== true) {
        void claimPendingAnonymousLeads();
      }
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  return null;
}

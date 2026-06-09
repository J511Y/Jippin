'use client';

/**
 * OAuth(카카오) 로그인 후 익명 상담 리드 이관 (CMP-DIRECT).
 *
 * "카카오로 시작하기" 는 ADR-0003 에 따라 항상 `signInWithOAuth` 로 first-class 카카오
 * 계정을 만든다(익명 세션에 자동 link 하지 않음). 그 결과 익명 세션의 상담 리드는 옛 익명
 * 유저에 남으므로, 이메일 로그인 경로(`/auth/password-login`)와 대칭으로 백엔드
 * `/auth/claim-anonymous-leads` 에 **양쪽 토큰 증명**을 보내 새 계정으로 이관한다.
 *
 * OAuth 는 외부 redirect 로 메모리 상태가 사라지므로, redirect 직전 익명 access token 을
 * sessionStorage 에 stash 하고(같은 origin·같은 탭이라 round trip 후에도 보존), 로그인이
 * 끝난 페이지에서 한 번 claim 을 시도한다. 이관 실패는 로그인을 막지 않는다(best-effort).
 */

import { apiBaseUrl } from '@/lib/api-base-url';
import { createClient } from '@/lib/supabase/client';

const STASH_KEY = 'jippin_pending_anon_claim';

export function stashAnonAccessToken(token: string): void {
  try {
    sessionStorage.setItem(STASH_KEY, token);
  } catch {
    // sessionStorage 미지원/차단 환경 — 이관을 건너뛴다(로그인은 정상 진행).
  }
}

function readStash(): string | null {
  try {
    return sessionStorage.getItem(STASH_KEY);
  } catch {
    return null;
  }
}

function clearStash(): void {
  try {
    sessionStorage.removeItem(STASH_KEY);
  } catch {
    // 무시.
  }
}

/**
 * stash 된 익명 토큰이 있고 현재 세션이 영구(비익명) 계정이면 익명 리드를 이관한다.
 * 아직 세션이 준비되지 않았거나 익명이면 stash 를 유지하고 다음 기회에 다시 시도한다.
 */
export async function claimPendingAnonymousLeads(): Promise<void> {
  const stashed = readStash();
  if (!stashed) {
    return;
  }

  let token: string | null = null;
  try {
    const supabase = createClient();
    const {
      data: { session }
    } = await supabase.auth.getSession();
    if (session?.user?.is_anonymous === true) {
      return; // 아직 영구 계정 아님 — stash 보존.
    }
    token = session?.access_token ?? null;
  } catch {
    return;
  }
  if (!token) {
    return; // 세션 미확정 — stash 보존, 다음 mount 에서 재시도.
  }

  try {
    await fetch(`${apiBaseUrl()}/auth/claim-anonymous-leads`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/json',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ anonymous_access_token: stashed }),
      cache: 'no-store'
    });
  } catch {
    // best-effort — 실패해도 로그인/탐색을 막지 않는다.
  } finally {
    clearStash();
  }
}

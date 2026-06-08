/**
 * 비로그인(익명) 상담 신청을 위한 Supabase 세션 부트스트랩 (CMP-DIRECT).
 *
 * 정책: 상담 신청은 비회원도 가능하다. 기존 세션(익명/영구)이 있으면 그대로 쓰고,
 * 없으면 익명 게이트(G1 explicit_intent)를 통과한 뒤 `signInAnonymously()` 로 익명
 * 세션을 만든다 (ADR-0004 §2.3 No-session bootstrap 패턴과 정합). 발급한 access token
 * 은 `lib/auth-token` 메모리 저장소에 넣어 `apiClient` 가 자동으로 Bearer 부착하게 한다.
 *
 * 반드시 **실제 제출/업로드 액션 시점**(explicit intent)에만 호출한다 — layout mount
 * 에서 호출하지 않는다 (익명 user 남발 방지, `lib/anonymous-gate` G1).
 */

import { DEFAULT_ANONYMOUS_GATE_CONFIG, evaluateAnonymousGate } from '@/lib/anonymous-gate';
import { setAccessToken } from '@/lib/auth-token';
import { createClient } from '@/lib/supabase/client';

export interface AnonymousSession {
  userId: string;
  token: string;
}

export async function ensureAnonymousSession(): Promise<AnonymousSession> {
  const supabase = createClient();

  const {
    data: { session: existing }
  } = await supabase.auth.getSession();
  if (existing?.access_token && existing.user) {
    setAccessToken(existing.access_token);
    return { userId: existing.user.id, token: existing.access_token };
  }

  // G1 — 발급은 명시적 사용자 의도(제출/업로드 클릭)에서만.
  const decision = await evaluateAnonymousGate(
    { ...DEFAULT_ANONYMOUS_GATE_CONFIG, requireExplicitIntent: true },
    { reason: 'explicit_intent' }
  );
  if (!decision.allowed) {
    throw new Error(`익명 세션 발급이 차단되었습니다 (${decision.reason}).`);
  }

  const { data, error } = await supabase.auth.signInAnonymously();
  if (error || !data.session || !data.user) {
    throw new Error(error?.message ?? '익명 세션 생성에 실패했습니다.');
  }
  setAccessToken(data.session.access_token);
  return { userId: data.user.id, token: data.session.access_token };
}

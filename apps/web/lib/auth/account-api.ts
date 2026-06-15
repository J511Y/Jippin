/**
 * 이메일/비밀번호 회원가입·문자인증·아이디/비번 찾기·회원탈퇴 백엔드 호출 (CMP-DIRECT).
 *
 * 회원가입/인증/찾기 엔드포인트는 인증 불필요(공개)라 `apiClient`(axios refresh 인터셉터)
 * 대신 단순 fetch 를 쓴다. 회원 탈퇴만 현재 Supabase 세션 access token 을 Bearer 로 보낸다.
 *
 * 로그인 세션(jippin_session 쿠키) 발급은 같은 origin 의 Route Handler
 * (`/auth/password-login`)가 담당한다 — 백엔드(api.jippin.ai)의 Set-Cookie 는
 * cross-origin 이라 웹 origin 에 직접 적용되지 않기 때문이다(OAuth 콜백과 동일 패턴).
 */

import { apiBaseUrl } from '@/lib/api-base-url';
import { createClient } from '@/lib/supabase/client';
import type { HomeCheckJob } from '@contracts/home-check';

export class AccountApiError extends Error {
  code: string;

  constructor(message: string, code: string) {
    super(message);
    this.name = 'AccountApiError';
    this.code = code;
  }
}

type ErrorEnvelope = { error?: { code?: string; message?: string } };

async function request<T>(
  path: string,
  init: RequestInit
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${apiBaseUrl()}${path}`, {
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      ...init
    });
  } catch {
    throw new AccountApiError('네트워크 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.', 'NETWORK_ERROR');
  }

  const data = (await res.json().catch(() => null)) as (ErrorEnvelope & Record<string, unknown>) | null;
  if (!res.ok) {
    const message = data?.error?.message ?? '요청을 처리하지 못했습니다.';
    const code = data?.error?.code ?? `HTTP_${res.status}`;
    throw new AccountApiError(message, code);
  }
  return (data ?? {}) as T;
}

export async function sendPhoneCode(phone: string): Promise<{ expires_in_seconds: number }> {
  return request('/auth/phone/send-code', { method: 'POST', body: JSON.stringify({ phone }) });
}

export async function verifyPhoneCode(phone: string, code: string): Promise<{ phone_token: string }> {
  return request('/auth/phone/verify-code', {
    method: 'POST',
    body: JSON.stringify({ phone, code })
  });
}

export interface SignupInput {
  name: string;
  email: string;
  phone: string;
  password: string;
  phone_token: string;
  agreed_to_terms: boolean;
  /** 만 14세 이상 자기확인 — 필수(개인정보보호법). false 면 서버가 400 으로 거부한다. */
  age_over_14: boolean;
  /** 광고성 정보(SMS 등) 수신 동의 — 선택(정보통신망법 §50). */
  marketing_consent: boolean;
}

export async function signup(input: SignupInput): Promise<{ user_id: string; email: string }> {
  // 기존 익명 세션이 있으면 그 access token 을 실어 보낸다. 백엔드가 소유권을 검증해
  // 익명으로 만든 상담 리드를 새 계정으로 이관한다(IDOR 방지 — 토큰 증명 기반).
  let anonAuth: Record<string, string> = {};
  try {
    const supabase = createClient();
    const {
      data: { session }
    } = await supabase.auth.getSession();
    if (session?.access_token && session.user?.is_anonymous) {
      anonAuth = { Authorization: `Bearer ${session.access_token}` };
    }
  } catch {
    anonAuth = {};
  }
  return request('/auth/signup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...anonAuth },
    body: JSON.stringify(input)
  });
}

export interface FoundEmail {
  email_masked: string;
  created_at: string;
}

export async function findEmail(
  phone: string,
  phoneToken: string
): Promise<{ emails: FoundEmail[] }> {
  return request('/auth/find-email', {
    method: 'POST',
    body: JSON.stringify({ phone, phone_token: phoneToken })
  });
}

export interface ResetPasswordInput {
  email: string;
  phone: string;
  phone_token: string;
  new_password: string;
}

export async function resetPassword(input: ResetPasswordInput): Promise<{ ok: boolean }> {
  return request('/auth/reset-password', { method: 'POST', body: JSON.stringify(input) });
}

async function authToken(): Promise<string> {
  const supabase = createClient();
  const {
    data: { session }
  } = await supabase.auth.getSession();
  if (!session?.access_token) {
    throw new AccountApiError('로그인이 필요합니다.', 'AUTH_REQUIRED');
  }
  return session.access_token;
}

async function authedRequest<T>(path: string, init: RequestInit): Promise<T> {
  const token = await authToken();
  return request<T>(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
      ...(init.headers ?? {})
    }
  });
}

export async function changePassword(
  currentPassword: string,
  newPassword: string
): Promise<{ ok: boolean }> {
  return authedRequest('/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword })
  });
}

export async function deleteAccount(): Promise<{ ok: boolean }> {
  return authedRequest('/auth/account', { method: 'DELETE' });
}

export interface MyLead {
  id: string;
  source_form: 'main_page' | 'lead_page';
  status: string;
  applicant_name: string;
  road_addr_part1: string | null;
  road_addr_part2: string | null;
  expansion_location: string | null;
  created_at: string;
}

export async function listMyLeads(): Promise<MyLead[]> {
  const { items } = await authedRequest<{ items: MyLead[] }>('/leads/mine', {
    method: 'GET'
  });
  return items;
}

/**
 * 내 우리집 체크 이력(로그인 필수). `/home-check/mine` 은 `require_supabase_request_user`
 * 라, apiClient 의 메모리 토큰(하드 리프레시 후 비어있을 수 있음) 대신 현재 Supabase 세션
 * access token 을 명시적으로 Bearer 로 싣는다(listMyLeads 와 동일 경로).
 */
export async function listMyHomeChecks(): Promise<HomeCheckJob[]> {
  const { items } = await authedRequest<{ items: HomeCheckJob[] }>('/home-check/mine', {
    method: 'GET'
  });
  return items;
}

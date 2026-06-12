'use server';

import { revalidatePath } from 'next/cache';

import { isAdminUser } from '@/lib/auth';
import { createServerComponentClient } from '@/lib/supabase/server';

/**
 * 관리자 본인 프로필 수정 서버 액션 (CMP-DIRECT).
 *
 * 회사명/이름/연락처는 본인 계정의 `user_metadata` 에 저장한다 — 사용자 본인만
 * 수정 가능한 영역이라 자기 프로필 용도로 적합하다. 인가 게이트(role)는 절대
 * user_metadata 로 옮기지 않는다(`lib/auth.ts` 봉인 — 게이트는 app_metadata 단독).
 *
 * `name` 은 담당자 배정 드롭다운 표시명과 알림톡 #{담당자명} 치환에도 쓰인다
 * (0012 admin_list_admins 가 user_metadata.name 을 읽음).
 */

export interface ProfileInput {
  name: string;
  company: string;
  phone: string;
}

interface ActionResult {
  ok: boolean;
  error?: string;
}

export async function updateProfile(input: ProfileInput): Promise<ActionResult> {
  const supabase = await createServerComponentClient();
  const {
    data: { user }
  } = await supabase.auth.getUser();
  if (!isAdminUser(user)) {
    return { ok: false, error: '관리자 권한이 필요합니다.' };
  }

  const name = input.name.trim();
  const company = input.company.trim();
  const phone = input.phone.trim();

  if (!name) {
    return { ok: false, error: '이름을 입력해 주세요.' };
  }
  if (name.length > 40 || company.length > 60 || phone.length > 20) {
    return { ok: false, error: '입력값이 너무 깁니다.' };
  }
  if (phone && !/^[0-9+\-() ]+$/.test(phone)) {
    return { ok: false, error: '연락처 형식이 올바르지 않습니다.' };
  }

  const { error } = await supabase.auth.updateUser({
    data: { name, company, phone }
  });
  if (error) {
    return { ok: false, error: `프로필 저장 실패: ${error.message}` };
  }

  revalidatePath('/', 'layout');
  return { ok: true };
}

export interface PasswordInput {
  currentPassword: string;
  newPassword: string;
}

/** GoTrue 에러 코드 → 사용자용 한국어 메시지 (출처: supabase/auth apierrors). */
const PASSWORD_ERROR_MESSAGES: Record<string, string> = {
  current_password_required: '현재 비밀번호를 입력해 주세요.',
  current_password_invalid: '현재 비밀번호가 올바르지 않습니다.',
  same_password: '새 비밀번호가 현재 비밀번호와 같습니다. 다른 비밀번호를 입력해 주세요.',
  weak_password: '비밀번호가 보안 기준을 충족하지 않습니다.'
};

export async function updatePassword({
  currentPassword,
  newPassword
}: PasswordInput): Promise<ActionResult> {
  const supabase = await createServerComponentClient();
  const {
    data: { user }
  } = await supabase.auth.getUser();
  if (!isAdminUser(user)) {
    return { ok: false, error: '관리자 권한이 필요합니다.' };
  }

  if (!currentPassword) {
    return { ok: false, error: '현재 비밀번호를 입력해 주세요.' };
  }
  if (newPassword.length < 8) {
    return { ok: false, error: '비밀번호는 8자 이상이어야 합니다.' };
  }
  if (newPassword.length > 72) {
    return { ok: false, error: '비밀번호는 72자 이하여야 합니다.' };
  }

  // Supabase 프로젝트의 secure password change 설정이 켜져 있어 현재 비밀번호
  // 검증(current_password)이 필수다 — 누락 시 GoTrue 가 400(current_password_required)을 반환한다.
  const { error } = await supabase.auth.updateUser({
    password: newPassword,
    current_password: currentPassword
  });
  if (error) {
    const known = error.code ? PASSWORD_ERROR_MESSAGES[error.code] : undefined;
    return { ok: false, error: known ?? `비밀번호 변경 실패: ${error.message}` };
  }
  return { ok: true };
}

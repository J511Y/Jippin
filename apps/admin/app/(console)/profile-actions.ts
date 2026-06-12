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

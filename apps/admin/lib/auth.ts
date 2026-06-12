/**
 * 관리자 판별 SSOT (CMP-DIRECT).
 *
 * 게이트 기준은 `app_metadata.role === 'admin'` 단 하나다.
 *  - `app_metadata` 는 service_role 로만 수정 가능 — 클라이언트가 위조할 수 없다.
 *    (`user_metadata` 는 사용자가 직접 바꿀 수 있으므로 절대 게이트로 쓰지 않는다.)
 *  - 계정 부여는 `tools/admin/create-admin-users.mjs` 시드 스크립트가 수행한다.
 *  - 익명 사용자(is_anonymous)는 role 이 없으므로 자동으로 걸러진다.
 */

import type { User } from '@supabase/supabase-js';

export function isAdminUser(user: User | null | undefined): user is User {
  if (!user) return false;
  const role = (user.app_metadata as Record<string, unknown> | undefined)?.role;
  return role === 'admin';
}

/**
 * Server Component / Route Handler 방어선: proxy 게이트와 별개로 호출 지점에서
 * 한 번 더 확인한다 (matcher 누락·정적 export 등으로 proxy 가 안 탄 경우 대비).
 */
export function requireAdminUser(user: User | null | undefined): User {
  if (!isAdminUser(user)) {
    throw new Error('관리자 권한이 필요합니다.');
  }
  return user;
}

/** user_metadata 의 프로필 필드 — 표시명은 0012 admin_list_admins 폴백과 동일 규칙. */
export function adminProfile(user: User): { name: string; company: string; phone: string } {
  const meta = (user.user_metadata ?? {}) as Record<string, unknown>;
  const metaName = typeof meta.name === 'string' ? meta.name.trim() : '';
  return {
    name: metaName || (user.email?.split('@')[0] ?? '관리자'),
    company: typeof meta.company === 'string' ? meta.company : '',
    phone: typeof meta.phone === 'string' ? meta.phone : ''
  };
}

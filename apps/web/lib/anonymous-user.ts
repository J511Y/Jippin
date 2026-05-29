/**
 * 비회원(anonymous user) ID 핸들링 헬퍼 (CMP-557, CMP-560).
 *
 * - 정책: 비회원 사전검토 흐름은 `localStorage.jippin_anonymous_user_id` 로 식별을
 *   유지하고, OAuth start / anonymous-users API 호출 시 동일 ID 를 백엔드와 동기화한다.
 * - 백엔드(`POST /auth/anonymous-users`)가 ID 의 유효성/재사용 여부(`reused`)를 결정하므로,
 *   클라이언트 측에서 무조건 새 UUID 를 만들지 않고 서버 응답을 정본으로 따른다.
 * - 모든 함수는 브라우저(window) 환경에서만 동작한다. SSR / Edge 에서 호출되면 즉시 throw.
 */
import { apiBaseUrl } from '@/lib/api-base-url';

export const ANONYMOUS_USER_ID_STORAGE_KEY = 'jippin_anonymous_user_id';

type AnonymousUserResponse = {
  anonymous_user_id: string;
  reused: boolean;
};

function assertBrowser(): void {
  if (typeof window === 'undefined') {
    throw new Error('anonymous-user helper must be called in the browser.');
  }
}

export function readStoredAnonymousUserId(): string | null {
  assertBrowser();
  try {
    return window.localStorage.getItem(ANONYMOUS_USER_ID_STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStoredAnonymousUserId(id: string): void {
  try {
    window.localStorage.setItem(ANONYMOUS_USER_ID_STORAGE_KEY, id);
  } catch {
    // localStorage 비활성/꽉 참 상황은 비회원 흐름의 hard-fail 사유는 아니다.
  }
}

export async function getOrCreateAnonymousUserId(): Promise<string> {
  assertBrowser();
  const existing = readStoredAnonymousUserId();
  const response = await fetch(`${apiBaseUrl()}/auth/anonymous-users`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ existing_anonymous_user_id: existing })
  });
  if (!response.ok) {
    throw new Error(`anonymous-user 발급 실패 (${response.status})`);
  }
  const data = (await response.json()) as AnonymousUserResponse;
  if (!data.anonymous_user_id) {
    throw new Error('anonymous-user 응답에 ID 가 없습니다.');
  }
  writeStoredAnonymousUserId(data.anonymous_user_id);
  return data.anonymous_user_id;
}

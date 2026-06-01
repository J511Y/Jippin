/**
 * 비회원(anonymous user) ID 핸들링 헬퍼 (CMP-557, CMP-560, CMP-584 round-5).
 *
 * - 정책: 비회원 사전검토 흐름은 `localStorage.jippin_anonymous_user_id` 로 식별을
 *   유지하고, OAuth start / anonymous-users API 호출 시 동일 ID 를 백엔드와 동기화한다.
 * - 백엔드(`POST /auth/anonymous-users`)가 ID 의 유효성/재사용 여부(`reused`)를 결정하므로,
 *   클라이언트 측에서 무조건 새 UUID 를 만들지 않고 서버 응답을 정본으로 따른다.
 * - **CMP-584 round-5 봉인:** 브라우저는 same-origin `/auth/anonymous-users` BFF
 *   (`apps/web/app/auth/anonymous-users/route.ts`) 를 호출한다. 서버 사이드 fetch 만이
 *   `NEXT_PUBLIC_API_BASE_URL=http://api:8000` 같은 Docker-internal hostname 을 안전하게
 *   resolve 할 수 있어, 호스트 브라우저에서 OAuth 진입 prerequisite 가 사전에 실패하는
 *   사고를 차단한다. `apiBaseUrl()` 를 클라이언트에서 직접 부르지 않는다.
 * - 모든 함수는 브라우저(window) 환경에서만 동작한다. SSR / Edge 에서 호출되면 즉시 throw.
 */

export const ANONYMOUS_USER_ID_STORAGE_KEY = 'jippin_anonymous_user_id';

const ANONYMOUS_USER_BFF_PATH = '/auth/anonymous-users';

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
  const response = await fetch(ANONYMOUS_USER_BFF_PATH, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    credentials: 'same-origin',
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

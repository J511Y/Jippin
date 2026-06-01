/**
 * 백엔드 API 베이스 URL (CMP-529 / CMP-564).
 *
 * 환경변수 `NEXT_PUBLIC_API_BASE_URL` 를 단일 소스로 사용한다. 미설정 시 로컬 개발용
 * `http://localhost:8000` 로 폴백한다. 단순 헬퍼이지만 호출처가 늘면서 같은 fallback
 * 문자열이 중복 산재하는 것을 막기 위해 lib 으로 격리한다.
 */
export function apiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
}

/**
 * Server-side API base URL for Route Handlers and the OAuth callback bridge.
 *
 * Resolution order:
 *   1. `API_INTERNAL_BASE_URL` for internal compose/network hosts.
 *   2. Absolute `NEXT_PUBLIC_API_BASE_URL` for deployments without a private API host.
 *   3. Localhost only outside production.
 *
 * A relative public base like `/api` is browser-only. Server code must have an
 * internal base in production so callback bridges do not silently target localhost.
 */
export function serverApiBaseUrl(): string {
  const internal = process.env.API_INTERNAL_BASE_URL;
  if (internal) return internal;

  const configured = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (configured && /^https?:\/\//i.test(configured)) {
    return configured;
  }

  if (process.env.NODE_ENV === 'production') {
    throw new Error(
      '[api-base-url] API_INTERNAL_BASE_URL must be set in production when NEXT_PUBLIC_API_BASE_URL is not an absolute URL (got: ' +
        (configured ?? '<unset>') +
        ').',
    );
  }
  return 'http://localhost:8000';
}

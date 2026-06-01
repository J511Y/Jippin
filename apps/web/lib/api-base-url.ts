/**
 * 백엔드 API 베이스 URL (CMP-529 / CMP-564).
 *
 * 환경변수 `NEXT_PUBLIC_API_BASE_URL` 를 단일 소스로 사용한다. 미설정 시 로컬 개발용
 * `http://localhost:8000` 로 폴백한다. 단순 헬퍼이지만 호출처가 늘면서 같은 fallback
 * 문자열이 중복 산재하는 것을 막기 위해 lib 으로 격리한다.
 *
 * **server-to-server / 브라우저 양쪽 모두에서 호출 가능.** Next.js SSR 또는 Route Handler
 * 에서 server-side `fetch` 로 API 를 호출할 때 사용 가능 (Docker compose 의 내부 host
 * `http://api:8000` 같은 비-public URL 도 허용). 브라우저가 `Location` 으로 따라가야 하는
 * 302 redirect 처럼 **반드시 browser-reachable** 해야 하는 경로는 `publicApiBaseUrl()` 을
 * 사용해야 한다 (CMP-584 round-3 분리).
 */
export function apiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
}

const DOCKER_INTERNAL_HOST_PATTERNS = [
  /^https?:\/\/api(?::\d+)?(?:\/|$)/i,
  /^https?:\/\/web(?::\d+)?(?:\/|$)/i,
  /^https?:\/\/app(?::\d+)?(?:\/|$)/i
] as const;

export function isDockerInternalBaseUrl(value: string): boolean {
  return DOCKER_INTERNAL_HOST_PATTERNS.some((pattern) => pattern.test(value));
}

/**
 * **Browser-reachable** API 베이스 URL (CMP-584 round-3 분리).
 *
 * 우선순위:
 *  1. server-only env `API_PUBLIC_BASE_URL` — 브라우저가 도달 가능한 public URL 만 (예:
 *     `https://api.jippin.com` 또는 dev 의 `http://localhost:8000`). 본 var 는 `NEXT_PUBLIC_`
 *     prefix 없이 server-only 로 노출하여 client bundle 에 빌드되지 않게 한다 (Docker compose
 *     의 `NEXT_PUBLIC_API_BASE_URL=http://api:8000` 와 충돌하지 않도록).
 *  2. fallback: `NEXT_PUBLIC_API_BASE_URL` — 단, Docker 내부 hostname 패턴 (`api:`, `web:`,
 *     `app:`) 이 감지되면 throw. 그대로 redirect 하면 브라우저가 Docker 내부 host 를 외부에서
 *     해석 시도하다 fail (`net::ERR_NAME_NOT_RESOLVED`).
 *  3. 최종 fallback: 로컬 개발용 `http://localhost:8000`.
 *
 * 본 헬퍼는 OAuth 진입 BFF (`/auth/oauth/start`) 처럼 302 `Location` 으로 사용자 브라우저를
 * 보내야 하는 경로 전용. 서버 간 fetch 는 `apiBaseUrl()` 사용.
 */
export function publicApiBaseUrl(): string {
  const explicit = process.env.API_PUBLIC_BASE_URL;
  if (explicit) {
    if (isDockerInternalBaseUrl(explicit)) {
      throw new Error(
        `api_public_base_url_must_be_browser_reachable: API_PUBLIC_BASE_URL="${explicit}" matches a Docker internal hostname pattern.`
      );
    }
    return explicit;
  }
  const fallback = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (fallback) {
    if (isDockerInternalBaseUrl(fallback)) {
      throw new Error(
        `nextpublic_api_base_url_not_browser_reachable: NEXT_PUBLIC_API_BASE_URL="${fallback}" is a Docker internal host. Set API_PUBLIC_BASE_URL to a browser-reachable URL for OAuth redirect.`
      );
    }
    return fallback;
  }
  return 'http://localhost:8000';
}

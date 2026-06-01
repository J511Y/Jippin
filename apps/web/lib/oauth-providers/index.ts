/**
 * Provider 화이트리스트 SSOT — CMP-584.
 *
 * 봉인 규칙 (runbook §4.x):
 *  - UI 노출 / BFF 진입 / callback 검증 / 분석 코드가 모두 본 모듈에서 import 한다.
 *  - 본 화이트리스트 밖의 provider 식별자가 들어오면 400 (BFF) / null (헬퍼) 로 거부한다.
 *  - email / password / magic link / passwordless 등 비-OAuth 인증 경로는 추가되지 않는다.
 *  - CMP-572 CEO 결정 (manual identity linking only) 정합: 자동 merge 우회로가 줄어들도록
 *    provider 목록을 가능한 한 좁게 유지한다.
 */

export const ALLOWED_PROVIDERS = ['google', 'kakao', 'naver'] as const;

export type AllowedProvider = (typeof ALLOWED_PROVIDERS)[number];

export function isAllowedProvider(value: unknown): value is AllowedProvider {
  return (
    typeof value === 'string' &&
    (ALLOWED_PROVIDERS as readonly string[]).includes(value)
  );
}

export function assertAllowedProvider(value: unknown): AllowedProvider {
  if (!isAllowedProvider(value)) {
    throw new Error(`provider_not_allowed: ${String(value)}`);
  }
  return value;
}

export {
  NAVER_PROTOCOL,
  NAVER_DEFAULT_ENDPOINTS,
  NAVER_DEFAULT_SCOPE,
  NAVER_ENV_KEYS,
  resolveNaverEndpoints,
  resolveNaverScope,
  assertNaverIsOAuth2,
  isOidcDiscoveryUrl,
  type NaverOAuth2Endpoints
} from './naver';

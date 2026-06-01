/**
 * Naver Custom OAuth2 어댑터 — CMP-584 Phase 1 (e).
 *
 * Naver 는 Supabase native provider 가 아니며, Supabase Custom OAuth Provider 의
 * **OAuth2 경로** (not OIDC) 로 등록한다 — runbook §4.3 / §8 봉인.
 *
 * 봉인 (runbook §4.3 보강):
 *  - Naver 공식 인증 사양은 OIDC discovery 를 노출하지 않는다. authorize / token / userinfo
 *    URL 을 명시적으로 입력하는 OAuth2 모드로만 동작 가능하다.
 *  - 본 어댑터는 환경변수만 owner 로 가진다. 실 client_id / client_secret / endpoint URL 은
 *    `.env.local` 또는 시크릿 매니저에서 주입한다 — 코드 / 문서 / 이슈에 실값 금지.
 *  - Phase 1 에서는 endpoint 메타데이터를 export 하여 Supabase 콘솔 등록값과 코드 측의
 *    정합을 단위 테스트로만 검증한다. 라이브 OAuth 호출은 Supabase hosted OAuth 가 owner.
 *
 * 환경변수 (실값 금지 — 변수명만 SSOT):
 *  | 변수 | 책임 |
 *  |---|---|
 *  | `NAVER_CLIENT_ID` | Naver Developers 콘솔에서 발급한 client ID. Supabase 콘솔 입력. |
 *  | `NAVER_CLIENT_SECRET` | client secret. Supabase 콘솔 입력. backend / web 코드에서 직접 읽지 않는다. |
 *  | `NAVER_AUTHORIZE_URL` | OAuth2 authorize endpoint (`https://nid.naver.com/oauth2.0/authorize`). |
 *  | `NAVER_TOKEN_URL` | OAuth2 token endpoint (`https://nid.naver.com/oauth2.0/token`). |
 *  | `NAVER_USERINFO_URL` | OAuth2 user-info endpoint (`https://openapi.naver.com/v1/nid/me`). |
 *  | `NAVER_SCOPE` | (옵션) Supabase 콘솔에 입력하는 scope. 기본은 `account` (runbook §4.3.1). |
 *
 * Scope 정책 (runbook §4.3.1 정합):
 *  - 기본 scope 는 `account` — 식별만 필요하므로 최소 권한. Naver 인증 화면이 가장 적게 묻는다.
 *  - `email` scope 는 Naver 비즈니스 앱 심사 통과 후에만 추가 가능하므로 Phase 1 에서는
 *    요구하지 않는다. 그러므로 user-info 응답의 `response.email` 은 `undefined` 일 수 있다는
 *    가정으로 callback / backend sync 가 동작해야 한다 (runbook §4.5.1 정합).
 *  - 변수만 노출하고 실 scope 토큰 문자열은 Supabase 콘솔 입력 또는 `NAVER_SCOPE` env 로만
 *    주입한다. 본 모듈은 default 값을 export 하여 단위 테스트로 정합만 검증.
 *
 * **사전 등록 가드 (Phase 1 (e) — review item 5 정합).**
 * `supabase.auth.signInWithOAuth({ provider: 'custom:naver' })` 호출 전에:
 *  1. Supabase 콘솔 → Authentication → Providers 에 Naver Custom OAuth Provider 가
 *     `OAuth2 (Generic)` 모드로 등록되어 있어야 한다 (runbook §4.3.1 / §8).
 *  2. 콘솔 identifier 가 정확히 `naver` 여야 한다 (§4.2.3 매핑 표). 변형 (예: `naver-prod`,
 *     `naver_kr`) 으로 등록하면 SDK 호출 시 `provider_not_enabled` 에러.
 *  3. 콘솔 등록 누락 / mismatch 시 §4.2.4 에러 매트릭스의 `provider_not_enabled` 분기로 빠져
 *     사용자에게 "일시적 로그인 오류" toast + Sentry alert + provider 버튼 disabled.
 * 본 어댑터는 코드 레벨에서 콘솔 등록 여부를 검증할 수 없다 (Supabase 콘솔 = out-of-band SSOT).
 * 그러므로 신규 환경 라이브 진입 전에는 §8 입력 항목 표를 운영자가 1회 수동 확인해야 한다.
 *
 * OIDC 와의 차이 (실수 방지용 주석):
 *  - Naver 는 `id_token` (OIDC) 을 발급하지 않는다 — Supabase 콘솔에서 "OIDC discovery URL"
 *    필드에 값을 넣으면 안 된다. Custom OAuth Provider 의 `OAuth2 (Generic)` 모드로 등록.
 *  - 사용자 식별은 user-info API 의 응답 본문 (`response.id`) 으로만 한다.
 *  - PKCE 는 Supabase 가 owner — 본 어댑터는 endpoint metadata 만 노출.
 */

export type NaverOAuth2Endpoints = {
  authorizeUrl: string;
  tokenUrl: string;
  userInfoUrl: string;
};

export const NAVER_PROTOCOL = 'oauth2' as const;

export const NAVER_DEFAULT_ENDPOINTS: NaverOAuth2Endpoints = {
  authorizeUrl: 'https://nid.naver.com/oauth2.0/authorize',
  tokenUrl: 'https://nid.naver.com/oauth2.0/token',
  userInfoUrl: 'https://openapi.naver.com/v1/nid/me'
};

export const NAVER_ENV_KEYS = {
  clientId: 'NAVER_CLIENT_ID',
  clientSecret: 'NAVER_CLIENT_SECRET',
  authorizeUrl: 'NAVER_AUTHORIZE_URL',
  tokenUrl: 'NAVER_TOKEN_URL',
  userInfoUrl: 'NAVER_USERINFO_URL',
  scope: 'NAVER_SCOPE'
} as const;

/**
 * Phase 1 기본 scope — `account`.
 *
 * Naver 비즈니스 앱 심사 전에는 email scope 를 사용할 수 없으므로 식별 전용 최소 권한.
 * runbook §4.3.1 / §4.5.1 정합. Supabase 콘솔 Custom OAuth Provider 의 scope 필드 입력값.
 */
export const NAVER_DEFAULT_SCOPE = 'account' as const;

export function resolveNaverEndpoints(
  env: Readonly<Record<string, string | undefined>> = process.env
): NaverOAuth2Endpoints {
  return {
    authorizeUrl:
      env[NAVER_ENV_KEYS.authorizeUrl] ?? NAVER_DEFAULT_ENDPOINTS.authorizeUrl,
    tokenUrl: env[NAVER_ENV_KEYS.tokenUrl] ?? NAVER_DEFAULT_ENDPOINTS.tokenUrl,
    userInfoUrl:
      env[NAVER_ENV_KEYS.userInfoUrl] ?? NAVER_DEFAULT_ENDPOINTS.userInfoUrl
  };
}

export function resolveNaverScope(
  env: Readonly<Record<string, string | undefined>> = process.env
): string {
  return env[NAVER_ENV_KEYS.scope] ?? NAVER_DEFAULT_SCOPE;
}

export function isOidcDiscoveryUrl(value: string): boolean {
  return /\.well-known\/openid-configuration\b/i.test(value);
}

export function assertNaverIsOAuth2(endpoints: NaverOAuth2Endpoints): void {
  for (const value of Object.values(endpoints)) {
    if (isOidcDiscoveryUrl(value)) {
      throw new Error(
        `naver_must_be_oauth2_not_oidc: endpoint "${value}" looks like an OIDC discovery URL.`
      );
    }
  }
}

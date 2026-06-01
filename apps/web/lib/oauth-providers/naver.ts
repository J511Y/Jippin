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
  userInfoUrl: 'NAVER_USERINFO_URL'
} as const;

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

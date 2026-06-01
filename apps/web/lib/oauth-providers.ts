/**
 * UI provider id → Supabase provider id 매핑 (CMP-581 / runbook §4.3 / §4.2.3).
 *
 * SSOT:
 *   - `docs/runbooks/supabase-web-auth.md` §4.2.3.
 *   - `docs/adr/0003-anon-user-and-sso.md` §2.3 — 동일 verified email automatic
 *     identity link/merge 는 영구 금지. 본 provider 매핑은 manual `auth.linkIdentity()`
 *     호출의 인자 정본이며, Supabase 콘솔의 "Auto-link verified emails" /
 *     "Link accounts with same email" 토글 (= `dangerously_enable_same_email_link_
 *     identity`) 은 모두 **OFF** (기본값) 이어야 한다 (§8 console track 책임).
 *
 * Phase 1 봉인 — Naver 는 항상 Custom OIDC (`custom:naver`). Kakao 는 §8 콘솔 트랙이
 * native (`kakao`) / Custom (`custom:kakao`) 중 어느 경로로 등록할지 결정한다 (R9 review).
 * 콘솔이 Custom 으로 가는데 SDK 가 default `'kakao'` 를 호출하면 Supabase 가
 * "provider not enabled" 로 거부하므로, default 매핑이 콘솔과 정합해야 한다.
 *
 * 본 모듈은 SDK / BFF / audit helper 가 같은 Kakao provider id 를 쓰도록 보장하는
 * **단일 export** 다 (round-11 항목 4). 콘솔 등록 id 가 바뀌면 본 파일의 환경변수
 * 하나만 갱신하면 된다.
 *
 * 콘솔 트랙이 결정한 값은 환경변수 `NEXT_PUBLIC_SUPABASE_KAKAO_PROVIDER_ID` 로 주입한다:
 *   - 'kakao'        — Supabase native Kakao 활성 (현재 SDK default 와 일치).
 *   - 'custom:kakao' — Supabase Custom OIDC Provider 로 등록. identifier 필드는
 *                      반드시 'kakao' (§4.2.3 콘솔 identifier 일치 봉인).
 *
 * 환경변수 미지정 시 fallback 은 `'kakao'`. 콘솔 트랙이 Custom 경로를 선택했음에도
 * 환경변수를 잊은 채 라이브 진입하는 케이스는 §4.2.4 의 `provider_not_enabled` /
 * `redirect_uri_mismatch` UX 매트릭스로 Sentry alert 가 떨어진다.
 *
 * **id_token 검증 위임 봉인 (round-11 항목 1 보강).** native `kakao` 든 Custom OIDC
 * `custom:kakao` 든, Kakao 의 `id_token` 검증 (issuer/audience/expiry/signature/nonce/
 * JWKS rotation) 은 **Supabase Auth 가 단독 책임**. 본 매핑이 가리키는 provider 가
 * `custom:` prefix 라고 해서 웹/API 레이어가 OIDC discovery 나 id_token 파싱을
 * 직접 수행하지 않는다 — Supabase 콘솔의 Custom OIDC discovery URL / JWKS URL
 * 설정 (§4.2.3) 이 SSOT 다. 본 매핑 export 는 단지 콘솔 등록 id 와 SDK 호출 id 를
 * 정합시키는 라벨이며, id_token 검증 책임 경계와는 무관함을 명시한다.
 *
 * **콘솔/SDK/env 명명 1:1 매트릭스 (round-11 항목 3).** SDK 호출 시 사용하는
 * provider id 와 Supabase 콘솔의 provider 등록 id 는 **정확히 일치** 해야 한다 —
 * 어긋나면 `provider_not_enabled` 로 OAuth 흐름이 시작 단계에서 거부된다. 본
 * 모듈의 SDK id ↔ Supabase 콘솔 ↔ env var 매트릭스:
 *
 *   | UI provider | env var (NEXT_PUBLIC_SUPABASE_KAKAO_PROVIDER_ID) | Supabase 콘솔 등록 | SDK 호출 id |
 *   | google      | (해당없음)                                       | Google (native)     | `'google'`        |
 *   | kakao       | (미지정) 또는 `'kakao'`                          | Kakao (native)      | `'kakao'`         |
 *   | kakao       | `'custom:kakao'`                                 | Custom OIDC (id=`kakao`) | `'custom:kakao'` |
 *   | naver       | (해당없음)                                       | Custom OIDC (id=`naver`) | `'custom:naver'` |
 *
 * Kakao 시크릿 (Client ID / Client Secret = Kakao 측 REST API key / client secret)
 * 은 **Supabase 콘솔이 단독 보유**. web 어댑터는 직접 사용하지 않으며 backend 가
 * Kakao OpenAPI (예: `/v2/user/me`, `/v2/user/scopes`) 를 직접 호출해야 하는
 * 경우만 `apps/api/.env.example` 의 `KAKAO_REST_API_KEY` / `KAKAO_CLIENT_SECRET`
 * 변수로 노출한다 — 본 변수명은 Supabase 콘솔 'Client ID' / 'Client Secret' 라벨과
 * 1:1 대응 (§8 콘솔 트랙이 SSOT). 명명이 어긋나면 콘솔 변경 시 코드 한 곳에서
 * 끝나야 할 갱신이 다중 파일로 흩어지므로 본 룰이 명시 봉인.
 */

export type UiProvider = 'google' | 'kakao' | 'naver';
export type SupabaseProvider = 'google' | 'kakao' | `custom:${string}`;

const KAKAO_PROVIDER_ID_ENV = 'NEXT_PUBLIC_SUPABASE_KAKAO_PROVIDER_ID';

function isSupabaseKakaoProvider(value: string | undefined): value is SupabaseProvider {
  return value === 'kakao' || value === 'custom:kakao';
}

export function resolveKakaoProviderId(
  envValue: string | undefined = process.env[KAKAO_PROVIDER_ID_ENV],
): SupabaseProvider {
  if (envValue === undefined || envValue.length === 0) return 'kakao';
  if (!isSupabaseKakaoProvider(envValue)) {
    throw new Error(
      `[oauth-providers] ${KAKAO_PROVIDER_ID_ENV}="${envValue}" 는 허용되지 않는 값입니다. ` +
        `'kakao' 또는 'custom:kakao' 만 허용.`,
    );
  }
  return envValue;
}

export function buildProviderMap(
  envValue: string | undefined = process.env[KAKAO_PROVIDER_ID_ENV],
): Record<UiProvider, SupabaseProvider> {
  return {
    google: 'google',
    kakao: resolveKakaoProviderId(envValue),
    naver: 'custom:naver',
  };
}

export function toSupabaseProviderId(
  ui: UiProvider,
  envValue: string | undefined = process.env[KAKAO_PROVIDER_ID_ENV],
): SupabaseProvider {
  return buildProviderMap(envValue)[ui];
}

export function isKakaoProvider(provider: SupabaseProvider | string | null | undefined): boolean {
  return provider === 'kakao' || provider === 'custom:kakao';
}

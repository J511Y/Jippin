/**
 * Kakao Sync 동의 audit 호출 helper (CMP-581 / runbook §4.5.2 경로 (a)).
 *
 * SSOT:
 *   - `docs/runbooks/supabase-web-auth.md` §4.5.2.2.
 *   - `docs/adr/0003-anon-user-and-sso.md` §2 — Kakao Sync 약관은 `terms_consents.
 *     source = 'kakao_sync'` 로 별도 저장. 내부 약관 화면은 Google/Naver 만 통과.
 *
 * **id_token 검증 위임 봉인 (round-11 항목 1 보강 / CMP-577 2차 리뷰).** Supabase
 * Auth 가 Kakao 를 social provider (native `kakao` 또는 Custom OIDC `custom:kakao`)
 * 로 처리하므로, 웹/API 레이어는 Kakao 의 `id_token` 을 **직접 파싱하거나 캐싱하지
 * 않는다**. id_token 의 issuer/audience/expiry/signature 검증, nonce 매칭, JWKS
 * rotation 추적은 모두 Supabase Auth 서버 책임이다. 본 헬퍼의 input 인터페이스
 * (`KakaoSyncAuditInput`) 에는 id_token 류 필드 (`id_token`, `oidc_token`,
 * `raw_kakao_payload`) 가 **존재하지 않으며**, FastAPI 의 `/auth/terms/kakao-sync`
 * 라우트로 보내는 본 payload 에도 절대 포함되지 않는다 (R3 + 회귀 방지 테스트로
 * 봉인).
 *
 * **허용 경로 (round-11 항목 1 보강).** 본 헬퍼가 FastAPI 와 통신하는 정본 흐름은
 * 단 하나:
 *   `(1) Supabase callback Route Handler 가 exchangeCodeForSession 으로 session 획득`
 *   → `(2) session.access_token` (Supabase 가 발급한 자체 JWT) 을 본 헬퍼의
 *       `supabaseAccessToken` 으로 전달`
 *   → `(3) Authorization: Bearer <supabaseAccessToken>` 헤더로 FastAPI 호출`.
 * Kakao 의 `id_token` 을 Bearer 로 쓰거나 본문에 직접 싣는 경로는 금지 — FastAPI 는
 * Supabase JWKS 만으로 호출자 인증을 수행한다.
 *
 * 세 가지 회귀 방지 책임:
 *   - R3: callback payload 정본은 `provider_access_token` 이다. `id_token` 은 SDK 가
 *         안정적으로 노출하지 않으며, 본 모듈은 그 값을 받지도 보내지도 않는다.
 *   - R13: backend 의 4xx/5xx 응답이 silent success 로 처리돼 `terms_consents(source='kakao_sync')`
 *         가 누락되는 회귀를 막기 위해 `response.ok` 를 명시 검증한다. 4xx/5xx 는
 *         throw — 호출부(callback Route Handler) 가 Sentry alert + reconcile 잡 트리거.
 *   - 약관 동의 SSOT 는 Supabase `auth.users.user_metadata` 가 아니라 backend 의
 *     `terms_consents(source='kakao_sync')` 행이다. metadata 만 갱신되고 행이 누락된
 *     상태는 audit 실패로 본다.
 *
 * **이메일 scope / linkIdentity 정합 (round-11 항목 4).** Kakao 비즈니스 앱 승인
 * 전에는 email scope 가 거부될 수 있다. 본 audit 라우트와 callback 흐름은 모두
 * `email` 의 유무에 의존하지 않는다 — Supabase `auth.users.email` 은 NULL 가능
 * (ADR-0003 §2.1 `users.email TEXT NULL`). `auth.linkIdentity({ provider: 'kakao' })`
 * 도 동일 — provider_subject 만 기준으로 linking 되므로 email scope 가 없어도 정상
 * 동작한다. 본 helper 는 email 을 payload 에 싣지 않으며, backend 가 audit 후
 * email 의 빈 값과 채워진 값을 모두 idempotent 하게 처리해야 한다.
 *
 * **호출 실패 → terms_consents rollback (round-11).** 본 helper 가 throw 하면
 * 호출자 (callback Route Handler) 는 동일 트랜잭션의 `terms_consents(source=
 * 'kakao_sync')` 삽입을 rollback 해야 한다 — Supabase user_metadata 만 갱신된
 * 채로 SSOT 가 비는 회귀를 막기 위해. provider access token 이 만료/revoke 된
 * 경우의 재시도 정책은 backend 의 audit 라우트 retry policy 가 SSOT (Phase 1
 * 에서는 callback 단발성 호출, 실패 시 Sentry breadcrumb + reconcile 잡 enqueue).
 *
 * Phase 1 dual-write 동안 본 헬퍼는 callback Route Handler 가 `exchangeCodeForSession`
 * 직후 한 번만 호출한다. provider 가 Kakao 가 아닐 때는 호출 자체를 하지 않는다 —
 * 본 모듈은 그 판정 책임을 가지지 않는다 (호출자가 `isKakaoProvider` 로 판정 후 호출).
 *
 * 본 모듈은 라이브 Supabase / Kakao 가 없어도 컴파일·테스트 가능하도록 SDK 타입에
 * 의존하지 않는다. callback Route Handler 가 Supabase session 에서 추출한 값을
 * 평문 인터페이스로 받아온다.
 */

export type KakaoLinkedProvider = 'kakao' | 'custom:kakao';

export interface KakaoSyncAuditInput {
  supabaseUserId: string;
  linkedProvider: KakaoLinkedProvider;
  /** Supabase 가 발급한 자체 JWT — backend 가 호출자 인증/인가에 사용. */
  supabaseAccessToken: string;
  /**
   * provider OAuth access token. Supabase session.provider_token.
   * id_token 이 아니다 (R3 / runbook §4.5.2.2). 본 필드는 Kakao OpenAPI
   * (예: `/v2/user/scopes`) 를 backend 가 호출할 때 쓰는 *access* token 이며,
   * id_token (OIDC subject claim 보유 JWT) 과는 다르다. backend 도 access_token
   * 의 issuer 를 직접 검증하지 않고 (Kakao 가 OAuth 표준상 access_token 자체
   * 검증 엔드포인트가 없다), 응답 본문의 200/4xx 만으로 판정한다.
   * Custom OIDC provider 가 access_token 을 노출하지 않으면 null.
   */
  providerAccessToken: string | null;
  /** provider 가 지원하는 경우만 노출. 일반적으로 callback 1회 호출에 불필요. */
  providerRefreshToken?: string | null;
}

export interface KakaoSyncAuditOptions {
  apiBaseUrl: string;
  /** 테스트/SSR 주입용. 기본값은 글로벌 fetch. */
  fetchImpl?: typeof fetch;
}

export class KakaoSyncAuditError extends Error {
  readonly status: number;
  readonly responseBody: string | null;

  constructor(message: string, status: number, responseBody: string | null) {
    super(message);
    this.name = 'KakaoSyncAuditError';
    this.status = status;
    this.responseBody = responseBody;
  }
}

/**
 * `/auth/terms/kakao-sync` 호출. 성공 시 void, 4xx/5xx 또는 네트워크 실패 시 throw.
 *
 * 호출자는 throw 를 catch 하여 §4.5.2 fallback (Sentry breadcrumb + reconcile 잡 enqueue)
 * 로 진입해야 한다. 본 헬퍼는 silent success 회귀를 방지하기 위해 응답 본문을 절대
 * `response.ok === false` 인 채로 통과시키지 않는다 (R13).
 */
export async function persistKakaoSyncConsent(
  input: KakaoSyncAuditInput,
  options: KakaoSyncAuditOptions,
): Promise<void> {
  const fetchImpl = options.fetchImpl ?? fetch;
  const url = `${options.apiBaseUrl}/auth/terms/kakao-sync`;

  const body = JSON.stringify({
    supabase_user_id: input.supabaseUserId,
    linked_provider: input.linkedProvider,
    provider_access_token: input.providerAccessToken,
    provider_refresh_token: input.providerRefreshToken ?? null,
  });

  const response = await fetchImpl(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${input.supabaseAccessToken}`,
    },
    body,
  });

  if (!response.ok) {
    let responseBody: string | null = null;
    try {
      responseBody = await response.text();
    } catch {
      responseBody = null;
    }
    throw new KakaoSyncAuditError(
      `Kakao Sync audit 호출이 실패했습니다 (status=${response.status}).`,
      response.status,
      responseBody,
    );
  }
}

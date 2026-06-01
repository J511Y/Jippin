/**
 * Kakao Sync 동의 audit 호출 helper (CMP-581 / runbook §4.5.2 경로 (a)).
 *
 * SSOT: `docs/runbooks/supabase-web-auth.md` §4.5.2.2.
 *
 * 두 가지 회귀 방지 책임:
 *   - R3: callback payload 정본은 `provider_access_token` 이다. `id_token` 은 SDK 가
 *         안정적으로 노출하지 않으므로 보내지 않는다.
 *   - R13: backend 의 4xx/5xx 응답이 silent success 로 처리돼 `terms_consents(source='kakao_sync')`
 *         가 누락되는 회귀를 막기 위해 `response.ok` 를 명시 검증한다. 4xx/5xx 는
 *         throw — 호출부(callback Route Handler) 가 Sentry alert + reconcile 잡 트리거.
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
   * id_token 이 아니다 (R3 / runbook §4.5.2.2).
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

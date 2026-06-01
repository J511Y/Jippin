/**
 * UI provider id → Supabase SDK provider id 매핑 SSOT (runbook §4.2.3).
 *
 * ADR-0003 의 UI 식별자 (`google` | `kakao` | `naver`) 는 그대로 두고,
 * SDK 경계에서만 변환. Custom OAuth2/manual provider 의 콘솔 identifier 와 정확히 일치해야 한다
 * (runbook §4.2.3 review item 4 — 콘솔 identifier 불일치 시 "provider not enabled" 에러).
 */

export type UiProvider = 'google' | 'kakao' | 'naver';
export type SupabaseProvider = 'google' | 'kakao' | `custom:${string}`;

const UI_PROVIDERS: ReadonlySet<UiProvider> = new Set(['google', 'kakao', 'naver']);

const MAP: Record<UiProvider, SupabaseProvider> = {
  google: 'google',
  // Supabase 가 Kakao native 지원을 추가했는지 콘솔 세팅 트랙이 확정 후 'custom:kakao' 로 교체 가능.
  kakao: 'kakao',
  naver: 'custom:naver',
};

export function isUiProvider(value: string | null | undefined): value is UiProvider {
  return typeof value === 'string' && UI_PROVIDERS.has(value as UiProvider);
}

export function toSupabaseProviderId(ui: UiProvider): SupabaseProvider {
  return MAP[ui];
}

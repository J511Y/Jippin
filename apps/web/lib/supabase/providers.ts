/**
 * UI provider id → Supabase SDK provider id 매핑 SSOT (runbook §4.2.3).
 *
 * MVP 프론트 UI 식별자는 `kakao` 하나만 제공하고, SDK 경계에서만 변환.
 * Custom OAuth2/manual provider 의 콘솔 identifier 와 정확히 일치해야 한다
 * (runbook §4.2.3 review item 4 — 콘솔 identifier 불일치 시 "provider not enabled" 에러).
 */

export type UiProvider = 'kakao';
export type SupabaseProvider = 'google' | 'kakao' | `custom:${string}`;

const UI_PROVIDERS: ReadonlySet<UiProvider> = new Set(['kakao']);

const MAP: Record<UiProvider, SupabaseProvider> = {
  // Supabase 가 Kakao native 지원을 추가했는지 콘솔 세팅 트랙이 확정 후 'custom:kakao' 로 교체 가능.
  kakao: 'kakao',
};

export function isUiProvider(value: string | null | undefined): value is UiProvider {
  return typeof value === 'string' && UI_PROVIDERS.has(value as UiProvider);
}

export function toSupabaseProviderId(ui: UiProvider): SupabaseProvider {
  return MAP[ui];
}

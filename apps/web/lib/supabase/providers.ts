export type UiProvider = 'google' | 'kakao' | 'naver';
export type SupabaseProvider = 'google' | 'kakao' | 'custom:kakao' | 'custom:naver';

export const UI_PROVIDERS: readonly UiProvider[] = ['kakao', 'naver', 'google'];

const MAP: Record<UiProvider, SupabaseProvider> = {
  google: 'google',
  kakao: 'kakao',
  naver: 'custom:naver',
};

export function isUiProvider(value: string | null | undefined): value is UiProvider {
  return typeof value === 'string' && (UI_PROVIDERS as readonly string[]).includes(value);
}

export function isSupabaseProvider(
  value: string | null | undefined,
): value is SupabaseProvider {
  return (
    value === 'google' ||
    value === 'kakao' ||
    value === 'custom:kakao' ||
    value === 'custom:naver'
  );
}

export function toSupabaseProviderId(ui: UiProvider): SupabaseProvider {
  return MAP[ui];
}

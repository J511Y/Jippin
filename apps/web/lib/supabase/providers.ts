export type UiProvider = 'google' | 'kakao' | 'naver';
export type SupabaseProvider = 'google' | 'kakao' | 'custom:kakao' | 'custom:naver';

export const UI_PROVIDERS: readonly UiProvider[] = ['kakao', 'naver', 'google'];

const MAP: Record<UiProvider, SupabaseProvider> = {
  google: 'google',
  kakao: 'custom:kakao',
  naver: 'custom:naver',
};

const REVERSE_MAP: Record<SupabaseProvider, UiProvider> = {
  google: 'google',
  kakao: 'kakao',
  'custom:kakao': 'kakao',
  'custom:naver': 'naver',
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

export function toUiProviderId(provider: SupabaseProvider): UiProvider {
  return REVERSE_MAP[provider];
}

export function isKakaoProvider(
  provider: SupabaseProvider | null | undefined,
): provider is Extract<SupabaseProvider, 'kakao' | 'custom:kakao'> {
  return provider === 'kakao' || provider === 'custom:kakao';
}

export function requiresInternalTerms(
  provider: SupabaseProvider | null | undefined,
): provider is Extract<SupabaseProvider, 'google' | 'custom:naver'> {
  return provider === 'google' || provider === 'custom:naver';
}

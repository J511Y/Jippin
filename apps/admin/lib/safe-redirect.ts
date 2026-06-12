// 로그인 `?next=` open-redirect 가드 — apps/web `lib/safe-redirect.ts` 의 isSafeNext 와
// 동일 규칙(CMP-577 runbook §4.6): 스킴 상대(`//`)·백슬래시 변형·제어문자/공백 거부.

export const DEFAULT_NEXT = '/';

function hasUnsafeChar(value: string): boolean {
  for (let i = 0; i < value.length; i += 1) {
    const code = value.charCodeAt(i);
    // ASCII 제어문자(NUL..US + DEL) + 공백 — response-splitting/spoofing 차단.
    if (code <= 32 || code === 127) return true;
  }
  return false;
}

export function isSafeNext(value: unknown): value is string {
  if (typeof value !== 'string' || value.length === 0) return false;
  if (!value.startsWith('/')) return false;
  if (value.startsWith('//') || value.startsWith('/\\') || value.startsWith('\\')) return false;
  if (hasUnsafeChar(value)) return false;
  return true;
}

export function resolveSafeNext(value: unknown, fallback: string = DEFAULT_NEXT): string {
  return isSafeNext(value) ? value : fallback;
}

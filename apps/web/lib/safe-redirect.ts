export const DEFAULT_SAFE_NEXT = '/';

export function isSafeNext(value: unknown): value is string {
  if (typeof value !== 'string' || value.length === 0) return false;
  if (!value.startsWith('/')) return false;
  if (value.startsWith('//') || value.startsWith('/\\') || value.startsWith('\\')) {
    return false;
  }
  if (/[\0\r\n]/.test(value)) return false;
  return true;
}

export function resolveSafeNext(
  value: unknown,
  fallback: string = DEFAULT_SAFE_NEXT,
): string {
  return isSafeNext(value) ? value : fallback;
}

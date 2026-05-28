/**
 * JWT 액세스/리프레시 토큰 저장소 추상화.
 *
 * - 본 모듈은 인증 토큰을 **메모리** 에 보관하는 기본 구현을 제공한다.
 *   - XSS 표면적 축소를 위해 localStorage 직접 저장은 회피한다.
 *   - 리프레시 토큰은 백엔드가 발급한 HttpOnly Secure 쿠키에서 자동 전달되는 것이 정본 경로.
 *     본 클라이언트 측 저장은 토큰을 *기억* 하기 위해서가 아니라 *인터셉터에 주입* 하기 위함이다.
 * - 토큰 회전(refresh) 정책은 [Frontend] 후속 이슈에서 NextAuth v5 또는 자체 JWT 중 하나로 확정.
 *   현재는 자체 JWT 인터셉터 경로로 두고, NextAuth 도입 시 본 모듈만 교체한다.
 */

type Listener = (token: string | null) => void;

let accessToken: string | null = null;
const listeners = new Set<Listener>();

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(next: string | null): void {
  accessToken = next;
  for (const listener of listeners) {
    listener(next);
  }
}

export function onAccessTokenChange(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function clearAccessToken(): void {
  setAccessToken(null);
}

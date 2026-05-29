/**
 * 백엔드 API 베이스 URL (CMP-529 / CMP-564).
 *
 * 환경변수 `NEXT_PUBLIC_API_BASE_URL` 를 단일 소스로 사용한다. 미설정 시 로컬 개발용
 * `http://localhost:8000` 로 폴백한다. 단순 헬퍼이지만 호출처가 늘면서 같은 fallback
 * 문자열이 중복 산재하는 것을 막기 위해 lib 으로 격리한다.
 */
export function apiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
}

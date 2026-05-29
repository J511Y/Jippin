import { AuthTestPanel } from './auth-test-panel';

/**
 * `/auth/test` — CMP-557 통합 검증 페이지 (CMP-564).
 *
 * 정책 (CMP-557 §2):
 *   - 비회원 ID 발급 / 보존
 *   - OAuth start (Kakao / Naver / Google)
 *   - 세션 상태 (`GET /auth/me`)
 *   - 다른 provider 연결 (CMP-563 link API)
 *   - 내부 약관 동의 (CMP-563 `/auth/terms/accept`)
 *   - 로그아웃 (CMP-563 `POST /auth/logout`)
 *
 * 본 페이지는 디자인 검수가 아닌 흐름 검증용이므로 색상/타이포는 최소 셋만 사용한다.
 */

export const metadata = {
  title: '인증 흐름 검증'
};

export default function AuthTestPage() {
  return <AuthTestPanel />;
}

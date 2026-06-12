/**
 * FastAPI 백엔드 베이스 URL — 서버 전용 (CMP-DIRECT).
 * 알림톡 발송 등 backend 가 자격증명을 단독 보유한 작업을 위임할 때 쓴다.
 *
 * fail-closed: 프로덕션(VERCEL_ENV=production)에서만 기본값으로 운영 API 를 쓰고,
 * 로컬/프리뷰는 명시적 `API_BASE_URL` 이 없으면 null — 실수로 운영 API 에
 * 고객 알림톡을 쏘는 사고를 막는다.
 */

import 'server-only';

export function apiBaseUrl(): string | null {
  const explicit = process.env.API_BASE_URL;
  if (explicit) return explicit;
  return process.env.VERCEL_ENV === 'production' ? 'https://api.jippin.ai' : null;
}

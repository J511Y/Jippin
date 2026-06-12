/**
 * FastAPI 백엔드 베이스 URL — 서버 전용 (CMP-DIRECT).
 * 알림톡 발송 등 backend 가 자격증명을 단독 보유한 작업을 위임할 때 쓴다.
 */

import 'server-only';

export function apiBaseUrl(): string {
  return process.env.API_BASE_URL ?? 'https://api.jippin.ai';
}

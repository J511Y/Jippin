'use client';

import { Analytics } from '@vercel/analytics/next';
import { SpeedInsights } from '@vercel/speed-insights/next';

/**
 * Vercel Web Analytics · Speed Insights 마운트 지점.
 *
 * beforeSend(함수 prop)을 넘겨야 하므로 Server Component 인 RootLayout 에서
 * 분리한 클라이언트 경계 컴포넌트다.
 *
 * 집핀의 비공개 라우트는 경로·쿼리에 이용자별 식별자를 담는다
 * (예: /contacts/<contactId>, /sessions/<sessionId>,
 *  /leads/new?fromSession=<sessionId>, /login?next=<returnUrl>).
 * Vercel 은 전체 URL(경로+쿼리)을 수집하므로 이벤트 전송 전에 동적 식별자
 * 세그먼트를 자리표시자로 치환하고 쿼리 문자열을 통째로 제거한다.
 * https://vercel.com/docs/analytics/redacting-sensitive-data
 */
function redactUrl(rawUrl: string): string {
  try {
    const url = new URL(rawUrl);
    // 쿼리(fromSession, next 등)에 식별자·토큰이 실릴 수 있어 통째로 제거.
    url.search = '';
    // 경로의 동적 id 세그먼트를 라우트 패턴으로 치환.
    url.pathname = url.pathname
      .replace(/\/contacts\/[^/]+/g, '/contacts/[contactId]')
      .replace(/\/sessions\/[^/]+/g, '/sessions/[sessionId]');
    return url.toString();
  } catch {
    return rawUrl;
  }
}

export function WebVitals() {
  return (
    <>
      <Analytics beforeSend={(event) => ({ ...event, url: redactUrl(event.url) })} />
      <SpeedInsights beforeSend={(event) => ({ ...event, url: redactUrl(event.url) })} />
    </>
  );
}

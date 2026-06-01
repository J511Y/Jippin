import { NextResponse, type NextRequest } from 'next/server';

import { serverApiBaseUrl } from '@/lib/api-base-url';

/**
 * 비회원(anonymous user) 식별자 BFF 프록시 (CMP-584 round-5 봉인).
 *
 * 브라우저가 직접 `${NEXT_PUBLIC_API_BASE_URL}/auth/anonymous-users` 를 호출하면 docker
 * compose 환경에서 `NEXT_PUBLIC_API_BASE_URL=http://api:8000` 가 브라우저 코드에 bake 되어
 * 호스트 브라우저가 Docker-only 내부 hostname 을 resolve 시도하다 `ERR_NAME_NOT_RESOLVED`
 * 로 실패한다. 결과적으로 `getOrCreateAnonymousUserId()` 가 사전에 실패해 OAuth BFF 도
 * 진입하지 못한다 — CMP-584 round-5 review item 3.
 *
 * 본 라우트는 same-origin (`/auth/anonymous-users`) 으로 받아 server-side 에서
 * `serverApiBaseUrl()` 로 백엔드에 프록시한다. compose 에서는 브라우저 공개 base(`/api`)가
 * 아닌 `API_INTERNAL_BASE_URL=http://api:8000` 를 사용해야 Node fetch 가 절대 URL 로
 * 백엔드에 도달한다.
 *
 * 봉인 / 비목표:
 *  - 본 라우트는 단일 백엔드 endpoint (`POST /auth/anonymous-users`) 전용. 다른 API path
 *    proxy 로 일반화하지 않는다.
 *  - request body 는 JSON 그대로 forward. content-type / cookie 헤더는 백엔드의 legacy
 *    세션 미들웨어가 필요로 할 수 있으므로 함께 전달한다.
 *  - 응답 body / status / set-cookie 는 그대로 브라우저로 반환.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const body = await request.text();
  const targetUrl = `${serverApiBaseUrl()}/auth/anonymous-users`;

  const forwardedHeaders: HeadersInit = {
    'content-type': request.headers.get('content-type') ?? 'application/json'
  };
  const cookie = request.headers.get('cookie');
  if (cookie) {
    (forwardedHeaders as Record<string, string>).cookie = cookie;
  }

  const upstream = await fetch(targetUrl, {
    method: 'POST',
    headers: forwardedHeaders,
    body
  });

  const responseBody = await upstream.text();
  const response = new NextResponse(responseBody, {
    status: upstream.status,
    headers: {
      'content-type': upstream.headers.get('content-type') ?? 'application/json'
    }
  });
  const setCookie = upstream.headers.get('set-cookie');
  if (setCookie) {
    response.headers.set('set-cookie', setCookie);
  }
  return response;
}

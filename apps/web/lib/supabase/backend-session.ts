/**
 * 백엔드 세션 브릿지 헬퍼 (CMP-DIRECT).
 *
 * Supabase access token 을 백엔드 `POST /auth/supabase/session` 으로 보내 jippin_session
 * 쿠키(HttpOnly)를 발급받고, 그 Set-Cookie 를 현재 웹 응답에 그대로 복사한다. 백엔드
 * (api.jippin.ai)의 Set-Cookie 는 cross-origin 이라 직접 적용되지 않으므로, 반드시 web
 * origin 의 Route Handler 가 응답에 실어 전달해야 한다(OAuth 콜백과 동일 invariant).
 */

import type { NextResponse } from 'next/server';

import { serverApiBaseUrl } from '@/lib/api-base-url';

export type BackendSessionBridgeResult = {
  signup_complete?: boolean;
  missing_required_terms?: string[];
  redirect_url?: string | null;
};

function setCookieValues(headers: Headers): string[] {
  const withGetSetCookie = headers as Headers & { getSetCookie?: () => string[] };
  const values = withGetSetCookie.getSetCookie?.();
  if (values?.length) {
    return values;
  }
  const value = headers.get('set-cookie');
  return value ? value.split(/,(?=\s*[^,;]+=)/g) : [];
}

export function copyBackendSessionCookies(source: Response, target: NextResponse): void {
  for (const cookie of setCookieValues(source.headers)) {
    target.headers.append('Set-Cookie', cookie);
  }
}

export async function mintBackendSession(
  accessToken: string,
  requestedProvider: string | null,
  response: NextResponse
): Promise<BackendSessionBridgeResult | null> {
  try {
    const bridge = await fetch(`${serverApiBaseUrl()}/auth/supabase/session`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        Accept: 'application/json',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        anonymous_user_id: null,
        requested_provider: requestedProvider
      }),
      cache: 'no-store'
    });
    if (!bridge.ok) {
      return null;
    }
    copyBackendSessionCookies(bridge, response);
    return (await bridge.json()) as BackendSessionBridgeResult;
  } catch {
    return null;
  }
}

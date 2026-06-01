import { NextResponse, type NextRequest } from 'next/server';

import { publicApiBaseUrl } from '@/lib/api-base-url';
import { isAllowedProvider } from '@/lib/oauth-providers';

/**
 * OAuth 진입 BFF (CMP-584 Phase 1 (e) — provider 화이트리스트 봉인).
 *
 * 본 라우트는 runbook §4.2.1 의 OAuth 진입 BFF 의 Phase 1 봉인본이다. Phase 1 에서는
 * 화이트리스트 가드 + 백엔드 OAuth start 로의 same-origin 302 만 owner 로 가진다.
 * Supabase SDK 직접 호출 / PKCE verifier cookie / intent dispatch 는 후속 자식 이슈에서
 * §4.2.1 SSOT 패턴으로 확장한다.
 *
 * 봉인:
 *  - `provider` 파라미터가 `ALLOWED_PROVIDERS` 밖이면 400 (`provider_not_allowed`).
 *  - email / password / magic link / OTP / passwordless 등 비-OAuth 인증 경로는 본 BFF
 *    의 진입점이 아니다. 별도 라우트로도 노출하지 않는다.
 *  - `provider` 파라미터가 화이트리스트 안일 때만 **browser-reachable** 백엔드 URL 로 302.
 *    `publicApiBaseUrl()` 가 Docker 내부 hostname (`api:`, `app:`, `web:`) 을 거부하므로
 *    compose 의 `NEXT_PUBLIC_API_BASE_URL=http://api:8000` 같은 server-to-server 전용 값을
 *    그대로 302 `Location` 에 흘리는 사고가 차단된다 (CMP-584 round-3 봉인).
 */

const ALLOWED_FORWARD_PARAMS = new Set(['return_url', 'anonymous_user_id', 'intent']);

export function GET(request: NextRequest): NextResponse {
  const url = request.nextUrl;
  const provider = url.searchParams.get('provider');

  if (!isAllowedProvider(provider)) {
    return NextResponse.json(
      {
        error: {
          code: 'PROVIDER_NOT_ALLOWED',
          message: '허용되지 않은 OAuth provider 입니다.'
        }
      },
      { status: 400 }
    );
  }

  let baseUrl: string;
  try {
    baseUrl = publicApiBaseUrl();
  } catch {
    return NextResponse.json(
      {
        error: {
          code: 'OAUTH_BASE_URL_MISCONFIGURED',
          message:
            'OAuth redirect base URL 이 brower-reachable 하지 않습니다. 운영자에게 문의해 주세요.'
        }
      },
      { status: 500 }
    );
  }

  const target = new URL(`${baseUrl}/auth/${provider}/start`);
  for (const [key, value] of url.searchParams.entries()) {
    if (key === 'provider') continue;
    if (!ALLOWED_FORWARD_PARAMS.has(key)) continue;
    target.searchParams.append(key, value);
  }

  return NextResponse.redirect(target, { status: 302 });
}

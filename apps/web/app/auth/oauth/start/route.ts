/**
 * OAuth 진입 BFF — `/auth/oauth/start` (runbook §4.2.1 / CMP-580).
 *
 * 본 Route Handler 가 단일 NextResponse 객체에 다음을 누적해 302 로 반환한다:
 *
 *   - Supabase SDK 가 `signInWithOAuth` / `linkIdentity` 호출 시 setAll 콜백으로 발급하는
 *     PKCE verifier cookie (`sb-<ref>-auth-token-code-verifier` 등).  ← R2 핵심.
 *   - flow context cookie (`jippin_oauth_provider`, Path=/auth/callback) — callback 의
 *     Kakao Sync 감지 (§4.5.2.1) 가 의도된 provider 를 식별하는 1차 신호.
 *
 * 모든 Set-Cookie 가 동일 `response` 객체에 부착되어야 PKCE / flow context 가 함께
 * 브라우저까지 전달된다 — 새 NextResponse.redirect 를 만들면 verifier 가 손실되어
 * callback 이 `auth/missing-code-verifier` 로 실패한다.
 *
 * 본 PR (CMP-580) 봉인 범위:
 *   - intent `link` / `signin` 완전 구현.
 *   - intent `link-merge` 는 익명 세션 폐기 + signInWithOAuth 까지 처리하되, backend
 *     `POST /auth/anon-merge-intents` 호출 및 `jippin_merge_intent` 쿠키 발급은
 *     CMP-579 (callback ladder · merge commit) 스코프에서 추가한다.
 *   - flow context cookie 는 plain provider id 로 시작. HMAC 서명/검증은 callback 의
 *     `detectNewlyLinkedProvider` 사용처 (CMP-579) 가 추가될 때 함께 봉인한다.
 */

import { NextResponse, type NextRequest } from 'next/server';

import { createRouteHandlerClient } from '@/lib/supabase/server';
import {
  isUiProvider,
  toSupabaseProviderId,
  type SupabaseProvider,
} from '@/lib/supabase/providers';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const VALID_INTENTS = ['link', 'signin', 'link-merge'] as const;
type Intent = (typeof VALID_INTENTS)[number];

function isIntent(value: string | null): value is Intent {
  return value !== null && (VALID_INTENTS as readonly string[]).includes(value);
}

const FLOW_CONTEXT_COOKIE = 'jippin_oauth_provider';
const FLOW_CONTEXT_MAX_AGE_SECONDS = 600;

function callbackUrl(request: NextRequest): string {
  const configured = process.env.NEXT_PUBLIC_FRONTEND_AUTH_CALLBACK_URL;
  if (configured) return configured;
  return new URL('/auth/callback', request.nextUrl.origin).toString();
}

function badRequest(reason: string): NextResponse {
  return NextResponse.json({ error: { code: 'invalid_request', message: reason } }, { status: 400 });
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const url = request.nextUrl;
  const uiProviderRaw = url.searchParams.get('provider');
  const intentRaw = url.searchParams.get('intent');

  if (!isUiProvider(uiProviderRaw)) {
    return badRequest('provider must be one of google | kakao | naver');
  }
  const intent: Intent = isIntent(intentRaw) ? intentRaw : 'link';
  const sbProvider: SupabaseProvider = toSupabaseProviderId(uiProviderRaw);

  // ★ Step 1 — 응답 객체 먼저 생성. SDK 의 setAll 콜백이 본 객체에 누적한다.
  //    NextResponse.next() 는 mutable header 컨테이너로 충분하며, 마지막에 status/Location 을
  //    덮어쓴다.
  const response = NextResponse.next();
  const supabase = createRouteHandlerClient({ request, response });

  // ★ Step 2 — flow context cookie. callback (Kakao Sync 감지 §4.5.2.1) 1차 신호.
  //    Path=/auth/callback 로 좁혀 다른 라우트에 누설 방지. HMAC 서명은 callback 검증 추가 시 (CMP-579) 봉인.
  response.cookies.set({
    name: FLOW_CONTEXT_COOKIE,
    value: sbProvider,
    httpOnly: true,
    secure: true,
    sameSite: 'lax',
    path: '/auth/callback',
    maxAge: FLOW_CONTEXT_MAX_AGE_SECONDS,
  });

  // ★ Step 3 — intent dispatch (runbook §4.2.1 표). 익명 user id 보존 의무 — link 에서는
  //    절대 signInWithOAuth 를 호출하지 않는다.
  let urlResult: Awaited<ReturnType<typeof supabase.auth.signInWithOAuth>>;
  if (intent === 'link') {
    urlResult = await supabase.auth.linkIdentity({
      provider: sbProvider,
      options: { redirectTo: callbackUrl(request), skipBrowserRedirect: true },
    });
  } else {
    if (intent === 'link-merge') {
      // §4.2.2 ladder step c — 익명 세션 명시 폐기 후에만 signInWithOAuth.
      // signOut 도 setAll 로 빈 cookie 를 response 에 부착.
      // NOTE: CMP-579 가 backend POST /auth/anon-merge-intents 호출 + jippin_merge_intent
      //       cookie 발급을 본 BFF 에 추가한다 (R5).
      await supabase.auth.signOut();
    }
    urlResult = await supabase.auth.signInWithOAuth({
      provider: sbProvider,
      options: { redirectTo: callbackUrl(request), skipBrowserRedirect: true },
    });
  }

  if (urlResult.error || !urlResult.data?.url) {
    // PKCE verifier cookie 는 이미 부착되었을 수 있으나 redirect 가 불가능하므로 4xx.
    // failure UX 는 runbook §4.2.4 매트릭스 / CMP-579 가 callback 가 받지 못한 케이스를 사용자에게 안내.
    return NextResponse.json(
      {
        error: {
          code: urlResult.error?.code ?? 'oauth_init_failed',
          message: urlResult.error?.message ?? 'Failed to acquire OAuth authorization URL',
        },
      },
      { status: 502 },
    );
  }

  // ★ Step 4 — 새 NextResponse.redirect 를 만들지 말고, 누적된 response.headers 를 그대로
  //    재사용하여 302 로 변환. Set-Cookie 헤더 (PKCE verifier + flow context) 가 모두 보존된다.
  response.headers.set('Location', urlResult.data.url);
  return new NextResponse(null, { status: 302, headers: response.headers });
}

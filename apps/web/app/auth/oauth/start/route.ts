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
 *   - flow context cookie 는 `SUPABASE_FLOW_COOKIE_SECRET` HMAC 서명 + nonce 로 봉인한다.
 */

import { NextResponse, type NextRequest } from 'next/server';

import { signFlowCookie } from '@/lib/flow-cookie';
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

function safeRelativeRedirect(value: string | null): string | null {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.includes('\\')) {
    return null;
  }

  return value;
}

function callbackUrl(request: NextRequest): string {
  const configured = process.env.NEXT_PUBLIC_FRONTEND_AUTH_CALLBACK_URL;
  const callback = configured
    ? new URL(configured, request.nextUrl.origin)
    : new URL('/auth/callback', request.nextUrl.origin);
  const next = safeRelativeRedirect(request.nextUrl.searchParams.get('next'));
  if (next) {
    callback.searchParams.set('next', next);
  }
  return callback.toString();
}

function badRequest(reason: string): NextResponse {
  return NextResponse.json({ error: { code: 'invalid_request', message: reason } }, { status: 400 });
}

function oauthInitFailed(error?: { code?: string; message?: string } | null): NextResponse {
  return NextResponse.json(
    {
      error: {
        code: error?.code ?? 'oauth_init_failed',
        message: error?.message ?? 'Failed to acquire OAuth authorization URL',
      },
    },
    { status: 500 },
  );
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const url = request.nextUrl;
  const uiProviderRaw = url.searchParams.get('provider');
  const intentRaw = url.searchParams.get('intent');

  if (!isUiProvider(uiProviderRaw)) {
    return badRequest('provider must be one of google | kakao | naver');
  }
  if (!isIntent(intentRaw)) {
    return badRequest('intent must be one of link | signin | link-merge');
  }
  const intent: Intent = intentRaw;
  const sbProvider: SupabaseProvider = toSupabaseProviderId(uiProviderRaw);

  // ★ Step 1 — 응답 객체 먼저 생성. SDK 의 setAll 콜백이 본 객체에 누적한다.
  //    Route Handler 에서는 middleware-only `NextResponse.next()` 를 쓰지 않는다.
  const response = new NextResponse(null);
  const supabase = createRouteHandlerClient({ request, response });

  // ★ Step 2 — flow context cookie. callback (Kakao Sync 감지 §4.5.2.1) 1차 신호.
  //    Path=/auth/callback 로 좁혀 다른 라우트에 누설 방지. 값은 HMAC + nonce 로 서명한다.
  response.cookies.set({
    name: FLOW_CONTEXT_COOKIE,
    value: signFlowCookie(
      { provider: uiProviderRaw, supabase_provider: sbProvider, intent },
      FLOW_CONTEXT_MAX_AGE_SECONDS,
    ),
    httpOnly: true,
    secure: true,
    sameSite: 'lax',
    path: '/auth/callback',
    maxAge: FLOW_CONTEXT_MAX_AGE_SECONDS,
  });

  // ★ Step 3 — intent dispatch (runbook §4.2.1 표). 익명 user id 보존 의무 — link 에서는
  //    절대 signInWithOAuth 를 호출하지 않는다.
  let urlResult: Awaited<ReturnType<typeof supabase.auth.signInWithOAuth>>;
  try {
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
        const signOutResult = await supabase.auth.signOut();
        if (signOutResult.error) {
          return oauthInitFailed({
            code: signOutResult.error.code ?? 'oauth_signout_failed',
            message: signOutResult.error.message ?? 'Failed to discard current session before OAuth merge',
          });
        }
      }
      urlResult = await supabase.auth.signInWithOAuth({
        provider: sbProvider,
        options: { redirectTo: callbackUrl(request), skipBrowserRedirect: true },
      });
    }
  } catch {
    return oauthInitFailed();
  }

  if (urlResult.error || !urlResult.data?.url) {
    // Fail-fast: fresh JSON response intentionally drops any accumulator Set-Cookie
    // headers so PKCE / flow cookies cannot survive a missing authorization URL.
    return oauthInitFailed(urlResult.error);
  }

  // ★ Step 4 — 새 NextResponse.redirect 를 만들지 말고, 누적된 response.headers 를 그대로
  //    재사용하여 302 로 변환. Set-Cookie 헤더 (PKCE verifier + flow context) 가 모두 보존된다.
  response.headers.set('Location', urlResult.data.url);
  return new NextResponse(null, { status: 302, headers: response.headers });
}

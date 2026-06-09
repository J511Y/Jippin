import { type NextRequest, NextResponse } from 'next/server';

import { serverApiBaseUrl } from '@/lib/api-base-url';
import { isSafeNext } from '@/lib/safe-redirect';
import { mintBackendSession } from '@/lib/supabase/backend-session';
import { createRouteHandlerClient } from '@/lib/supabase/server';

/**
 * 이메일/비밀번호 로그인 Route Handler (CMP-DIRECT).
 *
 * 카카오 OAuth 콜백과 동일하게 web origin 에서 세션 쿠키를 세팅한다:
 *   1) `signInWithPassword` 로 Supabase 세션(sb-* 쿠키)을 응답에 적재.
 *   2) 백엔드 `/auth/supabase/session` 브릿지로 jippin_session 쿠키 발급 후 응답에 복사.
 *   3) 클라이언트가 따라갈 redirect 경로를 JSON 으로 반환.
 *
 * 비밀번호는 서버측에서만 다루며 클라이언트 메모리/스토리지에 남기지 않는다.
 */

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

function safeNext(value: unknown): string {
  return typeof value === 'string' && isSafeNext(value) ? value : '/';
}

/**
 * 로그인한 영구 계정 토큰으로 익명 세션의 상담 리드를 이관 요청한다(백엔드가 양쪽 토큰 검증).
 * 실패해도 로그인 자체는 막지 않는다(best-effort).
 */
async function claimAnonymousLeads(accessToken: string, anonAccessToken: string): Promise<void> {
  try {
    await fetch(`${serverApiBaseUrl()}/auth/claim-anonymous-leads`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        Accept: 'application/json',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ anonymous_access_token: anonAccessToken }),
      cache: 'no-store'
    });
  } catch {
    // 무시 — 리드 이관 실패가 로그인을 막지 않는다.
  }
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  let body: { email?: unknown; password?: unknown; next?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: '잘못된 요청입니다.' }, { status: 400 });
  }

  const email = typeof body.email === 'string' ? body.email.trim() : '';
  const password = typeof body.password === 'string' ? body.password : '';
  const next = safeNext(body.next);

  if (!email || !password) {
    return NextResponse.json(
      { error: '이메일과 비밀번호를 입력해 주세요.' },
      { status: 400 }
    );
  }

  const response = new NextResponse(null);
  const supabase = createRouteHandlerClient({ request, response });

  // 로그인 직전 익명 세션이 있으면 그 access token 을 잡아둔다 — 로그인 후 익명 상담 리드를
  // 영구 계정으로 이관하는 데 쓴다(회원가입 경로와 대칭, 토큰-증명 기반).
  const { data: pre } = await supabase.auth.getSession();
  const anonAccessToken =
    pre.session?.user?.is_anonymous === true ? pre.session.access_token : null;

  const { data, error } = await supabase.auth.signInWithPassword({ email, password });
  const accessToken = data.session?.access_token;

  if (error || !accessToken) {
    return NextResponse.json(
      { error: '이메일 또는 비밀번호가 올바르지 않습니다.' },
      { status: 401 }
    );
  }

  if (anonAccessToken) {
    await claimAnonymousLeads(accessToken, anonAccessToken);
  }

  const bridge = await mintBackendSession(accessToken, 'email', response);
  if (!bridge) {
    return NextResponse.json(
      { error: '로그인 처리에 실패했습니다. 잠시 후 다시 시도해 주세요.' },
      { status: 502 }
    );
  }

  const redirect = bridge.signup_complete === false ? bridge.redirect_url ?? '/auth/terms' : next;
  const out = NextResponse.json({ redirect });
  for (const cookie of response.headers.getSetCookie?.() ?? []) {
    out.headers.append('Set-Cookie', cookie);
  }
  return out;
}

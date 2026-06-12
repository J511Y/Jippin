import { NextResponse, type NextRequest } from 'next/server';

import { isAdminUser } from '@/lib/auth';
import { resolveSafeNext } from '@/lib/safe-redirect';
import { createRouteHandlerClient } from '@/lib/supabase/server';

/**
 * 관리자 이메일/비밀번호 로그인 Route Handler (CMP-DIRECT).
 *
 * apps/web 의 `auth/password-login` 과 동일한 단일 NextResponse accumulator 패턴.
 * 단, 백엔드 세션 브릿지는 타지 않는다 — 관리자 앱은 Supabase 세션(sb-* 쿠키)만 쓴다.
 *
 * 로그인 성공이어도 `app_metadata.role !== 'admin'` 이면 즉시 signOut 후 403:
 * main Supabase 프로젝트는 일반 사용자 이메일 가입이 열려 있으므로 인증 성공과
 * 관리자 인가를 절대 동일시하지 않는다.
 */

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest): Promise<NextResponse> {
  let body: { email?: unknown; password?: unknown; next?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: '잘못된 요청입니다.' }, { status: 400 });
  }

  const email = typeof body.email === 'string' ? body.email.trim() : '';
  const password = typeof body.password === 'string' ? body.password : '';
  const next = resolveSafeNext(body.next);

  if (!email || !password) {
    return NextResponse.json({ error: '이메일과 비밀번호를 입력해 주세요.' }, { status: 400 });
  }

  const response = new NextResponse(null);
  const supabase = createRouteHandlerClient({ request, response });

  const { data, error } = await supabase.auth.signInWithPassword({ email, password });
  if (error || !data.user) {
    return NextResponse.json(
      { error: '이메일 또는 비밀번호가 올바르지 않습니다.' },
      { status: 401 }
    );
  }

  if (!isAdminUser(data.user)) {
    // 메인 제품과 auth 를 공유하므로 전역 signOut 은 해당 사용자의 모든 기기 세션을
    // 무효화한다 — 방금 만든 admin 사이트 세션만 지우도록 local scope 로 제한.
    await supabase.auth.signOut({ scope: 'local' });
    const out = NextResponse.json({ error: '관리자 권한이 없는 계정입니다.' }, { status: 403 });
    // signOut 의 쿠키 삭제분까지 응답에 반영한다.
    for (const cookie of response.headers.getSetCookie?.() ?? []) {
      out.headers.append('Set-Cookie', cookie);
    }
    return out;
  }

  const out = NextResponse.json({ redirect: next });
  for (const cookie of response.headers.getSetCookie?.() ?? []) {
    out.headers.append('Set-Cookie', cookie);
  }
  return out;
}

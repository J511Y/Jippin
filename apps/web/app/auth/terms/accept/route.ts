import { NextResponse, type NextRequest } from 'next/server';

import { apiBaseUrl } from '@/lib/api-base-url';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

const PENDING_ANONYMOUS_COOKIE = 'jippin_pending_anonymous_user_id';
const TERMS_PENDING_COOKIE = 'jippin_terms_pending';

type TermsAcceptPayload = {
  consents?: unknown;
};

function expireTermsFlowCookies(response: NextResponse): void {
  response.cookies.set(PENDING_ANONYMOUS_COOKIE, '', { path: '/auth', maxAge: 0 });
  response.cookies.set(TERMS_PENDING_COOKIE, '', { path: '/', maxAge: 0 });
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const authorization = request.headers.get('authorization');
  const payload = (await request.json()) as TermsAcceptPayload;
  const pendingAnonymousUserId = request.cookies.get(PENDING_ANONYMOUS_COOKIE)?.value ?? null;

  const upstream = await fetch(`${apiBaseUrl()}/auth/terms/accept`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      ...(authorization ? { authorization } : {}),
    },
    body: JSON.stringify({
      consents: payload.consents ?? [],
      pending_anonymous_user_id: pendingAnonymousUserId,
    }),
  });

  const body = await upstream.text();
  const response = new NextResponse(body, {
    status: upstream.status,
    headers: {
      'content-type': upstream.headers.get('content-type') ?? 'application/json',
    },
  });

  if (upstream.ok) {
    expireTermsFlowCookies(response);
  }

  return response;
}

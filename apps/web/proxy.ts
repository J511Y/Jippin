import { NextResponse, type NextRequest } from 'next/server';

import { serverApiBaseUrl } from '@/lib/api-base-url';
import { updateSession } from '@/lib/supabase/proxy';

const AUTH_COOKIE_NAME = process.env.AUTH_COOKIE_NAME ?? 'jippin_session';
const TERMS_PENDING_COOKIE = 'jippin_terms_pending';
const TERMS_STATUS_TIMEOUT_MS = 2_000;

const ANONYMOUS_ALLOWED_APP_PREFIXES = ['/app/pre-review'] as const;
const PROTECTED_APP_PREFIXES = [
  '/app/consult',
  '/app/leads',
  '/app/reports',
] as const;

function isAnonymousAllowed(pathname: string): boolean {
  return ANONYMOUS_ALLOWED_APP_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

function isProtected(pathname: string): boolean {
  if (!pathname.startsWith('/app')) {
    return false;
  }
  if (isAnonymousAllowed(pathname)) {
    return false;
  }
  return PROTECTED_APP_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

function redirectToLogin(request: NextRequest, nextPath: string): NextResponse {
  const loginUrl = request.nextUrl.clone();
  loginUrl.pathname = '/login';
  loginUrl.search = '';
  loginUrl.searchParams.set('next', nextPath);
  return NextResponse.redirect(loginUrl);
}

function redirectToTermsGate(request: NextRequest, nextPath: string): NextResponse {
  const termsUrl = request.nextUrl.clone();
  termsUrl.pathname = '/auth/terms';
  termsUrl.search = '';
  termsUrl.searchParams.set('next', nextPath);
  return NextResponse.redirect(termsUrl);
}

async function hasMissingRequiredTerms(request: NextRequest): Promise<boolean> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TERMS_STATUS_TIMEOUT_MS);
  try {
    const cookie = request.headers.get('cookie');
    const response = await fetch(`${serverApiBaseUrl()}/auth/me`, {
      method: 'GET',
      signal: controller.signal,
      headers: {
        accept: 'application/json',
        ...(cookie ? { cookie } : {}),
      },
      cache: 'no-store',
    });
    if (!response.ok) return true;
    const data = (await response.json()) as {
      signup_complete?: boolean;
      missing_required_terms?: string[];
    };
    return data.signup_complete === false || (data.missing_required_terms?.length ?? 0) > 0;
  } catch {
    return true;
  } finally {
    clearTimeout(timeout);
  }
}

export async function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  if (!isProtected(pathname)) {
    return NextResponse.next();
  }

  const nextPath = pathname + search;
  if (request.cookies.has(TERMS_PENDING_COOKIE)) {
    return redirectToTermsGate(request, nextPath);
  }

  if (!request.cookies.has(AUTH_COOKIE_NAME)) {
    return redirectToLogin(request, nextPath);
  }

  let response: NextResponse;
  try {
    ({ response } = await updateSession(request));
  } catch {
    return redirectToLogin(request, nextPath);
  }

  if (await hasMissingRequiredTerms(request)) {
    return redirectToTermsGate(request, nextPath);
  }

  return response;
}

export const config = {
  matcher: ['/app/:path*'],
};

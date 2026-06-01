import type { NextRequest } from 'next/server';

export function siteOriginFromRequest(request: NextRequest): string {
  const configured = process.env.NEXT_PUBLIC_SITE_URL;
  if (configured) {
    try {
      return new URL(configured).origin;
    } catch {
      // Fall through to the request URL. Invalid env config should not create an open redirect.
    }
  }
  return request.nextUrl.origin;
}

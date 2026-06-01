// Unit tests for the next / OAuth handoff guard SSOT (CMP-582, runbook §11 R6/R11).
//
// Run: `pnpm test` (apps/web).

import { describe, expect, it } from 'vitest';

import {
  DEFAULT_NEXT,
  isSafeNext,
  isSafeOAuthHandoff,
  resolveSafeNext,
  safeSameOriginPath,
} from './safe-redirect.ts';

describe('isSafeNext — legal next destinations preserved (R11)', () => {
  it('accepts a simple absolute in-app path', () => {
    expect(isSafeNext('/app/foo')).toBe(true);
  });

  it('accepts a nested in-app path', () => {
    expect(isSafeNext('/app/reports/123/edit')).toBe(true);
  });

  it('accepts a path with a legitimate query string', () => {
    expect(isSafeNext('/app/leads?tab=open')).toBe(true);
  });

  it('accepts the project root', () => {
    expect(isSafeNext('/')).toBe(true);
  });
});

describe('isSafeNext — open-redirect payloads blocked (R11)', () => {
  it('rejects schema-relative URL `//evil.com`', () => {
    expect(isSafeNext('//evil.com')).toBe(false);
  });

  it('rejects absolute https URL', () => {
    expect(isSafeNext('https://evil.com/steal')).toBe(false);
  });

  it('rejects absolute http URL', () => {
    expect(isSafeNext('http://evil.com/steal')).toBe(false);
  });

  it('rejects javascript: scheme', () => {
    expect(isSafeNext('javascript:alert(1)')).toBe(false);
  });

  it('rejects data: scheme', () => {
    expect(isSafeNext('data:text/html,<script>alert(1)</script>')).toBe(false);
  });

  it('rejects a leading backslash (browser may parse as host)', () => {
    expect(isSafeNext('\\evil.com')).toBe(false);
  });

  it('rejects `/\\evil.com` mixed slash/backslash', () => {
    expect(isSafeNext('/\\evil.com')).toBe(false);
  });

  it('rejects empty string', () => {
    expect(isSafeNext('')).toBe(false);
  });

  it('rejects non-string', () => {
    expect(isSafeNext(undefined)).toBe(false);
    expect(isSafeNext(null)).toBe(false);
    expect(isSafeNext(42)).toBe(false);
    expect(isSafeNext({ next: '/app' })).toBe(false);
  });

  it('rejects values containing CR/LF (response-splitting)', () => {
    expect(isSafeNext('/app\r\nLocation: https://evil.com')).toBe(false);
    expect(isSafeNext('/app\n/foo')).toBe(false);
  });

  it('rejects values containing spaces', () => {
    expect(isSafeNext('/app /foo')).toBe(false);
  });

  it('rejects relative paths missing leading slash', () => {
    expect(isSafeNext('app/foo')).toBe(false);
    expect(isSafeNext('app')).toBe(false);
  });
});

describe('resolveSafeNext — fallback contract', () => {
  it('returns the safe value when valid', () => {
    expect(resolveSafeNext('/app/leads')).toBe('/app/leads');
  });

  it('falls back to DEFAULT_NEXT for invalid values', () => {
    expect(resolveSafeNext('//evil.com')).toBe(DEFAULT_NEXT);
    expect(resolveSafeNext('https://evil.com')).toBe(DEFAULT_NEXT);
    expect(resolveSafeNext(null)).toBe(DEFAULT_NEXT);
    expect(resolveSafeNext(undefined)).toBe(DEFAULT_NEXT);
  });

  it('honors a caller-supplied fallback', () => {
    expect(resolveSafeNext('//evil.com', '/auth/success')).toBe('/auth/success');
  });
});

describe('safeSameOriginPath — same-origin absolute URL normalization', () => {
  const ORIGIN = 'https://www.jippin.com';

  it('accepts same-origin absolute URLs by returning a relative path', () => {
    expect(safeSameOriginPath('https://www.jippin.com/app/reports?a=1#done', ORIGIN)).toBe(
      '/app/reports?a=1#done',
    );
  });

  it('rejects cross-origin URLs', () => {
    expect(safeSameOriginPath('https://evil.com/app/reports', ORIGIN, '/fallback')).toBe(
      '/fallback',
    );
  });
});

describe('isSafeOAuthHandoff — /auth/redirect ?to= guard (R6)', () => {
  const SUPABASE = 'https://abc.supabase.co';

  it('accepts the canonical Supabase OAuth start URL', () => {
    expect(
      isSafeOAuthHandoff(
        'https://abc.supabase.co/auth/v1/authorize?provider=kakao&redirect_to=...',
        SUPABASE,
      ),
    ).toBe(true);
  });

  it('accepts an app same-origin handoff URL', () => {
    expect(
      isSafeOAuthHandoff(
        'https://www.jippin.com/auth/oauth/start?provider=google',
        SUPABASE,
        'https://www.jippin.com',
      ),
    ).toBe(true);
  });

  it('rejects an arbitrary external https origin', () => {
    expect(
      isSafeOAuthHandoff('https://evil.com/steal?cookie=1', SUPABASE),
    ).toBe(false);
  });

  it('rejects a sibling supabase.co subdomain (homograph)', () => {
    expect(
      isSafeOAuthHandoff('https://abc-evil.supabase.co/auth/v1/authorize', SUPABASE),
    ).toBe(false);
    expect(
      isSafeOAuthHandoff('https://abc.supabase.co.evil.com/auth/v1/authorize', SUPABASE),
    ).toBe(false);
  });

  it('rejects http scheme when project is https (downgrade)', () => {
    expect(
      isSafeOAuthHandoff('http://abc.supabase.co/auth/v1/authorize', SUPABASE),
    ).toBe(false);
  });

  it('rejects javascript:/data: schemes', () => {
    expect(isSafeOAuthHandoff('javascript:alert(1)', SUPABASE)).toBe(false);
    expect(isSafeOAuthHandoff('data:text/html,<script>alert(1)</script>', SUPABASE)).toBe(false);
  });

  it('rejects schema-relative URL `//evil.com`', () => {
    expect(isSafeOAuthHandoff('//evil.com/foo', SUPABASE)).toBe(false);
  });

  it('rejects when NEXT_PUBLIC_SUPABASE_URL is missing', () => {
    expect(
      isSafeOAuthHandoff('https://abc.supabase.co/auth/v1/authorize', undefined),
    ).toBe(false);
    expect(
      isSafeOAuthHandoff('https://abc.supabase.co/auth/v1/authorize', ''),
    ).toBe(false);
  });

  it('rejects non-string / empty `to`', () => {
    expect(isSafeOAuthHandoff(null, SUPABASE)).toBe(false);
    expect(isSafeOAuthHandoff(undefined, SUPABASE)).toBe(false);
    expect(isSafeOAuthHandoff('', SUPABASE)).toBe(false);
    expect(isSafeOAuthHandoff(42, SUPABASE)).toBe(false);
  });

  it('accepts a local Supabase dev origin exactly', () => {
    expect(
      isSafeOAuthHandoff('http://localhost:54321/auth/v1/authorize', 'http://localhost:54321'),
    ).toBe(true);
  });

  it('rejects a port mismatch on otherwise-matching host', () => {
    expect(
      isSafeOAuthHandoff('http://localhost:9999/auth/v1/authorize', 'http://localhost:54321'),
    ).toBe(false);
  });
});

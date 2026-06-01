// Unit tests for the next / OAuth handoff guard SSOT (CMP-582, runbook §11 R6/R11).
//
// Run: `pnpm test` (apps/web).

import { strict as assert } from 'node:assert';
import { describe, it } from 'vitest';

import {
  DEFAULT_NEXT,
  isSafeNext,
  isSafeOAuthHandoff,
  resolveSafeNext,
} from './safe-redirect.ts';

describe('isSafeNext — legal next destinations preserved (R11)', () => {
  it('accepts a simple absolute in-app path', () => {
    assert.equal(isSafeNext('/app/foo'), true);
  });

  it('accepts a nested in-app path', () => {
    assert.equal(isSafeNext('/app/reports/123/edit'), true);
  });

  it('accepts a path with a legitimate query string', () => {
    assert.equal(isSafeNext('/app/leads?tab=open'), true);
  });

  it('accepts the project root', () => {
    assert.equal(isSafeNext('/'), true);
  });
});

describe('isSafeNext — open-redirect payloads blocked (R11)', () => {
  it('rejects schema-relative URL `//evil.com`', () => {
    assert.equal(isSafeNext('//evil.com'), false);
  });

  it('rejects absolute https URL', () => {
    assert.equal(isSafeNext('https://evil.com/steal'), false);
  });

  it('rejects absolute http URL', () => {
    assert.equal(isSafeNext('http://evil.com/steal'), false);
  });

  it('rejects javascript: scheme', () => {
    assert.equal(isSafeNext('javascript:alert(1)'), false);
  });

  it('rejects data: scheme', () => {
    assert.equal(isSafeNext('data:text/html,<script>alert(1)</script>'), false);
  });

  it('rejects a leading backslash (browser may parse as host)', () => {
    assert.equal(isSafeNext('\\evil.com'), false);
  });

  it('rejects `/\\evil.com` mixed slash/backslash', () => {
    assert.equal(isSafeNext('/\\evil.com'), false);
  });

  it('rejects empty string', () => {
    assert.equal(isSafeNext(''), false);
  });

  it('rejects non-string', () => {
    assert.equal(isSafeNext(undefined), false);
    assert.equal(isSafeNext(null), false);
    assert.equal(isSafeNext(42), false);
    assert.equal(isSafeNext({ next: '/app' }), false);
  });

  it('rejects values containing CR/LF (response-splitting)', () => {
    assert.equal(isSafeNext('/app\r\nLocation: https://evil.com'), false);
    assert.equal(isSafeNext('/app\n/foo'), false);
  });

  it('rejects values containing spaces', () => {
    assert.equal(isSafeNext('/app /foo'), false);
  });

  it('rejects relative paths missing leading slash', () => {
    assert.equal(isSafeNext('app/foo'), false);
    assert.equal(isSafeNext('app'), false);
  });
});

describe('resolveSafeNext — fallback contract', () => {
  it('returns the safe value when valid', () => {
    assert.equal(resolveSafeNext('/app/leads'), '/app/leads');
  });

  it('falls back to DEFAULT_NEXT for invalid values', () => {
    assert.equal(resolveSafeNext('//evil.com'), DEFAULT_NEXT);
    assert.equal(resolveSafeNext('https://evil.com'), DEFAULT_NEXT);
    assert.equal(resolveSafeNext(null), DEFAULT_NEXT);
    assert.equal(resolveSafeNext(undefined), DEFAULT_NEXT);
  });

  it('honors a caller-supplied fallback', () => {
    assert.equal(resolveSafeNext('//evil.com', '/auth/success'), '/auth/success');
  });
});

describe('isSafeOAuthHandoff — /auth/redirect ?to= guard (R6)', () => {
  const SUPABASE = 'https://abc.supabase.co';

  it('accepts the canonical Supabase OAuth start URL', () => {
    assert.equal(
      isSafeOAuthHandoff(
        'https://abc.supabase.co/auth/v1/authorize?provider=kakao&redirect_to=...',
        SUPABASE,
      ),
      true,
    );
  });

  it('rejects an arbitrary external https origin', () => {
    assert.equal(
      isSafeOAuthHandoff('https://evil.com/steal?cookie=1', SUPABASE),
      false,
    );
  });

  it('rejects a sibling supabase.co subdomain (homograph)', () => {
    assert.equal(
      isSafeOAuthHandoff('https://abc-evil.supabase.co/auth/v1/authorize', SUPABASE),
      false,
    );
    assert.equal(
      isSafeOAuthHandoff('https://abc.supabase.co.evil.com/auth/v1/authorize', SUPABASE),
      false,
    );
  });

  it('rejects http scheme when project is https (downgrade)', () => {
    assert.equal(
      isSafeOAuthHandoff('http://abc.supabase.co/auth/v1/authorize', SUPABASE),
      false,
    );
  });

  it('rejects javascript:/data: schemes', () => {
    assert.equal(isSafeOAuthHandoff('javascript:alert(1)', SUPABASE), false);
    assert.equal(isSafeOAuthHandoff('data:text/html,<script>alert(1)</script>', SUPABASE), false);
  });

  it('rejects schema-relative URL `//evil.com`', () => {
    assert.equal(isSafeOAuthHandoff('//evil.com/foo', SUPABASE), false);
  });

  it('rejects when NEXT_PUBLIC_SUPABASE_URL is missing', () => {
    assert.equal(
      isSafeOAuthHandoff('https://abc.supabase.co/auth/v1/authorize', undefined),
      false,
    );
    assert.equal(
      isSafeOAuthHandoff('https://abc.supabase.co/auth/v1/authorize', ''),
      false,
    );
  });

  it('rejects non-string / empty `to`', () => {
    assert.equal(isSafeOAuthHandoff(null, SUPABASE), false);
    assert.equal(isSafeOAuthHandoff(undefined, SUPABASE), false);
    assert.equal(isSafeOAuthHandoff('', SUPABASE), false);
    assert.equal(isSafeOAuthHandoff(42, SUPABASE), false);
  });

  it('accepts a local Supabase dev origin exactly', () => {
    assert.equal(
      isSafeOAuthHandoff('http://localhost:54321/auth/v1/authorize', 'http://localhost:54321'),
      true,
    );
  });

  it('rejects a port mismatch on otherwise-matching host', () => {
    assert.equal(
      isSafeOAuthHandoff('http://localhost:9999/auth/v1/authorize', 'http://localhost:54321'),
      false,
    );
  });
});

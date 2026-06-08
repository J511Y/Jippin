// Unit tests for the shared error → copy mapping used by `error.tsx` and the
// global query-error toast. Pure function; we feed it pre-normalized ApiError
// instances (parseApiError passes ApiError through unchanged).
//
// Run: `pnpm test` (apps/web).

import { strict as assert } from 'node:assert';
import { describe, it } from 'vitest';

import { ApiError } from './error.ts';
import { resolveErrorContent } from './error-content.ts';

function apiError(status: number | undefined, code = `HTTP_${status}`): ApiError {
  return new ApiError({ code, message: 'raw', status, requestId: 'req-123' });
}

describe('resolveErrorContent — HTTP status classification', () => {
  it('maps 401 to auth (not retryable)', () => {
    const r = resolveErrorContent(apiError(401));
    assert.equal(r.kind, 'auth');
    assert.equal(r.retryable, false);
    assert.equal(r.title, '로그인이 필요해요');
  });

  it('maps 403 to auth (not retryable)', () => {
    const r = resolveErrorContent(apiError(403));
    assert.equal(r.kind, 'auth');
    assert.equal(r.retryable, false);
    assert.equal(r.title, '접근 권한이 없어요');
  });

  it('maps 404 to notfound (not retryable)', () => {
    const r = resolveErrorContent(apiError(404));
    assert.equal(r.kind, 'notfound');
    assert.equal(r.retryable, false);
  });

  it('maps 5xx to server (retryable)', () => {
    const r = resolveErrorContent(apiError(500));
    assert.equal(r.kind, 'server');
    assert.equal(r.retryable, true);
  });

  it('maps 422 to client, surfacing backend message, not retryable', () => {
    const r = resolveErrorContent(new ApiError({ code: 'X', message: '필수값 누락', status: 422 }));
    assert.equal(r.kind, 'client');
    assert.equal(r.retryable, false);
    assert.equal(r.message, '필수값 누락');
  });

  it('maps 429 to client (retryable)', () => {
    const r = resolveErrorContent(apiError(429));
    assert.equal(r.retryable, true);
    assert.equal(r.title, '요청이 너무 많아요');
  });

  it('preserves requestId for support tracing', () => {
    const r = resolveErrorContent(apiError(500));
    assert.equal(r.apiError.requestId, 'req-123');
  });
});

describe('resolveErrorContent — non-HTTP failures', () => {
  it('treats network errors as retryable network kind', () => {
    const r = resolveErrorContent(new ApiError({ code: 'NETWORK_ERROR', message: '...' }));
    assert.equal(r.kind, 'network');
    assert.equal(r.retryable, true);
  });

  it('treats timeouts as network kind', () => {
    const r = resolveErrorContent(new ApiError({ code: 'NETWORK_TIMEOUT', message: '...' }));
    assert.equal(r.kind, 'network');
  });

  it('falls back to a retryable client error for unknown shapes', () => {
    const r = resolveErrorContent(new Error('boom'));
    assert.equal(r.kind, 'client');
    assert.equal(r.retryable, true);
    assert.equal(r.title, '문제가 발생했어요');
  });
});

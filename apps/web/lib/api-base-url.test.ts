import { afterEach, describe, expect, it, vi } from 'vitest';

import { serverApiBaseUrl } from './api-base-url';

function unsetEnv(name: string): void {
  vi.stubEnv(name, undefined);
}

describe('serverApiBaseUrl', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('prefers API_INTERNAL_BASE_URL for server-side calls', () => {
    vi.stubEnv('API_INTERNAL_BASE_URL', 'http://api:8000');
    vi.stubEnv('NEXT_PUBLIC_API_BASE_URL', 'https://public-api.example.com');

    expect(serverApiBaseUrl()).toBe('http://api:8000');
  });

  it('falls back to an absolute NEXT_PUBLIC_API_BASE_URL when internal base is absent', () => {
    unsetEnv('API_INTERNAL_BASE_URL');
    vi.stubEnv('NEXT_PUBLIC_API_BASE_URL', 'https://public-api.example.com');

    expect(serverApiBaseUrl()).toBe('https://public-api.example.com');
  });

  it('fails loud in production when only a relative public API base is configured', () => {
    unsetEnv('API_INTERNAL_BASE_URL');
    vi.stubEnv('NEXT_PUBLIC_API_BASE_URL', '/api');
    vi.stubEnv('NODE_ENV', 'production');

    expect(() => serverApiBaseUrl()).toThrow(/API_INTERNAL_BASE_URL/);
  });
});

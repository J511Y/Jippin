import { describe, expect, it } from 'vitest';

import {
  NAVER_DEFAULT_ENDPOINTS,
  NAVER_DEFAULT_SCOPE,
  NAVER_ENV_KEYS,
  NAVER_PROTOCOL,
  assertNaverIsOAuth2,
  isOidcDiscoveryUrl,
  resolveNaverEndpoints,
  resolveNaverScope
} from '../index';

describe('Naver Custom OAuth2 adapter — OAuth2 (not OIDC)', () => {
  it('declares protocol as oauth2', () => {
    expect(NAVER_PROTOCOL).toBe('oauth2');
  });

  it('default endpoints are Naver OAuth2 authorize/token/userinfo (not OIDC discovery)', () => {
    expect(NAVER_DEFAULT_ENDPOINTS.authorizeUrl).toBe(
      'https://nid.naver.com/oauth2.0/authorize'
    );
    expect(NAVER_DEFAULT_ENDPOINTS.tokenUrl).toBe(
      'https://nid.naver.com/oauth2.0/token'
    );
    expect(NAVER_DEFAULT_ENDPOINTS.userInfoUrl).toBe(
      'https://openapi.naver.com/v1/nid/me'
    );
    for (const value of Object.values(NAVER_DEFAULT_ENDPOINTS)) {
      expect(isOidcDiscoveryUrl(value)).toBe(false);
      expect(value).not.toMatch(/openid-configuration/);
    }
  });

  it('env var keys document NAVER_OAUTH_* names only (no live values, AGENTS.md §4.7 정합)', () => {
    expect(NAVER_ENV_KEYS).toEqual({
      clientId: 'NAVER_OAUTH_CLIENT_ID',
      clientSecret: 'NAVER_OAUTH_CLIENT_SECRET',
      authorizeUrl: 'NAVER_OAUTH_AUTHORIZE_URL',
      tokenUrl: 'NAVER_OAUTH_TOKEN_URL',
      userInfoUrl: 'NAVER_OAUTH_USERINFO_URL',
      scope: 'NAVER_OAUTH_SCOPE'
    });
  });

  it('Phase 1 default scope is "account" (minimum-permission identification-only)', () => {
    expect(NAVER_DEFAULT_SCOPE).toBe('account');
  });

  it('resolveNaverScope falls back to the default when NAVER_OAUTH_SCOPE is unset', () => {
    expect(resolveNaverScope({})).toBe('account');
  });

  it('resolveNaverScope honors NAVER_OAUTH_SCOPE env override (post biz-app approval)', () => {
    expect(resolveNaverScope({ NAVER_OAUTH_SCOPE: 'account,email' })).toBe(
      'account,email'
    );
  });

  it('resolveNaverEndpoints falls back to defaults when env is empty', () => {
    const result = resolveNaverEndpoints({});
    expect(result).toEqual(NAVER_DEFAULT_ENDPOINTS);
  });

  it('resolveNaverEndpoints honors env overrides (Naver-prod relocation drill)', () => {
    const result = resolveNaverEndpoints({
      NAVER_OAUTH_AUTHORIZE_URL: 'https://nid.naver.com/oauth2.0/authorize?v=2',
      NAVER_OAUTH_TOKEN_URL: 'https://nid.naver.com/oauth2.0/token?v=2',
      NAVER_OAUTH_USERINFO_URL: 'https://openapi.naver.com/v1/nid/me?v=2'
    });
    expect(result.authorizeUrl).toBe(
      'https://nid.naver.com/oauth2.0/authorize?v=2'
    );
    expect(result.tokenUrl).toBe('https://nid.naver.com/oauth2.0/token?v=2');
    expect(result.userInfoUrl).toBe(
      'https://openapi.naver.com/v1/nid/me?v=2'
    );
  });

  it('isOidcDiscoveryUrl flags .well-known/openid-configuration paths', () => {
    expect(
      isOidcDiscoveryUrl(
        'https://accounts.google.com/.well-known/openid-configuration'
      )
    ).toBe(true);
    expect(
      isOidcDiscoveryUrl(
        'https://example.com/.well-known/openid-configuration?x=1'
      )
    ).toBe(true);
    expect(isOidcDiscoveryUrl('https://nid.naver.com/oauth2.0/token')).toBe(
      false
    );
  });

  it('assertNaverIsOAuth2 throws if any endpoint smells like OIDC discovery', () => {
    expect(() =>
      assertNaverIsOAuth2({
        authorizeUrl:
          'https://nid.naver.com/.well-known/openid-configuration',
        tokenUrl: NAVER_DEFAULT_ENDPOINTS.tokenUrl,
        userInfoUrl: NAVER_DEFAULT_ENDPOINTS.userInfoUrl
      })
    ).toThrow(/naver_must_be_oauth2_not_oidc/);
  });

  it('assertNaverIsOAuth2 passes for the default Naver OAuth2 endpoints', () => {
    expect(() => assertNaverIsOAuth2(NAVER_DEFAULT_ENDPOINTS)).not.toThrow();
  });
});

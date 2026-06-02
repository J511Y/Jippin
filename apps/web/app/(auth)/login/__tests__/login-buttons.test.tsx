import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { LoginButtons } from '../login-buttons';

vi.mock('@/lib/anonymous-user', () => ({
  getOrCreateAnonymousUserId: vi.fn(async () => '00000000-0000-0000-0000-000000000000')
}));

afterEach(() => {
  cleanup();
});

describe('LoginButtons — provider whitelist UI seal', () => {
  it('renders exactly 1 OAuth provider button (Kakao only)', () => {
    render(<LoginButtons nextPath={null} />);
    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(1);
    expect(screen.getByText('카카오로 시작하기')).toBeDefined();
    expect(screen.queryByText('네이버로 시작하기')).toBeNull();
    expect(screen.queryByText('Google 로 시작하기')).toBeNull();
  });

  it('does not render any email / password / OTP / magic-link input field', () => {
    const { container } = render(<LoginButtons nextPath={null} />);
    const inputs = container.querySelectorAll('input');
    expect(inputs.length).toBe(0);
    for (const inputType of ['email', 'password', 'tel', 'text']) {
      expect(
        container.querySelector(`input[type="${inputType}"]`)
      ).toBeNull();
    }
    expect(container.querySelector('form')).toBeNull();
  });

  it('does not render passwordless / magic-link / OTP CTA text', () => {
    render(<LoginButtons nextPath={null} />);
    expect(screen.queryByText(/이메일.*로그인/i)).toBeNull();
    expect(screen.queryByText(/비밀번호/i)).toBeNull();
    expect(screen.queryByText(/매직 ?링크/i)).toBeNull();
    expect(screen.queryByText(/magic ?link/i)).toBeNull();
    expect(screen.queryByText(/OTP/i)).toBeNull();
    expect(screen.queryByText(/인증번호/i)).toBeNull();
  });
});

describe('LoginButtons — BFF routing (CMP-584 round-5)', () => {
  let assignSpy: ReturnType<typeof vi.fn>;
  const origLocation = window.location;

  beforeEach(() => {
    assignSpy = vi.fn();
    Object.defineProperty(window, 'location', {
      writable: true,
      configurable: true,
      value: {
        ...origLocation,
        origin: 'http://localhost:3000',
        assign: assignSpy
      } as unknown as Location
    });
  });

  afterEach(() => {
    Object.defineProperty(window, 'location', {
      writable: true,
      configurable: true,
      value: origLocation
    });
  });

  it.each(['kakao'] as const)(
    'navigates to same-origin /auth/oauth/start BFF (provider=%s, not to NEXT_PUBLIC_API_BASE_URL)',
    async (provider) => {
      const labels = {
        kakao: '카카오로 시작하기',
      } as const;

      render(<LoginButtons nextPath="/dashboard" />);
      fireEvent.click(screen.getByText(labels[provider]));

      await waitFor(() => {
        expect(assignSpy).toHaveBeenCalledTimes(1);
      });

      const firstCallArgs = assignSpy.mock.calls[0];
      if (!firstCallArgs) throw new Error('assign spy was not called');
      const navigatedTo = String(firstCallArgs[0]);
      const url = new URL(navigatedTo);
      expect(url.origin).toBe('http://localhost:3000');
      expect(url.pathname).toBe('/auth/oauth/start');
      expect(url.searchParams.get('provider')).toBe(provider);
      expect(url.searchParams.get('intent')).toBe('signin');
      expect(url.searchParams.get('next')).toBe('/dashboard');
      expect(url.searchParams.get('anonymous_user_id')).toBe(
        '00000000-0000-0000-0000-000000000000'
      );
      // 정합 검증 — 직접 backend host 로 가지 않음.
      expect(navigatedTo).not.toMatch(/api:8000/);
      expect(navigatedTo).not.toMatch(/localhost:8000/);
    }
  );
});

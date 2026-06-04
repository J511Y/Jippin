import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  getSession: vi.fn(),
}));

vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({
    auth: {
      getSession: mocks.getSession,
    },
  }),
}));

import { LoginButtons } from '../login-buttons';

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
    mocks.getSession.mockResolvedValue({ data: { session: null }, error: null });
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
    mocks.getSession.mockReset();
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
      expect(url.searchParams.has('anonymous_user_id')).toBe(false);
      // 정합 검증 — 직접 backend host 로 가지 않음.
      expect(navigatedTo).not.toMatch(/api:8000/);
      expect(navigatedTo).not.toMatch(/localhost:8000/);
    }
  );

  it('uses link intent when the current Supabase session is anonymous', async () => {
    mocks.getSession.mockResolvedValue({
      data: {
        session: {
          user: {
            id: 'anonymous-user-id',
            is_anonymous: true,
            app_metadata: { provider: 'anonymous', providers: ['anonymous'] },
          },
        },
      },
      error: null,
    });

    render(<LoginButtons nextPath="/reports/preview" />);
    fireEvent.click(screen.getByText('카카오로 시작하기'));

    await waitFor(() => {
      expect(assignSpy).toHaveBeenCalledTimes(1);
    });
    const url = new URL(String(assignSpy.mock.calls[0]?.[0]));
    expect(url.searchParams.get('intent')).toBe('link');
    expect(url.searchParams.get('next')).toBe('/reports/preview');
  });

  it('keeps signin intent for an existing permanent Supabase user', async () => {
    mocks.getSession.mockResolvedValue({
      data: {
        session: {
          user: {
            id: 'permanent-user-id',
            is_anonymous: false,
            app_metadata: { provider: 'kakao', providers: ['kakao'] },
          },
        },
      },
      error: null,
    });

    render(<LoginButtons nextPath="/account" />);
    fireEvent.click(screen.getByText('카카오로 시작하기'));

    await waitFor(() => {
      expect(assignSpy).toHaveBeenCalledTimes(1);
    });
    const url = new URL(String(assignSpy.mock.calls[0]?.[0]));
    expect(url.searchParams.get('intent')).toBe('signin');
    expect(url.searchParams.get('next')).toBe('/account');
  });
});

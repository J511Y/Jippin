import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { LoginButtons } from '../login-buttons';

describe('LoginButtons — provider whitelist UI seal', () => {
  it('renders exactly 3 OAuth provider buttons (Kakao / Naver / Google)', () => {
    render(<LoginButtons nextPath={null} />);
    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(3);
    expect(screen.getByText('카카오로 시작하기')).toBeDefined();
    expect(screen.getByText('네이버로 시작하기')).toBeDefined();
    expect(screen.getByText('Google 로 시작하기')).toBeDefined();
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

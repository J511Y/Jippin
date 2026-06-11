// OAuth 가입 약관 동의 패널 — 만 14세 확인 필수화 회귀 테스트 (PR #107 Codex P2).
// 서버 missing_required_terms 에 age_over_14 가 포함되면 signup form 과 동일 문구의
// 체크박스가 노출되고, 체크 전에는 제출이 차단되어야 한다.
import { cleanup, fireEvent, render, screen, waitFor } from '@/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  replace: vi.fn()
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mocks.replace })
}));

import { TermsAcceptancePanel } from '../terms-acceptance-panel';

const MISSING_TERMS = ['service_terms', 'privacy_policy', 'age_over_14'];

function mockFetch() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith('/auth/me')) {
      return new Response(
        JSON.stringify({
          signup_complete: false,
          missing_required_terms: MISSING_TERMS
        }),
        { status: 200, headers: { 'content-type': 'application/json' } }
      );
    }
    if (url.endsWith('/auth/terms/accept')) {
      return new Response(
        JSON.stringify({
          signup_complete: true,
          missing_required_terms: [],
          claimed_anonymous_user: false
        }),
        { status: 200, headers: { 'content-type': 'application/json' } }
      );
    }
    throw new Error(`unexpected fetch: ${url}`);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  mocks.replace.mockReset();
});

describe('TermsAcceptancePanel — 만 14세 확인 필수 (OAuth 가입 경로)', () => {
  let fetchMock: ReturnType<typeof mockFetch>;

  beforeEach(() => {
    fetchMock = mockFetch();
  });

  it('renders the age_over_14 checkbox with the signup-form wording', async () => {
    render(<TermsAcceptancePanel nextPath="/" />);
    await waitFor(() => {
      expect(screen.getByText('만 14세 이상입니다. (필수)')).toBeDefined();
    });
    expect(screen.getByText('이용약관에 동의합니다. (필수)')).toBeDefined();
    expect(screen.getByText('개인정보처리방침에 동의합니다. (필수)')).toBeDefined();
  });

  it('keeps submit disabled until age_over_14 is checked', async () => {
    render(<TermsAcceptancePanel nextPath="/" />);
    await waitFor(() => {
      expect(screen.getByText('만 14세 이상입니다. (필수)')).toBeDefined();
    });

    const submit = screen.getByRole('button', { name: '동의하고 계속' });
    fireEvent.click(screen.getByText('이용약관에 동의합니다. (필수)'));
    fireEvent.click(screen.getByText('개인정보처리방침에 동의합니다. (필수)'));
    expect((submit as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(screen.getByText('만 14세 이상입니다. (필수)'));
    expect((submit as HTMLButtonElement).disabled).toBe(false);
  });

  it('includes age_over_14 in the /auth/terms/accept payload once checked', async () => {
    render(<TermsAcceptancePanel nextPath="/next-target" />);
    await waitFor(() => {
      expect(screen.getByText('만 14세 이상입니다. (필수)')).toBeDefined();
    });

    for (const label of [
      '이용약관에 동의합니다. (필수)',
      '개인정보처리방침에 동의합니다. (필수)',
      '만 14세 이상입니다. (필수)'
    ]) {
      fireEvent.click(screen.getByText(label));
    }
    fireEvent.click(screen.getByRole('button', { name: '동의하고 계속' }));

    await waitFor(() => {
      expect(mocks.replace).toHaveBeenCalledWith('/next-target');
    });
    const acceptCall = fetchMock.mock.calls.find(([input]) =>
      String(input).endsWith('/auth/terms/accept')
    );
    expect(acceptCall).toBeDefined();
    const body = JSON.parse(String((acceptCall?.[1] as RequestInit).body));
    expect(body.consents).toContainEqual({ term_id: 'age_over_14', agreed: true });
  });
});

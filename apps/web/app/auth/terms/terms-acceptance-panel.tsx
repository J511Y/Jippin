'use client';

import { Alert, Button, Card, Checkbox, Stack, Text } from '@mantine/core';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';

import { apiBaseUrl } from '@/lib/api-base-url';
import { PageColumn, PageHeader } from '@/components/ui';

type AuthMeResponse = {
  signup_complete?: boolean;
  missing_required_terms?: string[];
};

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; missingTerms: string[] }
  | { kind: 'unauthenticated' }
  | { kind: 'error'; message: string };

type TermsAcceptancePanelProps = {
  nextPath: string;
};

// 서버(missing_required_terms)가 내려주는 term_id 의 사용자 노출 문구.
// age_over_14 는 법정 자기확인(개인정보보호법)이라 OAuth 가입 경로에서도 항상 필수이며
// signup form(apps/web/app/(auth)/signup/signup-form.tsx)과 동일한 문구를 쓴다.
export const TERM_LABELS: Record<string, string> = {
  service_terms: '이용약관에 동의합니다. (필수)',
  privacy_policy: '개인정보처리방침에 동의합니다. (필수)',
  age_over_14: '만 14세 이상입니다. (필수)'
};

export function termLabel(termId: string): string {
  return TERM_LABELS[termId] ?? termId;
}

export function TermsAcceptancePanel({ nextPath }: TermsAcceptancePanelProps) {
  const router = useRouter();
  const [state, setState] = useState<LoadState>({ kind: 'loading' });
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const readTermsState = useCallback(async (): Promise<LoadState | { kind: 'complete' }> => {
    try {
      const response = await fetch(`${apiBaseUrl()}/auth/me`, {
        method: 'GET',
        credentials: 'include',
        headers: { accept: 'application/json' }
      });
      if (response.status === 401) {
        return { kind: 'unauthenticated' };
      }
      if (!response.ok) {
        return { kind: 'error', message: `세션 확인 실패 (${response.status})` };
      }
      const data = (await response.json()) as AuthMeResponse;
      const missingTerms = data.missing_required_terms ?? [];
      if (data.signup_complete !== false && missingTerms.length === 0) {
        return { kind: 'complete' };
      }
      return { kind: 'ready', missingTerms };
    } catch (error) {
      return {
        kind: 'error',
        message: error instanceof Error ? error.message : '세션 확인 실패'
      };
    }
  }, []);

  const applyTermsState = useCallback((nextState: LoadState | { kind: 'complete' }) => {
    if (nextState.kind === 'complete') {
      router.replace(nextPath);
      return;
    }
    if (nextState.kind === 'ready') {
      setChecked(Object.fromEntries(nextState.missingTerms.map((termId) => [termId, false])));
    }
    setState(nextState);
  }, [nextPath, router]);

  const loadTerms = useCallback(async () => {
    setSubmitError(null);
    applyTermsState(await readTermsState());
  }, [applyTermsState, readTermsState]);

  useEffect(() => {
    let cancelled = false;
    void readTermsState().then((nextState) => {
      if (!cancelled) {
        applyTermsState(nextState);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [applyTermsState, readTermsState]);

  const allChecked = useMemo(() => {
    return (
      state.kind === 'ready'
      && state.missingTerms.length > 0
      && state.missingTerms.every((termId) => checked[termId])
    );
  }, [checked, state]);

  async function submitTerms() {
    if (state.kind !== 'ready' || !allChecked) {
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const response = await fetch(`${apiBaseUrl()}/auth/terms/accept`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          consents: state.missingTerms.map((termId) => ({
            term_id: termId,
            agreed: true
          }))
        })
      });
      if (!response.ok) {
        setSubmitError(`약관 동의 실패 (${response.status})`);
        return;
      }
      router.replace(nextPath);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : '약관 동의 실패');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    // OAuth 온보딩 중간 단계라 SiteShell(헤더) 없이 독립 레이아웃을 유지한다.
    // 폭·상단 여백은 인증 폼 표준(PageColumn form 560 + 상단 고정)을 따르고,
    // 헤더가 없어 가로 패딩(px)을 자체 부담한다.
    <PageColumn width="form" px="md" py={48}>
      <PageHeader
        title="필수 약관 동의"
        subtitle="계정 생성을 완료하려면 아래 필수 약관에 동의해 주세요."
      />

      {state.kind === 'loading' ? (
        <Text size="sm" c="dimmed">
          확인 중...
        </Text>
      ) : null}

      {state.kind === 'unauthenticated' ? (
        <Card withBorder>
          <Stack gap="sm" align="flex-start">
            <Text size="sm">로그인 세션이 만료되었습니다.</Text>
            <Button
              type="button"
              variant="light"
              color="jippin"
              size="md"
              mih={44}
              onClick={() => router.replace(`/login?next=${encodeURIComponent(nextPath)}`)}
            >
              다시 로그인
            </Button>
          </Stack>
        </Card>
      ) : null}

      {state.kind === 'error' ? (
        <Alert color="danger" variant="light">
          <Stack gap="sm" align="flex-start">
            <Text size="sm" c="danger.8">
              {state.message}
            </Text>
            {/* light 는 Alert 의 danger 틴트 배경과 같은 색이라 버튼이 묻힌다 — outline. */}
            <Button
              type="button"
              variant="outline"
              color="danger"
              size="md"
              mih={44}
              onClick={() => {
                setState({ kind: 'loading' });
                void loadTerms();
              }}
            >
              다시 시도
            </Button>
          </Stack>
        </Alert>
      ) : null}

      {state.kind === 'ready' ? (
        <Card withBorder>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void submitTerms();
            }}
          >
            <Stack gap="md">
              <Stack gap={4}>
                {state.missingTerms.map((termId) => (
                  <Checkbox
                    key={termId}
                    size="md"
                    checked={Boolean(checked[termId])}
                    onChange={(event) =>
                      setChecked((current) => ({
                        ...current,
                        [termId]: event.target.checked
                      }))
                    }
                    label={termLabel(termId)}
                    // 모바일 터치 타깃 ≥44px — 라벨 행 전체를 히트 영역으로 키운다.
                    styles={{
                      body: { alignItems: 'center' },
                      label: {
                        display: 'flex',
                        alignItems: 'center',
                        minHeight: 44,
                        cursor: 'pointer'
                      },
                      input: { cursor: 'pointer' }
                    }}
                  />
                ))}
              </Stack>
              {submitError ? (
                <Text size="sm" c="danger.6">
                  {submitError}
                </Text>
              ) : null}
              <Button
                type="submit"
                color="jippin"
                size="md"
                mih={44}
                fullWidth
                disabled={!allChecked || submitting}
              >
                {submitting ? '저장 중...' : '동의하고 계속'}
              </Button>
            </Stack>
          </form>
        </Card>
      ) : null}
    </PageColumn>
  );
}

import { Anchor, Box, Container, Group, Stack, Text } from '@mantine/core';

/**
 * AGENTS.md §4.6 — 모든 리포트 화면·다운로드 산출물에 노출되어야 하는 법적 고지.
 * 본 컴포넌트는 base layout 에서 항상 렌더되며, 리포트/공유 산출물에서 재사용한다.
 *
 * - `inline` (결과 카드 등 본문 컨텍스트): caption(13/20). 면책은 실제로 읽혀야 하므로
 *   result-card 안에서는 한 단계 크게 노출한다.
 * - `footer` (페이지 푸터): 네이버식 컴팩트 푸터(약관·개인정보 링크 + 법적 고지 1줄 + 카피라이트).
 */
export const LEGAL_NOTICE_TEXT =
  '본 서비스는 AI 기반 사전 검토 시스템입니다. 최종 행위허가 여부는 관할 행정기관 판단에 따라 달라질 수 있습니다.';

type LegalNoticeProps = {
  className?: string;
  variant?: 'inline' | 'footer';
};

export function LegalNotice({ className, variant = 'footer' }: LegalNoticeProps) {
  if (variant === 'inline') {
    return (
      <Box
        component="aside"
        role="note"
        aria-label="법적 고지"
        data-testid="legal-notice"
        className={className}
        px="sm"
        py="xs"
        style={{
          background: 'var(--mantine-color-gray-0)',
          borderRadius: 'var(--mantine-radius-md)',
          wordBreak: 'keep-all',
          overflowWrap: 'break-word'
        }}
      >
        <Text c="var(--jippin-notice-legal)" fz="13px" lh="1.25rem">
          {LEGAL_NOTICE_TEXT}
        </Text>
      </Box>
    );
  }

  return (
    <Box
      component="footer"
      data-testid="legal-notice"
      className={className}
      style={{
        borderTop: '1px solid var(--jippin-brand-border)',
        background: 'var(--jippin-brand-surface-alt)'
      }}
    >
      <Container size="lg" py="md">
        <Stack gap={6}>
          <Group justify="space-between" align="center" wrap="wrap" gap="xs">
            <Group gap="xs" align="center" wrap="wrap">
              <Anchor
                href="/terms"
                size="xs"
                fw={600}
                c="var(--jippin-brand-copy)"
                underline="never"
              >
                이용약관
              </Anchor>
              <Text size="xs" c="dimmed">
                ·
              </Text>
              <Anchor
                href="/privacy"
                size="xs"
                fw={600}
                c="var(--jippin-brand-copy)"
                underline="never"
              >
                개인정보처리방침
              </Anchor>
            </Group>
            <Text size="xs" c="dimmed">
              © 2026 집핀(Jippin)
            </Text>
          </Group>
          <Text
            c="var(--jippin-notice-legal)"
            fz="11px"
            lh="1.1rem"
            style={{ wordBreak: 'keep-all', overflowWrap: 'break-word' }}
          >
            {LEGAL_NOTICE_TEXT}
          </Text>
        </Stack>
      </Container>
    </Box>
  );
}

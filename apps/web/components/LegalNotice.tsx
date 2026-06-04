import { Box, Text } from '@mantine/core';

/**
 * AGENTS.md §4.6 — 모든 리포트 화면·다운로드 산출물에 노출되어야 하는 법적 고지.
 * 본 컴포넌트는 base layout 에서 항상 렌더되며, 리포트/공유 산출물에서 재사용한다.
 */
export const LEGAL_NOTICE_TEXT =
  '본 서비스는 AI 기반 사전 검토 시스템입니다. 최종 행위허가 여부는 관할 행정기관 판단에 따라 달라질 수 있습니다.';

type LegalNoticeProps = {
  className?: string;
  variant?: 'inline' | 'footer';
};

export function LegalNotice({ className, variant = 'footer' }: LegalNoticeProps) {
  return (
    <Box
      component="aside"
      role="note"
      aria-label="법적 고지"
      data-testid="legal-notice"
      className={className}
      px={variant === 'footer' ? 'lg' : 'sm'}
      py={variant === 'footer' ? 'md' : 'xs'}
      style={{
        background: variant === 'inline' ? 'var(--mantine-color-gray-0)' : 'transparent',
        borderTop: variant === 'footer' ? '1px solid var(--jippin-brand-border)' : undefined,
        borderRadius: variant === 'inline' ? 'var(--mantine-radius-md)' : undefined
      }}
    >
      <Text c="var(--jippin-notice-legal)" lh="1.25rem" size="xs">
        {LEGAL_NOTICE_TEXT}
      </Text>
    </Box>
  );
}

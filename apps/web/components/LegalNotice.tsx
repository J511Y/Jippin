import { Box, Text } from '@mantine/core';

/**
 * AGENTS.md §4.6 — 모든 리포트 화면·다운로드 산출물에 노출되어야 하는 법적 고지.
 * 본 컴포넌트는 base layout 에서 항상 렌더되며, 리포트/공유 산출물에서 재사용한다.
 *
 * 가독성 정책 (디자인 QA 2026-06-05, docs/design/TYPOGRAPHY.md §3 동기화):
 * - `inline` (결과 카드 등 본문 컨텍스트): `caption` (13/20). 면책은 실제로 읽혀야 하므로
 *   result-card 안에서는 한 단계 크게 노출한다.
 * - `footer` (페이지 푸터): `legal` (12/20). 항시 노출되는 footer fine print.
 */
export const LEGAL_NOTICE_TEXT =
  '본 서비스는 AI 기반 사전 검토 시스템입니다. 최종 행위허가 여부는 관할 행정기관 판단에 따라 달라질 수 있습니다.';

type LegalNoticeProps = {
  className?: string;
  variant?: 'inline' | 'footer';
};

export function LegalNotice({ className, variant = 'footer' }: LegalNoticeProps) {
  const isInline = variant === 'inline';
  return (
    <Box
      component="aside"
      role="note"
      aria-label="법적 고지"
      data-testid="legal-notice"
      className={className}
      px={isInline ? 'sm' : 'lg'}
      py={isInline ? 'xs' : 'md'}
      style={{
        background: isInline ? 'var(--mantine-color-gray-0)' : 'transparent',
        borderTop: isInline ? undefined : '1px solid var(--jippin-brand-border)',
        borderRadius: isInline ? 'var(--mantine-radius-md)' : undefined,
        // 한국어 어절 보존: 약관·면책 문구가 어절 중간에서 끊기지 않도록 한다.
        wordBreak: 'keep-all',
        overflowWrap: 'break-word'
      }}
    >
      {/* caption (13/20) for inline, legal (12/20) for footer — TYPOGRAPHY.md §2 토큰과 정합. */}
      <Text c="var(--jippin-notice-legal)" fz={isInline ? '13px' : '12px'} lh="1.25rem">
        {LEGAL_NOTICE_TEXT}
      </Text>
    </Box>
  );
}

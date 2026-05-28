import { clsx } from 'clsx';

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
    <aside
      role="note"
      aria-label="법적 고지"
      data-testid="legal-notice"
      className={clsx(
        'text-xs leading-relaxed text-slate-500',
        variant === 'footer' && 'border-t border-slate-200 px-6 py-4',
        variant === 'inline' && 'rounded-md bg-slate-50 px-3 py-2',
        className
      )}
    >
      {LEGAL_NOTICE_TEXT}
    </aside>
  );
}

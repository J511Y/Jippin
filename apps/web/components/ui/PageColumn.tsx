import { Box, type BoxProps } from '@mantine/core';
import type { ReactNode } from 'react';

/**
 * 페이지 내부 콘텐츠 폭 표준 (DESIGN.md §4.5 개정 — 레이아웃 컨테이너 폭).
 *
 * 바깥 Container 는 전 페이지 lg(헤더와 동일)로 고정해 페이지 전환 시 시각
 * 앵커(배경·헤더 정렬)가 움직이지 않게 하고, 좁아야 하는 콘텐츠는 컨테이너가
 * 아니라 이 내부 컬럼으로 좁힌다.
 *
 * - full   : 목록·리포트·랜딩 (제한 없음)
 * - prose  : 읽기 컬럼 — 약관·개인정보처리방침·긴 문서 (720px)
 * - form   : 단일 입력 폼 — 로그인·가입·상담 신청 (560px)
 * - funnel : 원-퀘스천 퍼널 — 우리집 체크 (460px)
 */
const WIDTHS = {
  full: undefined,
  prose: 720,
  form: 560,
  funnel: 460
} as const;

export type PageColumnWidth = keyof typeof WIDTHS;

export function PageColumn({
  width = 'full',
  children,
  ...rest
}: BoxProps & { width?: PageColumnWidth; children: ReactNode }) {
  return (
    <Box maw={WIDTHS[width]} mx="auto" w="100%" {...rest}>
      {children}
    </Box>
  );
}

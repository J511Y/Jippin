'use client';

import { useRouter } from 'next/navigation';
import type { ReactNode } from 'react';

import { TableRow } from '@/components/ui/table';

/**
 * 행 전체 클릭으로 상세 페이지에 진입하는 테이블 행 (CMP-DIRECT).
 * 행 안의 인터랙티브 요소(셀렉트 등)는 stopPropagation 으로 자체 처리한다.
 */
export function ClickableRow({ href, children }: { href: string; children: ReactNode }) {
  const router = useRouter();
  return (
    <TableRow className="cursor-pointer" onClick={() => router.push(href)}>
      {children}
    </TableRow>
  );
}

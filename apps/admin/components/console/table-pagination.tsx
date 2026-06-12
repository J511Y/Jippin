'use client';

import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import type { MouseEvent } from 'react';

import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious
} from '@/components/ui/pagination';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';
import { cn } from '@/lib/utils';

export const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const;

/** 1 … (current±1) … last 형태의 페이지 번호 목록. */
function pageItems(page: number, lastPage: number): Array<number | 'ellipsis'> {
  const pages = new Set<number>([1, lastPage, page - 1, page, page + 1]);
  const sorted = [...pages].filter((p) => p >= 1 && p <= lastPage).sort((a, b) => a - b);
  const items: Array<number | 'ellipsis'> = [];
  let prev = 0;
  for (const p of sorted) {
    if (prev && p - prev > 1) items.push('ellipsis');
    items.push(p);
    prev = p;
  }
  return items;
}

/**
 * 리스트 공용 페이지네이션 (CMP-DIRECT) — shadcn Pagination 프리미티브 기반.
 * 1페이지뿐이어도 항상 노출하고, 페이지당 행 수(size)를 셀렉트로 조절한다.
 * page/size 는 URL searchParams 로 유지된다.
 */
export function TablePagination({
  page,
  lastPage,
  total,
  pageSize,
  unitLabel = '건'
}: {
  page: number;
  lastPage: number;
  total: number;
  pageSize: number;
  unitLabel?: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  function buildHref(patch: { page?: number; size?: number }): string {
    const params = new URLSearchParams(searchParams.toString());
    if (patch.size !== undefined) {
      params.set('size', String(patch.size));
      params.delete('page'); // 사이즈 변경 시 1페이지로
    }
    if (patch.page !== undefined) {
      if (patch.page > 1) params.set('page', String(patch.page));
      else params.delete('page');
    }
    return params.size ? `${pathname}?${params.toString()}` : pathname;
  }

  function navigate(event: MouseEvent<HTMLAnchorElement>, href: string) {
    event.preventDefault(); // 풀 리로드 대신 SPA 네비게이션
    router.replace(href);
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-3">
        <p className="text-muted-foreground text-xs whitespace-nowrap">
          총 {total.toLocaleString('ko-KR')}
          {unitLabel}
        </p>
        <Select
          value={String(pageSize)}
          onValueChange={(next) => {
            if (next) router.replace(buildHref({ size: Number(next) }));
          }}
        >
          <SelectTrigger size="sm" className="w-32">
            <SelectValue>{pageSize}개씩 보기</SelectValue>
          </SelectTrigger>
          <SelectContent>
            {PAGE_SIZE_OPTIONS.map((option) => (
              <SelectItem key={option} value={String(option)}>
                {option}개씩 보기
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Pagination className="mx-0 w-auto justify-end">
        <PaginationContent>
          <PaginationItem>
            <PaginationPrevious
              text="이전"
              href={buildHref({ page: page - 1 })}
              onClick={(event) => navigate(event, buildHref({ page: page - 1 }))}
              aria-disabled={page <= 1}
              className={cn(page <= 1 && 'pointer-events-none opacity-50')}
            />
          </PaginationItem>
          {pageItems(page, lastPage).map((item, index) =>
            item === 'ellipsis' ? (
              // eslint-disable-next-line react/no-array-index-key
              <PaginationItem key={`ellipsis-${index}`}>
                <PaginationEllipsis />
              </PaginationItem>
            ) : (
              <PaginationItem key={item}>
                <PaginationLink
                  href={buildHref({ page: item })}
                  onClick={(event) => navigate(event, buildHref({ page: item }))}
                  isActive={item === page}
                >
                  {item}
                </PaginationLink>
              </PaginationItem>
            )
          )}
          <PaginationItem>
            <PaginationNext
              text="다음"
              href={buildHref({ page: page + 1 })}
              onClick={(event) => navigate(event, buildHref({ page: page + 1 }))}
              aria-disabled={page >= lastPage}
              className={cn(page >= lastPage && 'pointer-events-none opacity-50')}
            />
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    </div>
  );
}

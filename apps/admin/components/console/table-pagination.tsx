'use client';

import { ChevronLeft, ChevronRight } from 'lucide-react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';

import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';

export const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const;

/**
 * 리스트 공용 페이지네이션 (CMP-DIRECT).
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

  function navigate(patch: { page?: number; size?: number }) {
    const params = new URLSearchParams(searchParams.toString());
    if (patch.size !== undefined) {
      params.set('size', String(patch.size));
      params.delete('page'); // 사이즈 변경 시 1페이지로
    }
    if (patch.page !== undefined) {
      if (patch.page > 1) params.set('page', String(patch.page));
      else params.delete('page');
    }
    router.replace(params.size ? `${pathname}?${params.toString()}` : pathname);
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-muted-foreground text-xs">
        총 {total.toLocaleString('ko-KR')}
        {unitLabel} · {page} / {lastPage} 페이지
      </p>
      <div className="flex items-center gap-2">
        <Select
          value={String(pageSize)}
          onValueChange={(next) => {
            if (next) navigate({ size: Number(next) });
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
        <Button
          variant="outline"
          size="sm"
          disabled={page <= 1}
          onClick={() => navigate({ page: page - 1 })}
        >
          <ChevronLeft className="size-3.5" /> 이전
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={page >= lastPage}
          onClick={() => navigate({ page: page + 1 })}
        >
          다음 <ChevronRight className="size-3.5" />
        </Button>
      </div>
    </div>
  );
}

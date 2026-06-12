'use client';

import { SearchIcon, XIcon } from 'lucide-react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

/** 회원 검색 바 — 이메일/이름을 URL searchParams 로 유지 (CMP-DIRECT). */
export function UserSearch({ q }: { q?: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [term, setTerm] = useState(q ?? '');

  function apply(next: string | undefined) {
    const params = new URLSearchParams(searchParams.toString());
    if (next) params.set('q', next);
    else params.delete('q');
    params.delete('page');
    router.replace(params.size ? `${pathname}?${params.toString()}` : pathname);
  }

  function onSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    apply(term.trim() || undefined);
  }

  return (
    <div className="flex items-center gap-2">
      <form onSubmit={onSearch} className="relative">
        <SearchIcon className="text-muted-foreground absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
        <Input
          value={term}
          onChange={(event) => setTerm(event.target.value)}
          placeholder="이메일·이름 검색"
          className="h-8 w-64 pl-8"
        />
      </form>
      {q ? (
        <Button
          variant="ghost"
          size="sm"
          className="text-muted-foreground"
          onClick={() => {
            setTerm('');
            apply(undefined);
          }}
        >
          <XIcon className="size-3.5" />
          초기화
        </Button>
      ) : null}
    </div>
  );
}

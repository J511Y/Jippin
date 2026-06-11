'use client';

import {
  Badge,
  Box,
  Group,
  Highlight,
  Pagination,
  Stack,
  Text,
  TextInput,
  UnstyledButton
} from '@mantine/core';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useMemo, useState } from 'react';

import {
  FAQ_CATEGORY_LABELS,
  FAQ_CATEGORY_ORDER,
  type FaqCategory,
  type FaqItem
} from '@/lib/faq';

/** 한 페이지에 보여줄 질문 수 — 이를 넘으면 페이징 컨트롤을 노출한다. */
const PAGE_SIZE = 5;

type CategoryFilter = FaqCategory | 'all';

function isCategoryFilter(value: string | null): value is CategoryFilter {
  return value === 'all' || (value !== null && value in FAQ_CATEGORY_LABELS);
}

/**
 * 자주묻는질문 목록 브라우저 — 카테고리 필터 + 질문 검색(하이라이팅) + 페이징.
 *
 * 서버 컴포넌트(`/faq`)에서 전체 목록(현재 44건)을 받아 클라이언트에서 필터링한다.
 * 질문을 클릭하면 상세(`/faq/{faqId}`)로 이동한다. 필터·검색어·페이지는 URL 쿼리
 * (`?category=&q=&page=`)와 동기화해 공유·새로고침에도 유지된다(`router.replace`
 * 라 히스토리는 쌓지 않는다).
 */
export function FaqBrowser({ items }: { items: FaqItem[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [category, setCategory] = useState<CategoryFilter>(() => {
    const raw = searchParams.get('category');
    return isCategoryFilter(raw) ? raw : 'all';
  });
  const [query, setQuery] = useState(() => searchParams.get('q') ?? '');
  const [page, setPage] = useState(() => {
    const raw = Number(searchParams.get('page'));
    return Number.isInteger(raw) && raw >= 1 ? raw : 1;
  });

  /** 상태 변경을 URL 쿼리에 반영한다(기본값은 쿼리에서 생략해 URL 을 짧게 유지). */
  const syncUrl = (next: { category: CategoryFilter; q: string; page: number }) => {
    const params = new URLSearchParams();
    if (next.category !== 'all') params.set('category', next.category);
    if (next.q.trim()) params.set('q', next.q.trim());
    if (next.page > 1) params.set('page', String(next.page));
    const qs = params.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  const handleCategory = (value: CategoryFilter) => {
    setCategory(value);
    setPage(1);
    syncUrl({ category: value, q: query, page: 1 });
  };

  const handleQuery = (value: string) => {
    setQuery(value);
    setPage(1);
    syncUrl({ category, q: value, page: 1 });
  };

  const handlePage = (value: number) => {
    setPage(value);
    syncUrl({ category, q: query, page: value });
  };

  const keyword = query.trim();
  const filtered = useMemo(() => {
    const lowered = keyword.toLowerCase();
    return items.filter(
      (item) =>
        (category === 'all' || item.categories.includes(category)) &&
        (lowered === '' || item.question.toLowerCase().includes(lowered))
    );
  }, [items, category, keyword]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const visible = filtered.slice(
    (currentPage - 1) * PAGE_SIZE,
    currentPage * PAGE_SIZE
  );

  return (
    <Stack gap="md">
      <TextInput
        value={query}
        onChange={(event) => handleQuery(event.currentTarget.value)}
        placeholder="궁금한 내용을 검색해 보세요 (예: 비용, 행위허가, 방화)"
        aria-label="자주묻는질문 검색"
        size="md"
        radius="md"
      />

      {/* 카테고리 필터 칩 — 전체 + 카테고리 순서(라벨은 lib/faq.ts 소유). */}
      <Group gap="xs" wrap="wrap">
        {(['all', ...FAQ_CATEGORY_ORDER] as CategoryFilter[]).map((value) => {
          const active = category === value;
          return (
            <UnstyledButton
              key={value}
              onClick={() => handleCategory(value)}
              aria-pressed={active}
              fz="sm"
              fw={600}
              c={active ? 'white' : 'var(--jippin-brand-primary)'}
              bg={active ? 'var(--jippin-brand-primary)' : 'transparent'}
              style={{
                padding: '4px 12px',
                borderRadius: 'var(--mantine-radius-xl)',
                border: '1px solid var(--jippin-brand-border)'
              }}
            >
              {value === 'all' ? '전체' : FAQ_CATEGORY_LABELS[value]}
            </UnstyledButton>
          );
        })}
      </Group>

      <Text size="sm" c="dimmed">
        총 {filtered.length}개의 질문
        {keyword ? ` — "${keyword}" 검색 결과` : ''}
      </Text>

      {/* 질문 목록 — 클릭 시 상세(/faq/{id})로 이동. */}
      <Stack
        gap={0}
        style={{
          border: '1px solid var(--jippin-brand-border)',
          borderRadius: 'var(--mantine-radius-md)',
          overflow: 'hidden'
        }}
      >
        {visible.length === 0 ? (
          <Text p="lg" c="dimmed" ta="center">
            검색 결과가 없습니다. 다른 검색어나 카테고리를 선택해 보세요.
          </Text>
        ) : (
          visible.map((item, index) => (
            <Box
              key={item.id}
              component={Link}
              href={`/faq/${item.id}`}
              p="md"
              style={{
                display: 'block',
                textDecoration: 'none',
                color: 'inherit',
                borderTop:
                  index === 0
                    ? undefined
                    : '1px solid var(--jippin-brand-border)'
              }}
            >
              <Stack gap={6}>
                <Group gap={6}>
                  {item.categories.map((slug) => (
                    <Badge key={slug} variant="light" size="sm" radius="sm">
                      {FAQ_CATEGORY_LABELS[slug]}
                    </Badge>
                  ))}
                </Group>
                <Group gap={8} wrap="nowrap" align="flex-start">
                  <Text fw={700} c="var(--jippin-brand-primary)">
                    Q.
                  </Text>
                  <Highlight
                    highlight={keyword}
                    fw={600}
                    style={{ wordBreak: 'keep-all' }}
                  >
                    {item.question}
                  </Highlight>
                </Group>
              </Stack>
            </Box>
          ))
        )}
      </Stack>

      {filtered.length > PAGE_SIZE ? (
        <Group justify="center">
          <Pagination
            total={totalPages}
            value={currentPage}
            onChange={handlePage}
            radius="md"
          />
        </Group>
      ) : null}
    </Stack>
  );
}

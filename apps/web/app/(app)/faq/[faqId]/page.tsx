import {
  Anchor,
  Box,
  Button,
  Divider,
  Group,
  Stack,
  Text,
  Title
} from '@mantine/core';
import { IconChevronRight } from '@tabler/icons-react';
import type { Metadata } from 'next';
import { notFound } from 'next/navigation';

import { FaqAnswer } from '@/components/faq/FaqAnswer';
import {
  FAQ_CATEGORY_LABELS,
  fetchFaqById,
  fetchFaqs,
  stripMarkdown,
  type FaqItem
} from '@/lib/faq';
import { absoluteUrl, safeJsonLd, SITE_URL } from '@/lib/site';

type FaqDetailPageProps = {
  params: Promise<{ faqId: string }>;
};

// 목록과 동일하게 백엔드 콘텐츠를 ISR(revalidate 300s)로 캐시한다.
export const revalidate = 300;

/** URL 파라미터를 identity 정수 id 로 좁힌다(아니면 null → 404). */
function parseFaqId(raw: string): number | null {
  return /^\d+$/.test(raw) ? Number(raw) : null;
}

/** 카테고리가 겹치는 다른 질문 — 상세 하단 "관련 질문" + 내부 링크(SEO). */
function relatedFaqs(item: FaqItem, all: FaqItem[], limit = 5): FaqItem[] {
  return all
    .filter(
      (other) =>
        other.id !== item.id &&
        other.categories.some((slug) => item.categories.includes(slug))
    )
    .slice(0, limit);
}

function buildDetailJsonLd(item: FaqItem): Record<string, unknown>[] {
  return [
    {
      '@context': 'https://schema.org',
      '@type': 'FAQPage',
      '@id': `${SITE_URL}/faq/${item.id}#faqpage`,
      url: absoluteUrl(`/faq/${item.id}`),
      mainEntity: [
        {
          '@type': 'Question',
          name: item.question,
          acceptedAnswer: {
            '@type': 'Answer',
            text: stripMarkdown(item.answer)
          }
        }
      ]
    },
    {
      '@context': 'https://schema.org',
      '@type': 'BreadcrumbList',
      itemListElement: [
        {
          '@type': 'ListItem',
          position: 1,
          name: '자주묻는질문',
          item: absoluteUrl('/faq')
        },
        {
          '@type': 'ListItem',
          position: 2,
          name: item.question,
          item: absoluteUrl(`/faq/${item.id}`)
        }
      ]
    }
  ];
}

export async function generateMetadata({
  params
}: FaqDetailPageProps): Promise<Metadata> {
  const { faqId } = await params;
  const id = parseFaqId(faqId);
  const item = id === null ? null : await fetchFaqById(id);
  if (!item) return { title: '자주묻는질문' };

  const description = stripMarkdown(item.answer).slice(0, 160);
  return {
    title: item.question,
    description,
    alternates: { canonical: `/faq/${item.id}` },
    openGraph: {
      title: `${item.question} — 집핀`,
      description,
      url: `/faq/${item.id}`
    }
  };
}

export default async function FaqDetailPage({ params }: FaqDetailPageProps) {
  const { faqId } = await params;
  const id = parseFaqId(faqId);
  if (id === null) notFound();

  const item = await fetchFaqById(id);
  if (!item) notFound();

  const related = relatedFaqs(item, await fetchFaqs());
  const jsonLd = buildDetailJsonLd(item);

  return (
    <Stack gap="lg" component="article">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: safeJsonLd(jsonLd) }}
      />

      {/* 빵부스러기(좌) + 뒤로가기(우) — 보조 내비게이션이라 중립 색으로 둔다. */}
      <Group justify="space-between" align="center">
        <Group gap={6}>
          <Anchor href="/faq" size="sm" c="dimmed" underline="hover">
            자주묻는질문
          </Anchor>
          <Text span size="sm" c="dimmed">
            /
          </Text>
          <Text span size="sm" c="dimmed">
            {item.categories
              .map((slug) => FAQ_CATEGORY_LABELS[slug])
              .join(' · ')}
          </Text>
        </Group>
        <Anchor href="/faq" size="sm" c="dimmed" underline="hover">
          ← 목록으로
        </Anchor>
      </Group>

      {/* 본문 카드 — 흰 표면으로 페이지 배경과 구분한다. */}
      <Box
        p={{ base: 'lg', sm: 'xl' }}
        style={{
          background: 'var(--jippin-brand-surface-alt)',
          border: '1px solid var(--jippin-brand-border)',
          borderRadius: 'var(--mantine-radius-lg)'
        }}
      >
        <Stack gap="md">
          <Title
            order={1}
            c="var(--jippin-brand-ink)"
            style={{ wordBreak: 'keep-all' }}
          >
            {item.question}
          </Title>
          <Divider color="var(--jippin-brand-border)" />
          <FaqAnswer markdown={item.answer} />
        </Stack>
      </Box>

      <Divider color="var(--jippin-brand-border)" />

      {/* 상담 유도 — 카드 없이 본문 흐름에 둔다. 강조(primary)는 버튼 하나에만. */}
      <Stack gap="sm" component="section">
        <Title order={2} fz="h3" c="var(--jippin-brand-ink)">
          더 궁금한 점이 있으신가요?
        </Title>
        <Text
          size="sm"
          c="var(--jippin-brand-copy)"
          style={{ wordBreak: 'keep-all' }}
        >
          평면도 한 장이면 1분 안에 철거·확장 가능성을 무료로 확인할 수 있어요.
          자세한 내용은 전문가 상담으로 이어가세요.
        </Text>
        <Group gap="sm">
          <Button component="a" href="/sessions/new" radius="md">
            무료로 사전검토 시작
          </Button>
          <Button component="a" href="/leads/new" variant="default" radius="md">
            전문가 상담
          </Button>
        </Group>
      </Stack>

      <Divider color="var(--jippin-brand-border)" />

      {/* 관련 질문 — 같은 카테고리 내부 링크, 표처럼 행 구분선으로 나눈다. */}
      {related.length > 0 ? (
        <Stack gap="sm" component="section">
          <Title order={2} fz="h3" c="var(--jippin-brand-ink)">
            관련 질문
          </Title>
          <Stack
            gap={0}
            style={{
              background: 'var(--jippin-brand-surface-alt)',
              border: '1px solid var(--jippin-brand-border)',
              borderRadius: 'var(--mantine-radius-lg)',
              overflow: 'hidden'
            }}
          >
            {related.map((other, index) => (
              <Box
                key={other.id}
                component="a"
                href={`/faq/${other.id}`}
                data-faq-row
                px="lg"
                py="sm"
                style={{
                  display: 'block',
                  textDecoration: 'none',
                  borderTop:
                    index === 0
                      ? undefined
                      : '1px solid var(--jippin-brand-border)'
                }}
              >
                <Group gap="sm" wrap="nowrap" justify="space-between" align="center">
                  <Text
                    fw={500}
                    c="var(--jippin-brand-copy)"
                    style={{ wordBreak: 'keep-all' }}
                  >
                    {other.question}
                  </Text>
                  <IconChevronRight
                    size={16}
                    aria-hidden
                    style={{ flexShrink: 0, color: 'var(--jippin-brand-copy)' }}
                  />
                </Group>
              </Box>
            ))}
          </Stack>
        </Stack>
      ) : null}
    </Stack>
  );
}

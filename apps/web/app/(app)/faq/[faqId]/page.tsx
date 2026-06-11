import { Anchor, Badge, Group, Stack, Title } from '@mantine/core';
import type { Metadata } from 'next';
import { notFound } from 'next/navigation';

import { FaqAnswer } from '@/components/faq/FaqAnswer';
import { FAQ_CATEGORY_LABELS, fetchFaqById, stripMarkdown } from '@/lib/faq';

type FaqDetailPageProps = {
  params: Promise<{ faqId: string }>;
};

// 목록과 동일하게 백엔드 콘텐츠를 ISR(revalidate 300s)로 캐시한다.
export const revalidate = 300;

/** URL 파라미터를 identity 정수 id 로 좁힌다(아니면 null → 404). */
function parseFaqId(raw: string): number | null {
  return /^\d+$/.test(raw) ? Number(raw) : null;
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

  return (
    <Stack gap="lg">
      <Anchor href="/faq" size="sm" c="var(--jippin-brand-primary)" fw={600}>
        ← 자주묻는질문 목록으로
      </Anchor>

      <Stack gap="xs">
        <Group gap={6}>
          {item.categories.map((slug) => (
            <Badge key={slug} variant="light" size="sm" radius="sm">
              {FAQ_CATEGORY_LABELS[slug]}
            </Badge>
          ))}
        </Group>
        <Title order={1} fz="1.5rem" style={{ wordBreak: 'keep-all' }}>
          {item.question}
        </Title>
      </Stack>

      <FaqAnswer markdown={item.answer} />
    </Stack>
  );
}

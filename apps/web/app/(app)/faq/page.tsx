import { Stack, Text, Title } from '@mantine/core';
import type { Metadata } from 'next';

import { FaqView } from '@/components/faq/FaqView';
import { fetchFaqs, groupFaqs, stripMarkdown } from '@/lib/faq';
import { absoluteUrl, SITE_URL } from '@/lib/site';

export const metadata: Metadata = {
  title: '자주묻는질문',
  description:
    '베란다(발코니) 확장·벽 철거, 행위허가·입주민 동의, 방화판·시공, 사용검사까지 — 집핀 이용 전 자주 묻는 질문을 한곳에 모았습니다.',
  alternates: { canonical: '/faq' },
  openGraph: {
    title: '자주묻는질문 — 집핀',
    description:
      '베란다 확장·벽 철거, 행위허가, 입주민 동의, 방화·시공, 사용검사 관련 자주 묻는 질문.',
    url: '/faq'
  }
};

// FAQ 콘텐츠는 백엔드에서 받아 ISR(revalidate 300s)로 캐시한다.
export const revalidate = 300;

function buildFaqJsonLd(
  faqs: { question: string; answer: string }[]
): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    '@id': `${SITE_URL}/faq#faqpage`,
    url: absoluteUrl('/faq'),
    mainEntity: faqs.map((f) => ({
      '@type': 'Question',
      name: f.question,
      acceptedAnswer: { '@type': 'Answer', text: stripMarkdown(f.answer) }
    }))
  };
}

export default async function FaqPage() {
  const items = await fetchFaqs();
  const groups = groupFaqs(items);
  const jsonLd = buildFaqJsonLd(items);

  return (
    <Stack gap="lg">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <Stack gap={4}>
        <Title order={1} fz="1.75rem" style={{ wordBreak: 'keep-all' }}>
          자주묻는질문
        </Title>
        <Text c="dimmed" style={{ wordBreak: 'keep-all' }}>
          집핀 이용 전 가장 많이 묻는 질문을 모았습니다. 더 궁금한 점은 전문가
          상담으로 문의해 주세요.
        </Text>
      </Stack>
      <FaqView groups={groups} />
    </Stack>
  );
}

import {
  Badge,
  Box,
  Button,
  Card,
  Container,
  Group,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  Title
} from '@mantine/core';
import { IconArrowRight, IconCheck } from '@tabler/icons-react';
import type { Metadata } from 'next';

import { SITE_OG_IMAGE } from '@/lib/site';

export const metadata: Metadata = {
  title: '가격 — AI 사전검토·행위허가 대행',
  description:
    '베란다 확장·가벽철거 AI 사전검토는 무료. 전문가 1:1 상담과 입주민 동의서·행위허가 신청 대행까지, 집핀 서비스 단계별 가격을 확인하세요.',
  keywords: ['베란다 확장 비용', '행위허가 대행 비용', '사전검토 가격', '발코니 확장 견적'],
  alternates: { canonical: '/prices' },
  openGraph: {
    title: '집핀 가격 — AI 사전검토·행위허가 대행',
    description: '발코니 확장·가벽철거 AI 사전검토 무료. 상담·동의서·행위허가 대행 단계별 가격.',
    url: '/prices',
    images: [{ url: SITE_OG_IMAGE }]
  }
};

type Plan = {
  name: string;
  price: string;
  priceNote?: string;
  description: string;
  features: string[];
  cta: { href: string; label: string; color: 'jippin' | 'coral'; variant?: 'filled' | 'default' };
  highlighted?: boolean;
};

const PLANS: Plan[] = [
  {
    name: 'AI 사전검토',
    price: '무료',
    description: '도면과 주소만으로 받는 AI 행위허가 가능성 사전검토.',
    features: [
      '도면 자동 분석',
      '법령 및 사례 기반 평가',
      '실시간 질의응답',
      '로그인 없이 즉시 시작'
    ],
    cta: { href: '/sessions/new', label: '사전검토 시작', color: 'jippin', variant: 'default' }
  },
  {
    name: '전문가 단건 상담',
    price: '문의',
    description: '담당 전문가가 맞춤형 1:1 상담을 진행해요.',
    features: [
      'AI 사전검토 전체 포함',
      '전문가 1:1 도면 검토',
      '현장 리스크 피드백',
      '1일 이내 회신'
    ],
    cta: { href: '/leads/new', label: '상담 신청하기', color: 'coral', variant: 'filled' },
    highlighted: true
  },
  {
    name: '행위허가 대행',
    price: '문의',
    description: '입주민 동의서부터 행위허가 신청·승인까지 전 과정을 함께해요.',
    features: [
      '단건 상담 전체 포함',
      '입주민 동의서 대행',
      '현장 실측 방문',
      '행위허가 서류 대행',
    ],
    cta: { href: '/leads/new', label: '상담 신청하기', color: 'jippin', variant: 'default' }
  }
];

export default function PricesPage() {
  return (
    <Box>
      {/* ── 헤더 ─────────────────────────────────────────────── */}
      <Box
        style={{
          background:
            'radial-gradient(120% 120% at 50% 0%, #E2F1EF 0%, rgba(248,249,250,0) 60%), linear-gradient(180deg, #FBFDFC 0%, #F8F9FA 100%)',
          borderBottom: '1px solid var(--jippin-brand-border)'
        }}
      >
        <Container
          size="lg"
          style={{
            paddingTop: 'clamp(3rem, 6vw, 5rem)',
            paddingBottom: 'clamp(2rem, 4vw, 3rem)'
          }}
        >
          <Stack gap="sm" align="center" ta="center">
            <Title
              order={1}
              style={{
                fontSize: 'clamp(1.9rem, 4vw, 2.75rem)',
                lineHeight: 1.15,
                letterSpacing: '-0.02em'
              }}
            >
              사전검토는 무료, 상담은 필요한 만큼
            </Title>
            <Text c="dimmed" maw={480} style={{ wordBreak: 'keep-all' }}>
              AI 사전검토로 가능성부터 확인하고, 더 자세한 내용은 전문가 상담으로 이어가세요.
            </Text>
          </Stack>
        </Container>
      </Box>

      {/* ── 플랜 ─────────────────────────────────────────────── */}
      <Container
        size="lg"
        style={{
          paddingTop: 'clamp(2.5rem, 5vw, 4rem)',
          paddingBottom: 'clamp(3rem, 6vw, 5rem)'
        }}
      >
        <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="lg" verticalSpacing="lg">
          {PLANS.map((plan) => (
            <Card
              key={plan.name}
              radius="lg"
              padding="xl"
              withBorder
              style={{
                position: 'relative',
                borderColor: plan.highlighted
                  ? 'var(--jippin-brand-primary)'
                  : 'var(--jippin-brand-border)',
                borderWidth: plan.highlighted ? 2 : 1,
                boxShadow: plan.highlighted
                  ? '0 16px 40px -24px rgba(20,122,115,0.5)'
                  : undefined
              }}
            >
              <Stack gap="md" h="100%">
                <Stack gap={4}>
                  <Group justify="space-between" align="center">
                    <Text fw={700} fz="lg">
                      {plan.name}
                    </Text>
                    {plan.highlighted ? (
                      <Badge color="coral" variant="filled" radius="sm">
                        추천
                      </Badge>
                    ) : null}
                  </Group>
                  <Group align="baseline" gap={6}>
                    <Text fw={800} fz={28} style={{ letterSpacing: '-0.02em' }}>
                      {plan.price}
                    </Text>
                    {plan.priceNote ? (
                      <Text size="xs" c="dimmed">
                        {plan.priceNote}
                      </Text>
                    ) : null}
                  </Group>
                  <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
                    {plan.description}
                  </Text>
                </Stack>

                <Stack gap="xs">
                  {plan.features.map((f) => (
                    <Group key={f} gap="xs" wrap="nowrap" align="center">
                      <ThemeIcon color="jippin" variant="light" size={20} radius="xl">
                        <IconCheck size={13} />
                      </ThemeIcon>
                      <Text size="sm">{f}</Text>
                    </Group>
                  ))}
                </Stack>

                <Button
                  component="a"
                  href={plan.cta.href}
                  size="md"
                  radius="md"
                  color={plan.cta.color}
                  variant={plan.cta.variant ?? 'filled'}
                  fullWidth
                  mt="auto"
                  rightSection={<IconArrowRight size={16} />}
                >
                  {plan.cta.label}
                </Button>
              </Stack>
            </Card>
          ))}
        </SimpleGrid>

        <Text size="xs" c="dimmed" ta="center" mt="xl">
          상담 상품과 가격은 대상 규모와 진행 범위에 따라 안내해 드립니다.
        </Text>

        {/* 가격 앵커가 '문의' 중심이라, 비용 관련 FAQ 로 바로 이어주는 보조 동선을 둔다. */}
        <Group justify="center" mt="md">
          <Button
            component="a"
            href="/faq?category=cost"
            variant="subtle"
            color="jippin"
            radius="md"
            rightSection={<IconArrowRight size={16} />}
          >
            비용 관련 자주묻는질문 보기
          </Button>
        </Group>
      </Container>
    </Box>
  );
}

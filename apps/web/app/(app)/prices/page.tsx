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

import { LeadCtaButton } from '@/components/analytics/LeadCtaButton';
import { type LeadCtaId } from '@/lib/analytics/lead-cta';
import { buildPricesJsonLd, safeJsonLd, SITE_OG_IMAGE } from '@/lib/site';

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

// 버튼 위계(DESIGN.md): 제품 진입(사전검토)=jippin filled(1차), 전환(상담 신청)은
// 추천 플랜 1곳만 coral filled(화면당 1회), 나머지 상담 플랜은 jippin outline(2차).
type PlanCta = {
  label: string;
  color: 'jippin' | 'coral';
  variant?: 'filled' | 'outline';
} & (
  | { href: string; leadCta?: never }
  | { href?: never; leadCta: LeadCtaId } // 상담 인입 CTA — 위치 식별자로 추적
);

type Plan = {
  name: string;
  price: string;
  priceNote?: string;
  description: string;
  features: string[];
  cta: PlanCta;
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
    cta: { href: '/sessions', label: '사전검토 시작', color: 'jippin', variant: 'filled' }
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
    cta: { leadCta: 'prices_consult', label: '상담 신청하기', color: 'coral', variant: 'filled' },
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
    cta: { leadCta: 'prices_permit', label: '상담 신청하기', color: 'jippin', variant: 'outline' }
  }
];

export default function PricesPage() {
  return (
    <Box>
      {/* JSON-LD: Service · OfferCatalog (가격 질의 SEO/GEO) */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: safeJsonLd(buildPricesJsonLd()) }}
      />
      {/* ── 헤더 ─────────────────────────────────────────────── */}
      {/* 배경은 투명 — 흰 캔버스의 제도 격자가 그대로 드러난다(옛 회색 그라데이션 밴드 제거,
          COLOR_SYSTEM 그라데이션 금지). 경계는 보더 한 줄로만 구분한다. */}
      <Box style={{ borderBottom: '1px solid var(--jippin-brand-border)' }}>
        <Container
          size="lg"
          style={{
            paddingTop: 'var(--jippin-section-py)',
            paddingBottom: 'var(--jippin-section-py)'
          }}
        >
          <Stack gap="sm" align="center" ta="center">
            <Title
              order={1}
              style={{
                // 랜딩 히어로 전용 타입 토큰 — 페이지별 임의 clamp 발명 금지(TYPOGRAPHY.md §2).
                fontSize: 'var(--jippin-fz-hero)',
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
          paddingTop: 'var(--jippin-section-py)',
          paddingBottom: 'var(--jippin-section-py)'
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
                      // 코랄은 전환 CTA 전용 — 마커(추천 배지)는 브랜드 틸을 쓴다(BRAND).
                      <Badge color="jippin" variant="filled" radius="sm">
                        추천
                      </Badge>
                    ) : null}
                  </Group>
                  <Group align="baseline" gap={6}>
                    {/* 가격 숫자는 h2 토큰 수준(xl=20px)·fw 700 상한 — fw 800 금지(TYPOGRAPHY.md). */}
                    <Text fw={700} fz="xl" style={{ letterSpacing: '-0.02em' }}>
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

                {plan.cta.leadCta ? (
                  // 상담 전환 CTA — coral filled 는 전환 표준(CtaButton)과 같은 모양이 되도록
                  // fw 700 을 얹는다(LeadCtaButton 은 추적 때문에 유지, 스타일은 props 로만).
                  <LeadCtaButton
                    cta={plan.cta.leadCta}
                    size="md"
                    color={plan.cta.color}
                    variant={plan.cta.variant ?? 'filled'}
                    fw={plan.cta.color === 'coral' ? 700 : undefined}
                    fullWidth
                    mt="auto"
                    rightSection={<IconArrowRight size={16} />}
                  >
                    {plan.cta.label}
                  </LeadCtaButton>
                ) : (
                  // 서버 컴포넌트라 component={Link} 는 SSG prerender 를 깨뜨린다 —
                  // 네이티브 앵커 유지(app/not-found.tsx 와 동일한 RSC 비호환 회피).
                  <Button
                    component="a"
                    href={plan.cta.href}
                    size="md"
                    color={plan.cta.color}
                    variant={plan.cta.variant ?? 'filled'}
                    fullWidth
                    mt="auto"
                    rightSection={<IconArrowRight size={16} />}
                  >
                    {plan.cta.label}
                  </Button>
                )}
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
            rightSection={<IconArrowRight size={16} />}
          >
            비용 관련 자주묻는질문 보기
          </Button>
        </Group>
      </Container>
    </Box>
  );
}

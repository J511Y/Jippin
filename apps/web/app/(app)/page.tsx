import {
  Badge,
  Box,
  Card,
  Container,
  Divider,
  Group,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  Title
} from '@mantine/core';
import {
  IconArrowRight,
  IconClipboardCheck,
  IconFileCheck,
  IconFileSearch,
  IconFlame,
  IconMessageCircle2,
  IconReportAnalytics,
  IconRulerMeasure,
  IconShieldCheck,
  IconUpload,
  IconUsersGroup
} from '@tabler/icons-react';
import type { Metadata } from 'next';

import { LeadCtaButton } from '@/components/analytics/LeadCtaButton';
import { HeroStartCta } from '@/components/landing/HeroStartCta';
import { Reveal } from '@/components/landing/Reveal';
import { StatBand } from '@/components/landing/StatBand';
import { QuickConsultSection } from '@/components/QuickConsultSection';
import {
  SITE_DESCRIPTION,
  SITE_KEYWORDS,
  SITE_OG_IMAGE,
  buildHomeJsonLd,
  safeJsonLd
} from '@/lib/site';

export const metadata: Metadata = {
  title: '집핀 — 베란다 확장·벽 철거 사전검토',
  description: SITE_DESCRIPTION,
  keywords: SITE_KEYWORDS,
  alternates: { canonical: '/' },
  openGraph: {
    title: '집핀 — 벽 하나 철거 전에, 가능한지부터 확인하세요',
    description: SITE_DESCRIPTION,
    url: '/',
    images: [{ url: SITE_OG_IMAGE }]
  }
};

const STEPS = [
  {
    icon: IconUpload,
    title: '도면·주소 업로드',
    body: '평면도 한 장과 주소만 입력하면 끝. 로그인 없이 1분이면 됩니다.'
  },
  {
    icon: IconRulerMeasure,
    title: '도면 자동 인식',
    body: 'AI 가 평면도에서 벽체·개구부·치수를 인식해 구조를 읽어냅니다.'
  },
  {
    icon: IconShieldCheck,
    title: '구조 판별 · 위험 진단',
    body: '내력·비내력을 판별하고, 행위허가 필요 여부와 주의 구간을 진단합니다.'
  },
  {
    icon: IconReportAnalytics,
    title: '사전검토 리포트',
    body: '철거·확장 가능성을 신호등 리포트로 즉시 확인하고, 바로 상담으로 이어갈 수 있어요.'
  }
];

const FEATURES = [
  {
    icon: IconFileSearch,
    title: 'AI 사전검토',
    body: '도면으로 철거·확장 가능성과 주의 구간, 행위허가 필요 여부를 1분 만에 진단합니다.'
  },
  {
    icon: IconMessageCircle2,
    title: '전문가 상담',
    body: '사전검토 결과를 바탕으로 20년 경력 전문가가 1:1 맞춤 상담. 우리 집 상황에 맞는 진행 방법을 안내합니다.'
  },
  {
    icon: IconUsersGroup,
    title: '입주민 동의서 대행',
    body: '낯선 이웃 방문부터 서명까지 담당자가 직접. 평일 저녁·주말에 찾아가고, 부재 세대도 끝까지 받아냅니다.'
  },
  {
    icon: IconFileCheck,
    title: '행위허가 대행',
    body: '동의서·검인 도면·구조안전확인서·철거 사유서 준비부터 지자체 접수까지(약 7일). 누적 2만5천여 건.'
  },
  {
    icon: IconFlame,
    title: '방화 판·유리·문 시공',
    body: '발코니 확장 시 의무인 90cm 이상 방화판·방화유리를 건축법(KS F 2845) 기준에 맞게 시공합니다.'
  },
  {
    icon: IconClipboardCheck,
    title: '사용검사 · 건축물대장 등재',
    body: '사용검사를 신청해 공사 내용을 건축물대장에 정식 등재합니다. 이 절차까지 마쳐야 법적으로 완료됩니다.'
  }
];

export default function HomePage() {
  return (
    <Box>
      {/* JSON-LD: Organization · WebSite · Service · FAQ (SEO 리치결과 + GEO) */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: safeJsonLd(buildHomeJsonLd()) }}
      />
      {/* ── HERO ─────────────────────────────────────────────── */}
      {/* 흰 캔버스 기준 재보정 — 틸 틴트만 남기고 투명으로 페이드해 제도 격자가
          여백에서 은은히 비치게 한다(옛 회색 #F8F9FA 기반 그라데이션은 격자와
          어긋난 회색 섬이 됨). */}
      <Box
        style={{
          background:
            'radial-gradient(120% 120% at 80% 0%, var(--mantine-color-jippin-0) 0%, rgba(255,255,255,0) 55%)',
          borderBottom: '1px solid var(--jippin-brand-border)'
        }}
      >
        <Container
          size="lg"
          style={{
            paddingTop: 'var(--jippin-section-py)',
            paddingBottom: 'var(--jippin-section-py)'
          }}
        >
          <Reveal immediate stagger={0.14} style={{ display: 'contents' }}>
          <SimpleGrid cols={{ base: 1, md: 2 }} spacing={48} verticalSpacing={48}>
            <Stack gap="lg" justify="center">
              <Title
                order={1}
                data-reveal
                style={{
                  fontSize: 'var(--jippin-fz-hero)',
                  lineHeight: 1.12,
                  letterSpacing: '-0.02em',
                  wordBreak: 'keep-all'
                }}
              >
                벽 하나 철거 전에,
                <br />
                <Text
                  component="span"
                  inherit
                  c="var(--jippin-brand-primary)"
                >
                  가능한지부터
                </Text>{' '}
                확인하세요
              </Title>
              <Text
                size="lg"
                c="dimmed"
                maw={520}
                data-reveal
                style={{ wordBreak: 'keep-all', lineHeight: 1.6 }}
              >
                인테리어로 집 안의 벽을 트거나 옮기고 싶을 때, 철거해도 되는 벽인지
                도면과 주소만으로 미리 확인해 드려요.
              </Text>
              <Group gap="sm" mt="xs" data-reveal>
                {/* 1차 액션(제품 진입) = jippin filled. 이 화면의 코랄 1회는
                    QuickConsult 폼 제출이므로 상담 버튼은 outline 2차로 둔다. */}
                <HeroStartCta
                  href="/sessions"
                  size="lg"
                  color="jippin"
                  variant="filled"
                  rightSection={<IconArrowRight size={18} />}
                >
                  무료로 사전검토 시작
                </HeroStartCta>
                <LeadCtaButton cta="home_hero" size="lg" variant="outline" color="jippin">
                  전문가 상담
                </LeadCtaButton>
              </Group>
            </Stack>

            {/* 리포트 목업 */}
            <Box visibleFrom="md" data-reveal style={{ position: 'relative' }}>
              <Card
                shadow="xl"
                padding="xl"
                withBorder
                style={{ transform: 'rotate(1deg)' }}
              >
                <Stack gap="md">
                  <Group justify="space-between" align="flex-start">
                    <Stack gap={2}>
                      <Text size="xs" c="dimmed" fw={600} tt="uppercase">
                        사전검토 리포트
                      </Text>
                      <Text fw={700}>서울 강남구 ○○로 12</Text>
                    </Stack>
                    <Badge color="success" variant="light" radius="sm" size="lg">
                      철거 가능성 높음
                    </Badge>
                  </Group>
                  {/* 미니 도면 — '도면을 읽는 AI' 시각 신호. 내력벽=danger 실선,
                      비내력벽=success 점선 (globals.css OVERLAY 토큰 재사용). */}
                  <Box
                    aria-hidden="true"
                    style={{
                      border: '1px solid var(--jippin-brand-border)',
                      borderRadius: 'var(--mantine-radius-sm)',
                      background: 'var(--jippin-brand-surface)',
                      padding: '8px 10px'
                    }}
                  >
                    <svg
                      viewBox="0 0 260 84"
                      width="100%"
                      role="presentation"
                      focusable="false"
                      style={{ display: 'block' }}
                    >
                      {/* 외곽 벽 */}
                      <rect
                        x="4"
                        y="4"
                        width="252"
                        height="76"
                        fill="none"
                        stroke="var(--jippin-brand-professional)"
                        strokeOpacity="0.4"
                        strokeWidth="2"
                      />
                      {/* 내력벽(철거 불가) — 실선 */}
                      <line
                        x1="96"
                        y1="4"
                        x2="96"
                        y2="80"
                        stroke="var(--floorplan-wall-load)"
                        strokeWidth="3"
                      />
                      {/* 비내력벽(철거 후보) — 점선 */}
                      <line
                        x1="96"
                        y1="44"
                        x2="256"
                        y2="44"
                        stroke="var(--floorplan-wall-nonload)"
                        strokeWidth="3"
                        strokeDasharray="7 5"
                      />
                      <line
                        x1="178"
                        y1="44"
                        x2="178"
                        y2="80"
                        stroke="var(--floorplan-wall-nonload)"
                        strokeWidth="3"
                        strokeDasharray="7 5"
                      />
                    </svg>
                  </Box>
                  <Divider />
                  <Stack gap="sm">
                    {[
                      { label: '대상 벽체', value: '철거해도 되는 벽', tone: 'success' },
                      { label: '허가 필요', value: '필요 (구청)', tone: 'warning' },
                      { label: '주의 구간', value: '1곳 감지', tone: 'danger' }
                    ].map((row) => (
                      <Group key={row.label} justify="space-between">
                        <Text size="sm" c="dimmed">
                          {row.label}
                        </Text>
                        <Badge
                          color={row.tone}
                          variant="dot"
                          radius="sm"
                          styles={{ root: { textTransform: 'none' } }}
                        >
                          {row.value}
                        </Badge>
                      </Group>
                    ))}
                  </Stack>
                  {/* 목업 장식 — 동작 없는 리포트 화면 예시라 실제 버튼 대신
                      비인터랙티브 표현을 쓴다(죽은 버튼 오탭 방지). */}
                  <Box
                    aria-hidden="true"
                    mt="xs"
                    style={{
                      textAlign: 'center',
                      padding: '10px 16px',
                      borderRadius: 'var(--mantine-radius-md)',
                      background: 'var(--mantine-color-coral-0)',
                      color: 'var(--mantine-color-coral-8)',
                      fontSize: 'var(--mantine-font-size-sm)',
                      fontWeight: 600
                    }}
                  >
                    전문가 상담으로 전환
                  </Box>
                </Stack>
              </Card>
            </Box>
          </SimpleGrid>
          </Reveal>
        </Container>
      </Box>

      {/* ── HOW IT WORKS ─────────────────────────────────────── */}
      <Container
        size="lg"
        style={{
          paddingTop: 'var(--jippin-section-py)',
          paddingBottom: 'var(--jippin-section-py)'
        }}
      >
        <Stack gap={8} mb="xl" maw={620}>
          <Text fw={600} c="var(--jippin-brand-primary)" size="sm">
            이렇게 진행돼요
          </Text>
          <Title
            order={2}
            style={{
              fontSize: 'var(--jippin-fz-display)',
              lineHeight: 1.25,
              wordBreak: 'keep-all'
            }}
          >
            도면 한 장으로, 1분 사전검토
          </Title>
        </Stack>
        <Reveal>
        {/* 데스크탑·태블릿: 연결 스텝퍼 */}
        <Box visibleFrom="sm" style={{ position: 'relative' }}>
          {/* 연결 레일 (데스크탑) — 4단계가 한 흐름으로 읽히도록 */}
          <Box
            visibleFrom="lg"
            style={{
              position: 'absolute',
              top: 27,
              left: '12.5%',
              right: '12.5%',
              height: 2,
              background:
                'linear-gradient(90deg, var(--mantine-color-jippin-4), var(--jippin-brand-border))',
              zIndex: 0
            }}
          />
          <SimpleGrid
            cols={{ base: 1, sm: 2, lg: 4 }}
            spacing="xl"
            verticalSpacing="xl"
            style={{ position: 'relative', zIndex: 1 }}
          >
            {STEPS.map((step, i) => (
              <Stack key={step.title} data-reveal gap="sm" align="center" ta="center">
                <ThemeIcon
                  size={54}
                  radius="xl"
                  variant="filled"
                  color="jippin"
                  style={{ boxShadow: '0 0 0 6px var(--mantine-color-body)' }}
                >
                  <Text fw={700} fz="lg" c="var(--jippin-brand-primary-fg)">
                    {i + 1}
                  </Text>
                </ThemeIcon>
                <Text fw={600} size="lg">
                  {step.title}
                </Text>
                <Text
                  size="sm"
                  c="dimmed"
                  maw={240}
                  style={{ wordBreak: 'keep-all' }}
                >
                  {step.body}
                </Text>
              </Stack>
            ))}
          </SimpleGrid>
        </Box>

        {/* 모바일: 가로 스크롤 캐러셀 */}
        <Box
          hiddenFrom="sm"
          style={{
            display: 'flex',
            gap: 'var(--mantine-spacing-md)',
            overflowX: 'auto',
            scrollSnapType: 'x mandatory',
            paddingBottom: 8,
            WebkitOverflowScrolling: 'touch'
          }}
        >
          {STEPS.map((step, i) => (
            <Card
              key={step.title}
              data-reveal
              withBorder
              style={{ flex: '0 0 80%', scrollSnapAlign: 'start' }}
            >
              <Stack gap="sm">
                <ThemeIcon size={46} radius="xl" variant="filled" color="jippin">
                  <Text fw={700} c="var(--jippin-brand-primary-fg)">
                    {i + 1}
                  </Text>
                </ThemeIcon>
                <Text fw={600} size="lg">
                  {step.title}
                </Text>
                <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
                  {step.body}
                </Text>
              </Stack>
            </Card>
          ))}
        </Box>
        </Reveal>
      </Container>

      {/* ── FEATURES ─────────────────────────────────────────── */}
      {/* 흰 캔버스에서는 흰 밴드 구획이 사라지므로 브랜드 surface 틴트로 밴드를 만든다. */}
      <Box
        style={{
          background: 'var(--jippin-brand-surface)',
          borderTop: '1px solid var(--jippin-brand-border)',
          borderBottom: '1px solid var(--jippin-brand-border)'
        }}
      >
        <Container
          size="lg"
          style={{
            paddingTop: 'var(--jippin-section-py)',
            paddingBottom: 'var(--jippin-section-py)'
          }}
        >
          <Stack gap={8} mb="xl" maw={620}>
            <Text fw={600} c="var(--jippin-brand-primary)" size="sm">
              전 과정 한눈에
            </Text>
            <Title
              order={2}
              style={{
                fontSize: 'var(--jippin-fz-display)',
                lineHeight: 1.25,
                wordBreak: 'keep-all'
              }}
            >
              AI 사전검토부터 행위허가·시공까지
            </Title>
            <Text c="dimmed" style={{ wordBreak: 'keep-all', lineHeight: 1.6 }}>
              2007년부터 행위허가만 누적 2만5천여 건. 베테랑 전문가가 건축법 기준을 지켜
              사전검토부터 허가·시공까지 끝까지 책임집니다.
            </Text>
          </Stack>
          {/* 큰 숫자 스탯 밴드 — 한눈에 들어오는 신뢰 앵커 (뷰포트 진입 시 카운트업) */}
          <StatBand />

          <Reveal stagger={0.08}>
          <SimpleGrid visibleFrom="sm" cols={{ sm: 2, md: 3 }} spacing="lg">
            {FEATURES.map((f) => (
              <Card key={f.title} data-reveal withBorder>
                <Stack gap="sm">
                  <ThemeIcon size={48} radius="md" variant="light" color="jippin">
                    <f.icon size={26} />
                  </ThemeIcon>
                  <Text fw={600} size="lg" style={{ wordBreak: 'keep-all' }}>
                    {f.title}
                  </Text>
                  <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
                    {f.body}
                  </Text>
                </Stack>
              </Card>
            ))}
          </SimpleGrid>

          {/* 모바일: 가로 스크롤 캐러셀 */}
          <Box
            hiddenFrom="sm"
            style={{
              display: 'flex',
              gap: 'var(--mantine-spacing-md)',
              overflowX: 'auto',
              scrollSnapType: 'x mandatory',
              paddingBottom: 8,
              WebkitOverflowScrolling: 'touch'
            }}
          >
            {FEATURES.map((f) => (
              <Card
                key={f.title}
                data-reveal
                withBorder
                style={{ flex: '0 0 80%', scrollSnapAlign: 'start' }}
              >
                <Stack gap="sm">
                  <ThemeIcon size={48} radius="md" variant="light" color="jippin">
                    <f.icon size={26} />
                  </ThemeIcon>
                  <Text fw={600} size="lg" style={{ wordBreak: 'keep-all' }}>
                    {f.title}
                  </Text>
                  <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
                    {f.body}
                  </Text>
                </Stack>
              </Card>
            ))}
          </Box>
          </Reveal>
        </Container>
      </Box>

      {/* ── 빠른 상담 (CTA + 폼) ──────────────────────────────── */}
      <QuickConsultSection />
    </Box>
  );
}

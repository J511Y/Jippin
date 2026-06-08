import {
  Badge,
  Box,
  Button,
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

import { Reveal } from '@/components/landing/Reveal';
import { StatBand } from '@/components/landing/StatBand';
import { QuickConsultSection } from '@/components/QuickConsultSection';

export const metadata: Metadata = {
  title: '집핀 — 벽 철거 전 사전검토'
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
      {/* ── HERO ─────────────────────────────────────────────── */}
      <Box
        style={{
          background:
            'radial-gradient(120% 120% at 80% 0%, #E2F1EF 0%, rgba(248,249,250,0) 55%), linear-gradient(180deg, #FBFDFC 0%, #F8F9FA 100%)',
          borderBottom: '1px solid var(--jippin-brand-border)'
        }}
      >
        <Container
          size="lg"
          style={{
            paddingTop: 'clamp(3rem, 7vw, 6rem)',
            paddingBottom: 'clamp(3rem, 7vw, 6rem)'
          }}
        >
          <Reveal immediate stagger={0.14} style={{ display: 'contents' }}>
          <SimpleGrid cols={{ base: 1, md: 2 }} spacing={48} verticalSpacing={48}>
            <Stack gap="lg" justify="center">
              <Title
                order={1}
                data-reveal
                style={{
                  fontSize: 'clamp(2rem, 4.5vw, 3.25rem)',
                  lineHeight: 1.12,
                  letterSpacing: '-0.02em',
                  wordBreak: 'keep-all'
                }}
              >
                벽 하나 헐기 전에,
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
                인테리어로 집 안의 벽을 트거나 옮기고 싶을 때, 헐어도 되는 벽인지
                도면과 주소만으로 미리 확인해 드려요.
              </Text>
              <Group gap="sm" mt="xs" data-reveal>
                <Button
                  component="a"
                  href="/sessions/new"
                  size="lg"
                  color="jippin"
                  radius="md"
                  rightSection={<IconArrowRight size={18} />}
                >
                  무료로 사전검토 시작
                </Button>
                <Button
                  component="a"
                  href="/leads/new"
                  size="lg"
                  variant="default"
                  radius="md"
                >
                  전문가 상담
                </Button>
              </Group>
            </Stack>

            {/* 리포트 목업 */}
            <Box visibleFrom="md" data-reveal style={{ position: 'relative' }}>
              <Card
                shadow="xl"
                radius="lg"
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
                  <Divider />
                  <Stack gap="sm">
                    {[
                      { label: '대상 벽체', value: '헐어도 되는 벽', tone: 'success' },
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
                  <Button
                    color="coral"
                    variant="light"
                    radius="md"
                    fullWidth
                    mt="xs"
                  >
                    전문가 상담으로 전환
                  </Button>
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
          paddingTop: 'clamp(3rem, 6vw, 5rem)',
          paddingBottom: 'clamp(3rem, 6vw, 5rem)'
        }}
      >
        <Stack gap={8} mb="xl" maw={620}>
          <Text fw={600} c="var(--jippin-brand-primary)" size="sm">
            이렇게 진행돼요
          </Text>
          <Title
            order={2}
            style={{
              fontSize: 'clamp(1.5rem, 3vw, 2rem)',
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
                  style={{ boxShadow: '0 0 0 6px #F8F9FA' }}
                >
                  <Text fw={800} fz="lg" c="#FFFFFF">
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
              radius="lg"
              padding="lg"
              style={{ flex: '0 0 80%', scrollSnapAlign: 'start' }}
            >
              <Stack gap="sm">
                <ThemeIcon size={46} radius="xl" variant="filled" color="jippin">
                  <Text fw={800} c="#FFFFFF">
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
      <Box style={{ background: '#FFFFFF', borderTop: '1px solid var(--jippin-brand-border)', borderBottom: '1px solid var(--jippin-brand-border)' }}>
        <Container
          size="lg"
          style={{
            paddingTop: 'clamp(3rem, 6vw, 5rem)',
            paddingBottom: 'clamp(3rem, 6vw, 5rem)'
          }}
        >
          <Stack gap={8} mb="xl" maw={620}>
            <Text fw={600} c="var(--jippin-brand-primary)" size="sm">
              전 과정 한눈에
            </Text>
            <Title
              order={2}
              style={{
                fontSize: 'clamp(1.5rem, 3vw, 2rem)',
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
              <Card key={f.title} data-reveal withBorder radius="lg" padding="lg">
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
                radius="lg"
                padding="lg"
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

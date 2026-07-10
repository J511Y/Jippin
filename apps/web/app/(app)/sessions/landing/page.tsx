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
import {
  IconAlertTriangle,
  IconArrowRight,
  IconCheck,
  IconClockHour3,
  IconFileCheck,
  IconLock,
  IconReportAnalytics,
  IconSparkles,
  IconUpload
} from '@tabler/icons-react';
import type { Metadata } from 'next';

import { buildSessionsLandingJsonLd, safeJsonLd, SITE_FAQ } from '@/lib/site';

/**
 * `/sessions/landing` — 사전검토 외부 마케팅 랜딩(색인·LLM 인입 전용, 단일 전환 퍼널).
 *
 * 역할 분리(사용자 결정): 홈(`/`)은 회사·전체 서비스 소개, 이 페이지는 광고/검색으로
 * 들어온 방문자를 **무료 AI 사전검토 시작(`/sessions`)** 한 가지 행동으로 전환시키는
 * 데 특화한다. 따라서 홈과 겹치던 리포트 카드·StatBand·동일 스텝퍼를 의도적으로 쓰지
 * 않고, 실제 제품(대화형)을 보여 주는 채팅형 히어로 + 의도 칩 + 리스크 리버설 +
 * 판정 설명 + FAQ 로 구성한다. 인입 의도: 베란다(발코니) 확장 / 벽 철거·거실 확장(내력벽).
 *
 * 정적 server component(GSAP 미사용) — 콘텐츠 100% SSR 텍스트(SEO/GEO) + 가벼운 LCP.
 */
export const metadata: Metadata = {
  title: 'AI 사전검토 — 베란다 확장·벽 철거 가능 여부 1분 진단',
  description:
    '우리 집에서 베란다(발코니) 확장이나 거실 벽 철거가 가능한지, 평면도와 주소만으로 1분 만에 AI 가 사전검토합니다. 내력벽·비내력벽을 판별하고 행위허가 필요 여부까지 진단해요. 로그인 없이 무료.',
  alternates: { canonical: '/sessions/landing' },
  openGraph: {
    title: 'AI 사전검토 — 집핀',
    description:
      '베란다 확장·벽 철거가 우리 집에서 가능한지 도면과 주소만으로 1분 만에 AI 사전검토. 로그인 없이 무료.',
    url: '/sessions/landing'
  }
};

// 광고/검색 인입 의도를 그대로 질문으로 — 각 칩이 곧 CTA(전부 /sessions 로).
const INTENTS = [
  '베란다(발코니) 확장, 가능할까요?',
  '거실·방 사이 벽 철거하고 확장돼요?',
  '이 벽, 내력벽인가요 비내력벽인가요?',
  '화단·가벽 철거해도 되나요?',
  '행위허가를 꼭 받아야 하나요?'
];

// 1분 뒤 받는 답(신호등) — 색만으로 의미를 전하지 않도록 라벨+아이콘 동반(DESIGN.md §2.4).
// 상태색은 warning/danger 토큰만 쓴다 — 코랄은 전환 CTA 전용이라 상태에 금지(BRAND).
const VERDICTS = [
  {
    icon: IconCheck,
    color: 'jippin' as const,
    tag: '가능',
    desc: '손대도 되는 비내력벽·확장 가능 구간을 짚어 줍니다.'
  },
  {
    icon: IconFileCheck,
    color: 'warning' as const,
    tag: '확인 필요',
    desc: '행위허가·입주민 동의가 필요한 경우를 미리 알려 줍니다.'
  },
  {
    icon: IconAlertTriangle,
    color: 'danger' as const,
    tag: '주의',
    desc: '함부로 손대면 안 되는 내력벽·구조 위험 구간을 표시합니다.'
  }
];

// 3단계 미니 프로세스 — 홈의 큰 스텝퍼와 달리 한 줄로 압축.
const FLOW = [
  { icon: IconUpload, label: '도면·주소 업로드' },
  { icon: IconSparkles, label: 'AI 도면 분석' },
  { icon: IconReportAnalytics, label: '신호등 리포트' }
];

// 타입 스케일은 테마 토큰이 SSOT — 페이지별 임의 clamp 발명 금지(TYPOGRAPHY.md §2).
// 히어로 h1 = hero 토큰(32→44px), 섹션 h2 = display 토큰(24→28px).
const DISPLAY = {
  fontSize: 'var(--jippin-fz-hero)',
  lineHeight: 1.1,
  letterSpacing: '-0.03em',
  wordBreak: 'keep-all' as const
};
const H2 = {
  fontSize: 'var(--jippin-fz-display)',
  lineHeight: 1.2,
  letterSpacing: '-0.02em',
  wordBreak: 'keep-all' as const
};
// 랜딩 섹션 세로 패딩 공용 토큰 — 3개 랜딩(홈·가격·사전검토)이 공유.
const SECTION_PY = 'var(--jippin-section-py)';

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <Text
      fw={700}
      fz="sm"
      c="var(--jippin-brand-primary)"
      style={{ letterSpacing: '0.04em', textTransform: 'uppercase' }}
    >
      {children}
    </Text>
  );
}

export default function SessionsLandingPage() {
  return (
    <Box>
      {/* JSON-LD: WebPage · Service · HowTo · FAQ · BreadcrumbList (SEO 리치결과 + GEO) */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: safeJsonLd(buildSessionsLandingJsonLd()) }}
      />

      {/* ── HERO (채팅형 — 실제 제품을 보여 준다) ───────────────── */}
      {/* 배경은 투명 — 흰 캔버스의 제도 격자 위에 흰 채팅 카드가 떠 보인다(옛 회색
          그라데이션 밴드 제거, COLOR_SYSTEM 그라데이션 금지). */}
      <Box style={{ borderBottom: '1px solid var(--jippin-brand-border)' }}>
        <Container size="lg" style={{ paddingTop: SECTION_PY, paddingBottom: SECTION_PY }}>
          <SimpleGrid cols={{ base: 1, md: 2 }} spacing={56} verticalSpacing={44}>
            <Stack gap="xl" justify="center">
              <Stack gap="lg">
                <Eyebrow>베란다 확장 · 벽 철거 가능 여부 · 무료</Eyebrow>
                <Title order={1} style={DISPLAY}>
                  베란다 확장, 거실 벽 철거
                  <br />
                  <Text component="span" inherit c="var(--jippin-brand-primary)">
                    우리 집은 될까요?
                  </Text>
                </Title>
                <Text size="lg" c="dimmed" maw={500} style={{ wordBreak: 'keep-all', lineHeight: 1.65 }}>
                  평면도와 주소만 올리면, AI 가 내력벽·비내력벽을 판별하고 행위허가가
                  필요한지까지 1분 만에 알려드려요. 견적·상담 전에, 가능한지부터.
                </Text>
              </Stack>

              <Stack gap="sm">
                <Group gap="sm">
                  {/* 제품 진입 1차 액션 — 이 페이지의 /sessions CTA 는 전부 jippin filled
                      한 가지 모양만 쓴다(버튼 위계 §2). 서버 컴포넌트라 component={Link} 는
                      SSG prerender 를 깨뜨려 네이티브 앵커를 유지한다(not-found.tsx 와 동일). */}
                  <Button
                    component="a"
                    href="/sessions"
                    size="lg"
                    color="jippin"
                    rightSection={<IconArrowRight size={18} />}
                  >
                    무료로 확인하기
                  </Button>
                </Group>
                <Group gap="lg" mt={2}>
                  <Group gap={6} wrap="nowrap">
                    <IconLock size={15} color="var(--jippin-brand-primary)" />
                    <Text size="xs" c="dimmed">로그인 없이</Text>
                  </Group>
                  <Group gap={6} wrap="nowrap">
                    <IconUpload size={15} color="var(--jippin-brand-primary)" />
                    <Text size="xs" c="dimmed">평면도 한 장</Text>
                  </Group>
                  <Group gap={6} wrap="nowrap">
                    <IconClockHour3 size={15} color="var(--jippin-brand-primary)" />
                    <Text size="xs" c="dimmed">약 1분</Text>
                  </Group>
                </Group>
                <Text size="xs" c="dimmed" mt={2}>
                  2007년부터 행위허가 누적 25,000건+ 수행한 전문가가 운영합니다.
                </Text>
              </Stack>
            </Stack>

            {/* 채팅 미리보기 — 홈의 리포트 카드와 다른, 실제 대화형 제품 모습 */}
            <Box style={{ position: 'relative' }}>
              <Card
                shadow="lg"
                radius="lg"
                withBorder
                padding="lg"
                style={{ background: '#FFFFFF' }}
              >
                <Stack gap="md">
                  <Group gap="xs">
                    <ThemeIcon size={26} radius="xl" variant="light" color="jippin">
                      <IconSparkles size={15} />
                    </ThemeIcon>
                    <Text size="xs" c="dimmed" fw={700} style={{ letterSpacing: '0.03em' }}>
                      집핀 AI 사전검토
                    </Text>
                  </Group>

                  {/* 사용자 말풍선 */}
                  <Box style={{ alignSelf: 'flex-end', maxWidth: '88%' }}>
                    <Box
                      style={{
                        background: 'var(--mantine-color-jippin-6)',
                        color: '#FFFFFF',
                        padding: '10px 14px',
                        borderRadius: '14px 14px 4px 14px'
                      }}
                    >
                      <Text size="sm" style={{ wordBreak: 'keep-all', color: '#fff' }}>
                        거실이랑 주방 사이 벽, 철거하고 확장 가능할까요?
                      </Text>
                    </Box>
                  </Box>

                  {/* AI 말풍선 */}
                  <Box style={{ alignSelf: 'flex-start', maxWidth: '92%' }}>
                    <Box
                      style={{
                        background: 'var(--mantine-color-jippin-0)',
                        border: '1px solid var(--jippin-brand-border)',
                        padding: '12px 14px',
                        borderRadius: '14px 14px 14px 4px'
                      }}
                    >
                      <Text size="sm" style={{ wordBreak: 'keep-all', lineHeight: 1.6 }}>
                        도면 기준으로 그 벽은 <b>비내력벽</b>이라 철거 가능성이 높아요.
                        다만 <b>구청 행위허가</b>가 필요하고, 발코니 쪽 1곳은 주의가
                        필요합니다.
                      </Text>
                      {/* 판정 배지도 상태 토큰(warning/danger)만 — 코랄은 전환 CTA 전용. */}
                      <Group gap={6} mt={10}>
                        <Badge color="jippin" variant="light" radius="sm" size="sm">철거 가능</Badge>
                        <Badge color="warning" variant="light" radius="sm" size="sm">허가 필요</Badge>
                        <Badge color="danger" variant="light" radius="sm" size="sm">주의 1곳</Badge>
                      </Group>
                    </Box>
                  </Box>

                  <Text size="xs" c="dimmed" style={{ wordBreak: 'keep-all' }}>
                    예시 대화입니다. 실제 결과는 도면·주소에 따라 달라집니다.
                  </Text>
                </Stack>
              </Card>
            </Box>
          </SimpleGrid>
        </Container>
      </Box>

      {/* ── 의도 칩 (각 칩이 곧 CTA) ─────────────────────────── */}
      <Box style={{ borderBottom: '1px solid var(--jippin-brand-border)' }}>
        <Container size="lg" style={{ paddingTop: SECTION_PY, paddingBottom: SECTION_PY }}>
          <Stack gap="lg">
            <Text fw={700} fz="lg" style={{ wordBreak: 'keep-all' }}>
              이런 질문, 그대로 물어보세요
            </Text>
            <Group gap="sm">
              {INTENTS.map((q) => (
                // 질문 칩 — 칩 형태라 pill radius 허용(칩만 999). 라벨이 줄바꿈돼도
                // 잘리지 않도록 높이를 auto 로 풀고, 터치 타깃 최소 44px 를 보장한다.
                <Button
                  key={q}
                  component="a"
                  href="/sessions"
                  variant="default"
                  radius="xl"
                  size="md"
                  styles={{
                    root: { fontWeight: 500, height: 'auto', minHeight: 44, paddingBlock: 10 },
                    label: { whiteSpace: 'normal' }
                  }}
                >
                  {q}
                </Button>
              ))}
            </Group>
          </Stack>
        </Container>
      </Box>

      {/* ── 리스크 리버설 (비용 불안 해소) ───────────────────── */}
      {/* 다색 그라데이션 금지(COLOR_SYSTEM) — 어두운 틸 밴드 대신 흰 캔버스 기준의
          brand.surface 틴트 밴드로 재보정. 텍스트·CTA 도 표준 토큰/위계로 복귀한다
          (variant="white" 는 어두운 배경 전용이라 함께 제거). */}
      <Box
        style={{
          background: 'var(--jippin-brand-surface)',
          borderTop: '1px solid var(--jippin-brand-border)',
          borderBottom: '1px solid var(--jippin-brand-border)'
        }}
      >
        <Container size="lg" style={{ paddingTop: SECTION_PY, paddingBottom: SECTION_PY }}>
          <SimpleGrid cols={{ base: 1, md: 2 }} spacing={48} verticalSpacing="lg">
            <Stack gap="sm" justify="center">
              <Eyebrow>비용 걱정은 나중에</Eyebrow>
              <Title order={2} style={H2}>
                되는지부터, 공짜로 확인하세요
              </Title>
            </Stack>
            <Stack justify="center">
              <Text c="dimmed" style={{ wordBreak: 'keep-all', lineHeight: 1.7 }}>
                가능 여부 확인까지는 <b>100% 무료</b>입니다. 견적·시공
                이야기는 “가능하다”가 확인된 다음에 시작해요. 안 되는 공사에 상담비부터 쓰는
                일은 없습니다.
              </Text>
              <Group gap="sm" mt="xs">
                <Button component="a" href="/sessions" color="jippin" size="md" rightSection={<IconArrowRight size={18} />}>
                  무료 사전검토 시작
                </Button>
              </Group>
            </Stack>
          </SimpleGrid>
        </Container>
      </Box>

      {/* ── 1분 뒤 받는 답 + 미니 프로세스 ───────────────────── */}
      <Box>
        <Container size="lg" style={{ paddingTop: SECTION_PY, paddingBottom: SECTION_PY }}>
          <Stack gap="xl">
            <Stack gap="sm" maw={640}>
              <Eyebrow>1분 뒤, 이런 답을 받아요</Eyebrow>
              <Title order={2} style={H2}>
                판정 결과를 즉시 확인
              </Title>
            </Stack>

            <SimpleGrid cols={{ base: 1, md: 3 }} spacing="lg">
              {VERDICTS.map((v) => (
                <Card key={v.tag} withBorder radius="lg" padding="xl" style={{ borderColor: 'var(--jippin-brand-border)' }}>
                  <Stack gap="sm">
                    <Group gap="xs" wrap="nowrap" align="center">
                      <ThemeIcon size={26} variant="transparent" color={v.color} p={0}>
                        <v.icon size={24} />
                      </ThemeIcon>
                      <Text fw={700} fz="lg" style={{ wordBreak: 'keep-all' }}>
                        {v.tag}
                      </Text>
                    </Group>
                    <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all', lineHeight: 1.65 }}>
                      {v.desc}
                    </Text>
                  </Stack>
                </Card>
              ))}
            </SimpleGrid>

            {/* 미니 프로세스 한 줄 */}
            <Group gap="xs" justify="center" wrap="wrap" mt="xs">
              {FLOW.map((s, i) => (
                <Group key={s.label} gap="xs" wrap="nowrap">
                  <Group gap={8} wrap="nowrap">
                    <ThemeIcon size={30} radius="xl" variant="light" color="jippin">
                      <s.icon size={17} />
                    </ThemeIcon>
                    <Text size="sm" fw={600} style={{ wordBreak: 'keep-all' }}>
                      {s.label}
                    </Text>
                  </Group>
                  {i < FLOW.length - 1 && (
                    <IconArrowRight size={16} color="var(--jippin-brand-border)" />
                  )}
                </Group>
              ))}
            </Group>
          </Stack>
        </Container>
      </Box>

      {/* ── FAQ ──────────────────────────────────────────────── */}
      <Box style={{ background: 'var(--mantine-color-jippin-0)' }}>
        <Container size="md" style={{ paddingTop: SECTION_PY, paddingBottom: SECTION_PY }}>
          <Stack gap="xl">
            <Stack gap="sm">
              <Eyebrow>자주 묻는 질문</Eyebrow>
              <Title order={2} style={H2}>
                시작 전, 궁금한 점
              </Title>
            </Stack>
            <Stack gap={0}>
              {SITE_FAQ.map((faq, i) => (
                <Box
                  key={faq.question}
                  py="lg"
                  style={
                    i < SITE_FAQ.length - 1
                      ? { borderBottom: '1px solid var(--jippin-brand-border)' }
                      : undefined
                  }
                >
                  <Stack gap={6}>
                    <Text fw={700} style={{ wordBreak: 'keep-all' }}>
                      {faq.question}
                    </Text>
                    <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all', lineHeight: 1.7 }}>
                      {faq.answer}
                    </Text>
                  </Stack>
                </Box>
              ))}
            </Stack>
          </Stack>
        </Container>
      </Box>

      {/* ── 마무리 CTA ───────────────────────────────────────── */}
      {/* 코랄 틴트 그라데이션 제거 — 격자 캔버스가 페이지를 닫는다. 제품 진입 CTA 는
          히어로와 같은 jippin filled 1종(코랄은 상담 전환 전용, 이 페이지엔 없음). */}
      <Box>
        <Container size="md" style={{ paddingTop: SECTION_PY, paddingBottom: SECTION_PY }}>
          <Stack gap="lg" align="center" ta="center">
            <Title order={2} style={{ ...H2, maxWidth: 560 }}>
              공사 결정 전 1분, 가능성부터 확인하세요
            </Title>
            <Text c="dimmed" maw={520} style={{ wordBreak: 'keep-all', lineHeight: 1.65 }}>
              로그인도, 비용도 없습니다. 평면도 한 장이면 베란다 확장·벽 철거가 우리
              집에서 되는지 지금 바로 확인할 수 있어요.
            </Text>
            <Button component="a" href="/sessions" size="lg" color="jippin" rightSection={<IconArrowRight size={18} />}>
              무료 사전검토 시작
            </Button>
            <Text size="xs" c="dimmed" maw={560} style={{ wordBreak: 'keep-all' }}>
              본 서비스는 AI 기반 사전 검토이며, 최종 행위허가 여부는 관할 행정기관
              판단에 따라 달라질 수 있습니다.
            </Text>
          </Stack>
        </Container>
      </Box>
    </Box>
  );
}

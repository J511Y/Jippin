import {
  Button,
  Card,
  Group,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon
} from '@mantine/core';
import {
  IconArrowRight,
  IconBuildingCommunity,
  IconCheck,
  IconHome,
  IconX
} from '@tabler/icons-react';
import type { Metadata } from 'next';

import { PageColumn, PageHeader } from '@/components/ui';
import { buildHomeCheckJsonLd, safeJsonLd } from '@/lib/site';

export const metadata: Metadata = {
  title: '우리집 체크 — 위반건축물 셀프 진단',
  description:
    '아파트·빌라·오피스텔 등 집합건물 세대의 위반건축물(노란딱지) 표시와 확장·변경 등재 여부를 건축물대장(전유부·표제부)으로 셀프 확인하세요.',
  alternates: { canonical: '/home-check' },
  openGraph: {
    title: '우리집 체크 — 집핀',
    description:
      '집합건물 세대의 위반건축물 표시·변동 등재 여부를 건축물대장으로 셀프 진단합니다.',
    url: '/home-check'
  }
};

// 대상 안내 — 집합건물만 지원(단독·다가구 제외).
const SUPPORTED = ['아파트', '연립·다세대(빌라)', '오피스텔', '도시형 생활주택'];
const NOT_SUPPORTED = ['단독주택', '다가구주택', '상가·근린생활시설 단독건물'];

export default function HomeCheckLandingPage() {
  return (
    // 컨테이너가 전 페이지 lg(1140px)로 통일돼, 읽기 중심인 이 페이지는 PageColumn
    // (prose 720px)으로 내부 폭을 좁힌다 — 안 그러면 CTA·본문이 1140px 로 늘어난다.
    <PageColumn width="prose">
      {/* JSON-LD: WebPage · Service · BreadcrumbList (SEO 리치결과 + GEO) */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: safeJsonLd(buildHomeCheckJsonLd()) }}
      />
      {/* 타이틀 크기는 theme headings h1 이 SSOT — 페이지별 fz 오버라이드 금지. */}
      <PageHeader
        title="우리집 체크"
        subtitle="내 집(세대)의 건축물대장을 조회해 위반건축물(노란딱지) 표시 여부와 확장·변경 등재 여부를 셀프로 확인해요. 전유부와 건물 표제부를 함께 조회해 건물 단위 위반표시까지 살핍니다."
      />

      <Stack gap="xl">
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
          {/* 지원 대상 */}
          <Card withBorder radius="lg" padding="xl">
            <Stack gap="md">
              <Group gap="xs" wrap="nowrap" align="center">
                <ThemeIcon color="jippin" variant="light" size={28} radius="xl">
                  <IconBuildingCommunity size={18} />
                </ThemeIcon>
                <Text fw={600}>지원 대상 — 집합건물</Text>
              </Group>
              <Stack gap="xs">
                {SUPPORTED.map((item) => (
                  <Group key={item} gap="xs" wrap="nowrap" align="center">
                    <ThemeIcon color="teal.7" variant="transparent" size={20}>
                      <IconCheck size={16} stroke={2.5} />
                    </ThemeIcon>
                    <Text size="sm">{item}</Text>
                  </Group>
                ))}
              </Stack>
            </Stack>
          </Card>

          {/* 미지원 대상 */}
          <Card withBorder radius="lg" padding="xl">
            <Stack gap="md">
              <Group gap="xs" wrap="nowrap" align="center">
                <ThemeIcon color="gray" variant="light" size={28} radius="xl">
                  <IconHome size={18} />
                </ThemeIcon>
                <Text fw={600} c="dimmed">
                  지원하지 않는 대상
                </Text>
              </Group>
              <Stack gap="xs">
                {NOT_SUPPORTED.map((item) => (
                  <Group key={item} gap="xs" wrap="nowrap" align="center">
                    <ThemeIcon color="gray.5" variant="transparent" size={20}>
                      <IconX size={16} stroke={2.5} />
                    </ThemeIcon>
                    <Text size="sm" c="dimmed">
                      {item}
                    </Text>
                  </Group>
                ))}
              </Stack>
              <Text size="xs" c="dimmed" style={{ wordBreak: 'keep-all' }}>
                위 대상은 일반건축물대장 소관이라 현재 우리집 체크에서 조회할 수 없어요.
              </Text>
            </Stack>
          </Card>
        </SimpleGrid>

        {/* 1차 액션(제품 기능 진입) — 버튼 위계 §2: jippin filled. coral 은 전환 CTA
            (상담·견적) 전용이고 이 페이지엔 전환 CTA 가 없다. 풀폭으로 시선을 모으고,
            클릭 시 곧장 첫 질문(주소)으로 진입한다(퍼널에 별도 인트로 없음).
            서버 컴포넌트라 component={Link} 는 SSG 프리렌더가 깨져 component="a" 유지. */}
        <Button
          component="a"
          href="/home-check/new"
          size="lg"
          color="jippin"
          fullWidth
          rightSection={<IconArrowRight size={18} />}
        >
          내 집 체크 시작
        </Button>

        <Text className="a2ui-legal" style={{ wordBreak: 'keep-all' }}>
          본 서비스는 건축물대장 기재사항을 조회 시점 기준으로 제공하는 참고용 정보이며,
          위법 여부의 최종 판단은 관할 행정청·전문가 확인이 필요합니다.
        </Text>
      </Stack>
    </PageColumn>
  );
}

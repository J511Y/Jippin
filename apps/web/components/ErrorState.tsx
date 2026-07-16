'use client';

import {
  Box,
  Card,
  Code,
  Container,
  Group,
  Stack,
  Text,
  ThemeIcon,
  UnstyledButton
} from '@mantine/core';
import {
  IconAlertTriangle,
  IconLock,
  IconSearchOff,
  IconWifiOff,
  type IconProps
} from '@tabler/icons-react';
import Image from 'next/image';
import Link from 'next/link';
import type { ComponentType, ReactNode } from 'react';
import type { ErrorKind } from '@/lib/api/error-content';

/**
 * 공통 에러 화면. not-found / error 경계가 동일한 룩으로 빈 화면 대신
 * 브랜드 카드를 노출하도록 한다. 표현(presentational) 전용이며 액션 버튼은
 * 호출부가 `actions` 슬롯으로 주입한다.
 *
 * 루트 경계(app/error.tsx, app/not-found.tsx)는 SiteShell 밖에서 렌더돼 헤더가
 * 없으므로, 화면 안에 간단한 브랜드 바(로고 + 집핀, 홈 링크)를 함께 그린다.
 * SiteShell 안쪽에서 재사용하게 되면 헤더가 겹치니 브랜드 바 분리가 필요하다.
 *
 * `requestId` 가 있으면 함께 노출해 사용자가 지원 문의 시 추적값을 전달할 수 있게 한다.
 */

const KIND_ICON: Record<ErrorKind, ComponentType<IconProps>> = {
  auth: IconLock,
  notfound: IconSearchOff,
  network: IconWifiOff,
  server: IconAlertTriangle,
  client: IconAlertTriangle
};

/**
 * 상단 브랜드 바 — SiteShell 헤더의 최소 대체물(높이 60 동일). 에러 화면에서도
 * "집핀 안"이라는 맥락과 홈 복귀 경로를 항상 제공한다. 브랜드 마크의 minHeight 44
 * 는 모바일 터치 타깃 최소 규격(DESIGN.md 반응형 규칙).
 */
function BrandBar() {
  return (
    <Box
      component="header"
      style={{
        height: 60,
        borderBottom: '1px solid var(--jippin-brand-border)',
        background: 'var(--jippin-brand-surface-alt)'
      }}
    >
      <Container size="lg" h="100%">
        <Group h="100%" align="center">
          <UnstyledButton
            component={Link}
            href="/"
            aria-label="집핀 홈"
            style={{ display: 'flex', alignItems: 'center', gap: 8, minHeight: 44 }}
          >
            <Image
              src="/logo.png"
              alt="집핀"
              width={36}
              height={36}
              style={{ display: 'block', width: 36, height: 36 }}
            />
            <Text
              component="span"
              fw={700}
              fz="1.125rem"
              c="var(--jippin-brand-ink)"
              style={{ letterSpacing: '-0.01em' }}
            >
              집핀
            </Text>
          </UnstyledButton>
        </Group>
      </Container>
    </Box>
  );
}

/**
 * 평면도 라인 일러스트 — 제도 격자 + 벽 2개(문 개구부) + 문 호(弧) + 치수선.
 * 색은 전부 브랜드 토큰(격자=grid-major, 벽=professional 네이비, 문=primary 틸).
 * 장식이므로 aria-hidden. kind 아이콘 칩이 방 안(중앙)에 겹쳐 앉는다.
 */
function FloorplanIllustration() {
  return (
    <svg
      viewBox="0 0 240 120"
      width="216"
      height="108"
      aria-hidden="true"
      style={{ display: 'block', maxWidth: '100%' }}
    >
      <defs>
        <pattern
          id="jp-error-grid"
          width="20"
          height="20"
          patternUnits="userSpaceOnUse"
        >
          <path
            d="M20 0H0V20"
            fill="none"
            stroke="var(--jippin-grid-major)"
            strokeWidth="1"
          />
        </pattern>
      </defs>
      {/* 제도 격자 배경 — body 캔버스와 같은 알파 네이비 토큰. */}
      <rect width="240" height="120" fill="url(#jp-error-grid)" />
      {/* 벽 라인 — 좌측 ㄱ자 벽 + 우측 벽(사이가 문 개구부). */}
      <path
        d="M30 96V30h84"
        fill="none"
        stroke="var(--jippin-brand-professional)"
        strokeWidth="5"
        strokeLinecap="square"
      />
      <path
        d="M138 30h72v42"
        fill="none"
        stroke="var(--jippin-brand-professional)"
        strokeWidth="5"
        strokeLinecap="square"
      />
      {/* 문 — 힌지(114,30)에서 내린 문짝 + 스윙 호(점선). */}
      <path
        d="M114 30V54"
        stroke="var(--jippin-brand-primary)"
        strokeWidth="2"
      />
      <path
        d="M138 30A24 24 0 0 1 114 54"
        fill="none"
        stroke="var(--jippin-brand-primary)"
        strokeWidth="1.5"
        strokeDasharray="3 3"
      />
      {/* 치수선 — jp-dimline 모티프(양끝 틱). */}
      <g stroke="var(--jippin-brand-professional)" opacity="0.35">
        <path d="M30 111H210" strokeWidth="1" />
        <path d="M30 106v10M210 106v10" strokeWidth="1" />
      </g>
    </svg>
  );
}

export function ErrorState({
  kind = 'client',
  title,
  description,
  requestId,
  actions
}: {
  kind?: ErrorKind;
  title: string;
  description: string;
  requestId?: string;
  actions?: ReactNode;
}) {
  const Icon = KIND_ICON[kind];

  return (
    <Box>
      <BrandBar />
      <Box
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: 'min(70vh, 560px)',
          padding: 'var(--mantine-spacing-md)'
        }}
      >
        <Card
          shadow="lg"
          radius="lg"
          padding="xl"
          withBorder
          maw={440}
          w="100%"
          style={{ textAlign: 'center', background: 'var(--jippin-brand-surface-alt)' }}
        >
          <Stack align="center" gap="md">
            {/* 평면도 일러스트 위에 kind 아이콘 칩을 겹쳐 브랜드 정체성 + 에러
                종류 신호를 함께 준다(제너릭 아이콘 단독 노출 대체). */}
            <Box style={{ position: 'relative' }}>
              <FloorplanIllustration />
              <ThemeIcon
                size={44}
                radius="xl"
                variant="light"
                color="jippin"
                style={{
                  position: 'absolute',
                  left: '50%',
                  top: '54%',
                  transform: 'translate(-50%, -50%)',
                  // 격자·벽 라인과 겹쳐도 또렷하도록 흰 링을 두른다.
                  boxShadow: '0 0 0 4px var(--jippin-brand-surface-alt)'
                }}
              >
                <Icon size={24} />
              </ThemeIcon>
            </Box>
            <Stack gap={6}>
              <Text fw={700} fz="xl" style={{ wordBreak: 'keep-all' }}>
                {title}
              </Text>
              <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
                {description}
              </Text>
            </Stack>
            {actions ? (
              <Stack gap="xs" w="100%" mt="xs">
                {actions}
              </Stack>
            ) : null}
            {requestId ? (
              <Text size="xs" c="dimmed" mt={4}>
                지원 문의 시 코드: <Code>{requestId}</Code>
              </Text>
            ) : null}
          </Stack>
        </Card>
      </Box>
    </Box>
  );
}

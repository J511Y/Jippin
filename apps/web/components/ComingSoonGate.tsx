'use client';

import { Box, Button, Card, Stack, Text, ThemeIcon } from '@mantine/core';
import { IconArrowRight, IconSparkles } from '@tabler/icons-react';
import Link from 'next/link';
import type { ReactNode } from 'react';

/**
 * 개발 중인 메인 기능(검토/에이전트 세션)을 blur 로 가리고 상담으로 인입시키는 게이트.
 * children(실제 기능 미리보기)은 비상호작용 장식으로 흐릿하게 깔리고, 그 위에 상담 CTA 오버레이를 띄운다.
 */
export function ComingSoonGate({
  children,
  title,
  description
}: {
  children: ReactNode;
  title: string;
  description: string;
}) {
  return (
    <Box style={{ position: 'relative', minHeight: 'min(72vh, 620px)' }}>
      {/* inert: blur 뒤 자식의 키보드 포커스·상호작용·접근성 트리 노출을 모두 차단(P2 a11y). */}
      <Box
        aria-hidden
        inert
        style={{
          filter: 'blur(6px)',
          opacity: 0.5,
          pointerEvents: 'none',
          userSelect: 'none'
        }}
      >
        {children}
      </Box>

      <Box
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 'var(--mantine-spacing-md)',
          background:
            'linear-gradient(180deg, rgba(248,249,250,0.35) 0%, rgba(248,249,250,0.78) 100%)'
        }}
      >
        <Card
          shadow="lg"
          radius="lg"
          padding="xl"
          withBorder
          maw={440}
          w="100%"
          style={{
            textAlign: 'center',
            background: 'var(--jippin-brand-surface-alt)'
          }}
        >
          <Stack align="center" gap="md">
            <ThemeIcon size={60} radius="xl" variant="light" color="jippin">
              <IconSparkles size={30} />
            </ThemeIcon>
            <Stack gap={6}>
              <Text fw={700} fz="xl" style={{ wordBreak: 'keep-all' }}>
                {title}
              </Text>
              <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
                {description}
              </Text>
            </Stack>
            <Stack gap="xs" w="100%" mt="xs">
              <Button
                component={Link}
                href="/leads/new"
                color="coral"
                size="md"
                radius="md"
                fullWidth
                rightSection={<IconArrowRight size={18} />}
              >
                전문가 상담 신청하기
              </Button>
              {/* <Button
                component={Link}
                href="/mypage"
                variant="subtle"
                color="jippin"
                size="sm"
                radius="md"
                fullWidth
              >
                상담 진행 현황 보기
              </Button> */}
            </Stack>
          </Stack>
        </Card>
      </Box>
    </Box>
  );
}

'use client';

import { Box, Card, Code, Stack, Text, ThemeIcon } from '@mantine/core';
import {
  IconAlertTriangle,
  IconLock,
  IconSearchOff,
  IconWifiOff,
  type IconProps
} from '@tabler/icons-react';
import type { ComponentType, ReactNode } from 'react';
import type { ErrorKind } from '@/lib/api/error-content';

/**
 * 공통 에러 화면. not-found / error 경계가 동일한 룩으로 빈 화면 대신
 * 브랜드 카드를 노출하도록 한다. 표현(presentational) 전용이며 액션 버튼은
 * 호출부가 `actions` 슬롯으로 주입한다.
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
          <ThemeIcon size={60} radius="xl" variant="light" color="jippin">
            <Icon size={30} />
          </ThemeIcon>
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
  );
}

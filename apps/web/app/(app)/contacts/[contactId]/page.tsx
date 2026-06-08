import {
  Badge,
  Box,
  Button,
  Card,
  Group,
  Stack,
  Text,
  ThemeIcon,
  Title
} from '@mantine/core';
import { IconCheck, IconClock, IconMapPin } from '@tabler/icons-react';
import type { Metadata } from 'next';

type ContactDetailProps = {
  params: Promise<{ contactId: string }>;
};

export const metadata: Metadata = {
  title: '상담 상세'
};

const STAGES = [
  { label: '신청 접수', state: 'done' as const, note: '상담 신청이 정상 접수되었어요.' },
  { label: '담당자 배정', state: 'done' as const, note: '담당 전문가가 배정되었어요.' },
  { label: '현장 방문', state: 'active' as const, note: '방문 일정을 조율하고 있어요.' },
  { label: '행위허가 검토', state: 'pending' as const, note: '현장 확인 후 진행됩니다.' }
];

export default async function ContactDetailPage({ params }: ContactDetailProps) {
  const { contactId } = await params;

  return (
    <Stack gap="xl">
      <Stack gap="xs">
        <Group gap="xs">
          <Badge color="jippin" variant="light" radius="sm">
            상담 #{contactId}
          </Badge>
          <Badge color="success" variant="light" radius="sm">
            현장 방문 예정
          </Badge>
        </Group>
        <Title order={1} fz="h1" style={{ wordBreak: 'keep-all' }}>
          강남구 ○○로 12 비내력벽
        </Title>
        <Group gap={6} c="dimmed">
          <IconMapPin size={15} />
          <Text size="sm" c="dimmed">
            서울 강남구 ○○로 12
          </Text>
        </Group>
      </Stack>

      <Card withBorder radius="lg" padding="xl">
        <Stack gap="md">
          <Text fw={600}>진행 단계</Text>
          <Stack gap={0}>
            {STAGES.map((stage, i) => {
              const isLast = i === STAGES.length - 1;
              const done = stage.state === 'done';
              const active = stage.state === 'active';
              return (
                <Group key={stage.label} align="flex-start" wrap="nowrap" gap="md">
                  <Stack gap={0} align="center" style={{ alignSelf: 'stretch' }}>
                    <ThemeIcon
                      size={26}
                      radius="xl"
                      color={done || active ? 'jippin' : 'gray'}
                      variant={active ? 'filled' : 'light'}
                    >
                      {done ? (
                        <IconCheck size={14} />
                      ) : active ? (
                        <IconClock size={14} />
                      ) : (
                        <Box w={6} h={6} bg="var(--jippin-brand-border)" style={{ borderRadius: '50%' }} />
                      )}
                    </ThemeIcon>
                    {!isLast ? (
                      <Box
                        style={{
                          width: 2,
                          flex: 1,
                          minHeight: 20,
                          background: done
                            ? 'var(--mantine-color-jippin-3)'
                            : 'var(--jippin-brand-border)'
                        }}
                      />
                    ) : null}
                  </Stack>
                  <Stack gap={2} pb={isLast ? 0 : 'md'}>
                    <Text fw={600} size="sm">
                      {stage.label}
                    </Text>
                    <Text size="sm" c="dimmed">
                      {stage.note}
                    </Text>
                  </Stack>
                </Group>
              );
            })}
          </Stack>
        </Stack>
      </Card>

      <Card withBorder radius="lg" padding="xl">
        <Stack gap="sm">
          <Group justify="space-between" align="center">
            <Text fw={600}>최근 메모</Text>
            <Text size="xs" c="dimmed">
              담당 전문가
            </Text>
          </Group>
          <Card radius="md" padding="md" withBorder>
            <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
              도면상 대상 벽은 비내력벽으로 보이나, 배관 간섭 가능성이 있어 현장에서
              직접 확인이 필요합니다. 방문 일정 조율 후 다시 안내드릴게요.
            </Text>
          </Card>
        </Stack>
      </Card>

      <Group>
        <Button
          component="a"
          href="/contacts"
          variant="subtle"
          color="jippin"
          radius="md"
        >
          ← 상담 목록으로
        </Button>
      </Group>
    </Stack>
  );
}

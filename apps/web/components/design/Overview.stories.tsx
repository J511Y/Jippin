import { Anchor, Card, Code, List, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import type { Meta, StoryObj } from '@storybook/nextjs-vite';

const meta = {
  title: 'Design System/Overview',
  parameters: {
    docs: {
      description: {
        component:
          '집핀 디자인 시스템의 Storybook 진입점입니다. 색, 폰트, 타이포그래피, 컴포넌트 토큰은 docs/design 하위 정본과 lib/mantine-theme.ts를 함께 봅니다.'
      }
    },
    layout: 'padded'
  },
  tags: ['autodocs']
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const Guide: Story = {
  render: () => (
    <Stack maw={920}>
      <Stack gap={6}>
        <Title order={1}>Jippin Design System</Title>
        <Text c="dimmed">
          집핀은 차분한 전문가가 생활어로 비내력벽 철거의 사전검토를 설명해주는 서비스입니다.
          Storybook에서는 이 원칙을 토큰과 컴포넌트 사용 규칙으로 확인합니다.
        </Text>
      </Stack>

      <SimpleGrid cols={{ base: 1, md: 3 }}>
        <Card withBorder p="lg" radius="md">
          <Title order={3}>Colors</Title>
          <Text c="dimmed" mt="xs" size="sm">
            브랜드, CTA, 전문 영역, 상태 색상과 금지 규칙을 확인합니다.
          </Text>
          <Code mt="md">Design System/Colors</Code>
        </Card>
        <Card withBorder p="lg" radius="md">
          <Title order={3}>Typography</Title>
          <Text c="dimmed" mt="xs" size="sm">
            Pretendard 우선 폰트 스택, 모바일 타입스케일, 법적 고지 텍스트 크기를 확인합니다.
          </Text>
          <Code mt="md">Design System/Typography</Code>
        </Card>
        <Card withBorder p="lg" radius="md">
          <Title order={3}>Component Tokens</Title>
          <Text c="dimmed" mt="xs" size="sm">
            Mantine theme 색상명, radius, focus, motion, overlay 기본값을 확인합니다.
          </Text>
          <Code mt="md">Design System/Component Tokens</Code>
        </Card>
      </SimpleGrid>

      <Card withBorder p="lg" radius="md">
        <Title order={2}>Agent usage rules</Title>
        <List mt="md" spacing="xs">
          <List.Item>색상은 HEX를 직접 쓰지 말고 `jippin`, `blueprint`, `coral`, `success`, `warning`, `danger`, `info` 또는 CSS 변수 토큰을 사용합니다.</List.Item>
          <List.Item>새 토큰이 필요하면 `docs/design/*` 정본과 `lib/mantine-theme.ts`를 같은 PR에서 갱신합니다.</List.Item>
          <List.Item>법적 고지 문구는 줄이거나 바꾸지 않습니다.</List.Item>
          <List.Item>모바일 first 기준으로 360-414px 폭에서 텍스트 줄바꿈과 CTA 배치를 먼저 확인합니다.</List.Item>
        </List>
      </Card>

      <Text c="dimmed" size="sm">
        정본 문서: <Anchor href="../../docs/design/DESIGN.md">docs/design/DESIGN.md</Anchor>,{' '}
        <Anchor href="../../docs/design/COLOR_SYSTEM.md">COLOR_SYSTEM.md</Anchor>,{' '}
        <Anchor href="../../docs/design/TYPOGRAPHY.md">TYPOGRAPHY.md</Anchor>,{' '}
        <Anchor href="../../docs/design/BRAND.md">BRAND.md</Anchor>
      </Text>
    </Stack>
  )
};

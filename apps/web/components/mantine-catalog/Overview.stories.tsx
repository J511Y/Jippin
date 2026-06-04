import { Anchor, Badge, Card, Code, List, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core';
import type { Meta, StoryObj } from '@storybook/nextjs-vite';

const categories = [
  {
    area: 'Actions',
    components: 'Button, ActionIcon, Menu, Tooltip',
    story: 'Mantine Catalog/Actions'
  },
  {
    area: 'Forms',
    components: 'TextInput, Select, Checkbox, SegmentedControl, NumberInput, Textarea, DateInput',
    story: 'Mantine Catalog/Forms'
  },
  {
    area: 'Mobile Overlays',
    components: 'Drawer, Modal, Bottom sheet pattern',
    story: 'Mantine Catalog/Mobile Overlays'
  },
  {
    area: 'Feedback',
    components: 'Alert, Notification, Progress, Skeleton, Loader',
    story: 'Mantine Catalog/Feedback'
  },
  {
    area: 'Navigation',
    components: 'Tabs, Breadcrumbs',
    story: 'Mantine Catalog/Navigation'
  },
  {
    area: 'Workflow Progress',
    components: 'Stepper, Progress, Pagination',
    story: 'Mantine Catalog/Workflow Progress'
  },
  {
    area: 'Data Display / Layout',
    components: 'Card, Badge, Table, Timeline, Accordion, Grid, Stack',
    story: 'Mantine Catalog/Data Display'
  }
] as const;

const meta = {
  title: 'Mantine Catalog/Overview',
  parameters: {
    docs: {
      description: {
        component:
          '집핀의 기본 UI는 Mantine을 우선 사용합니다. 이 Catalog는 공식 Mantine 전체 문서를 대체하지 않고, 집핀 화면에서 자주 쓰는 모바일 우선 조합과 에이전트 사용 규칙을 정리한 Storybook 진입점입니다.'
      }
    },
    layout: 'padded'
  },
  tags: ['autodocs']
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const AgentUsageGuide: Story = {
  render: () => (
    <Stack gap="lg" maw={960}>
      <Stack gap={6}>
        <Title order={1}>Mantine Catalog</Title>
        <Text c="dimmed">
          새 화면을 만들 때는 Mantine 공식 컴포넌트를 먼저 조합하고, 집핀 정책을 반복해서
          캡슐화해야 할 때만 별도 래퍼를 만듭니다.
        </Text>
      </Stack>

      <SimpleGrid cols={{ base: 1, md: 3 }}>
        <Card withBorder radius="md" p="md">
          <Badge color="jippin" variant="light">1. Use Mantine first</Badge>
          <Text mt="sm" size="sm">
            버튼, 폼, Drawer, Modal, Toast, Table 등은 `@mantine/core`와 관련 패키지를 우선 사용합니다.
          </Text>
        </Card>
        <Card withBorder radius="md" p="md">
          <Badge color="blueprint" variant="light">2. Apply Jippin theme</Badge>
          <Text mt="sm" size="sm">
            색상은 `jippin`, `blueprint`, `coral`, `success`, `warning`, `danger`, `info` 토큰을 사용합니다.
          </Text>
        </Card>
        <Card withBorder radius="md" p="md">
          <Badge color="warning" variant="light">3. Mobile first</Badge>
          <Text mt="sm" size="sm">
            Overlay와 Form은 360-414px 모바일 폭에서 먼저 확인하고, 데스크톱은 확장으로 봅니다.
          </Text>
        </Card>
      </SimpleGrid>

      <Card withBorder radius="md" p="lg">
        <Title order={2}>Before components: design foundations</Title>
        <List mt="md" spacing="xs">
          <List.Item>색상과 의미는 <Code>Design System/Colors</Code>에서 확인합니다.</List.Item>
          <List.Item>폰트, 타입스케일, 법적 고지 텍스트 크기는 <Code>Design System/Typography</Code>에서 확인합니다.</List.Item>
          <List.Item>Mantine theme 매핑과 radius/focus/motion 기본값은 <Code>Design System/Component Tokens</Code>에서 확인합니다.</List.Item>
        </List>
      </Card>

      <Card withBorder radius="md" p="lg">
        <Title order={2}>Storybook sections</Title>
        <Table mt="md" striped withTableBorder withColumnBorders>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Area</Table.Th>
              <Table.Th>Components</Table.Th>
              <Table.Th>Storybook section</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {categories.map((category) => (
              <Table.Tr key={category.area}>
                <Table.Td>{category.area}</Table.Td>
                <Table.Td>{category.components}</Table.Td>
                <Table.Td>
                  <Code>{category.story}</Code>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Card>

      <Card withBorder radius="md" p="lg">
        <Title order={2}>Agent rules</Title>
        <List mt="md" spacing="xs">
          <List.Item>새 UI는 `components/ui/index.ts`의 Mantine re-export 또는 `@mantine/*` 직접 import를 사용합니다.</List.Item>
          <List.Item>법적 고지, 판정 문구, 색상 의미는 `docs/design/*` 정본을 우선합니다.</List.Item>
          <List.Item>Drawer/Modal은 모바일 story에서 먼저 확인하고, 내용이 길면 스크롤과 하단 CTA 고정을 점검합니다.</List.Item>
          <List.Item>Toast/Notification은 보조 피드백입니다. 법적 고지나 중요한 판정 결과를 Toast에만 의존하지 않습니다.</List.Item>
          <List.Item>컴포넌트 추가나 사용 패턴 변경 시 같은 PR에서 Storybook story를 갱신합니다.</List.Item>
        </List>
      </Card>

      <Text c="dimmed" size="sm">
        공식 상세 API는{' '}
        <Anchor href="https://mantine.dev/core/package/" target="_blank">
          Mantine docs
        </Anchor>
        를 확인합니다. 이 Catalog는 집핀에서 승인된 조합을 빠르게 고르는 용도입니다.
      </Text>
    </Stack>
  )
};

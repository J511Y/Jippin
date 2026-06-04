import { Button, Card, Code, FocusTrap, Group, Paper, Stack, Table, Text, Title } from '@mantine/core';
import type { Meta, StoryObj } from '@storybook/nextjs-vite';

const rows = [
  ['primaryColor', 'jippin', '일반 주요 액션과 선택 상태'],
  ['defaultRadius', 'md', '카드·입력·버튼 기본 radius'],
  ['activeClassName', 'mantine-active', '클릭 시 1px 눌림 효과'],
  ['focus ring', 'brand.primary', '키보드 접근성 포커스'],
  ['body background', 'brand.surface', '페이지 표면'],
  ['text', 'brand.ink', '본문 대표 텍스트']
] as const;

const meta = {
  title: 'Design System/Component Tokens',
  parameters: {
    docs: {
      description: {
        component:
          'Mantine theme에 적용된 집핀 컴포넌트 토큰입니다. 실제 구현은 lib/mantine-theme.ts와 app/globals.css에 있습니다.'
      }
    },
    layout: 'padded'
  },
  tags: ['autodocs']
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const MantineThemeMapping: Story = {
  render: () => (
    <Stack maw={860}>
      <Title order={2}>Mantine theme mapping</Title>
      <Table striped withTableBorder withColumnBorders>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Token</Table.Th>
            <Table.Th>Value</Table.Th>
            <Table.Th>Use</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map(([token, value, use]) => (
            <Table.Tr key={token}>
              <Table.Td><Code>{token}</Code></Table.Td>
              <Table.Td>{value}</Table.Td>
              <Table.Td>{use}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <Code block>{`<MantineProvider
  cssVariablesResolver={jippinCssVariablesResolver}
  defaultColorScheme="light"
  theme={jippinTheme}
>
  {children}
</MantineProvider>`}</Code>
    </Stack>
  )
};

export const RadiusAndMotion: Story = {
  render: () => (
    <Stack maw={860}>
      <Title order={2}>Radius and interaction</Title>
      <Group>
        <Button color="jippin">기본 버튼</Button>
        <Button color="coral" c="var(--jippin-brand-cta-fg)">CTA</Button>
        <Button color="blueprint">전문 영역</Button>
      </Group>
      <Group align="stretch">
        <Card withBorder p="md" radius="md" shadow="xs" w={240}>
          <Text fw={600}>Card radius md</Text>
          <Text c="dimmed" size="sm">반복 카드와 패널은 과한 둥근 모서리를 피합니다.</Text>
        </Card>
        <Paper withBorder p="md" radius="md" shadow="xs" w={240}>
          <Text fw={600}>Surface</Text>
          <Text c="dimmed" size="sm">표면은 brand.surface와 흰색을 중심으로 구성합니다.</Text>
        </Paper>
      </Group>
    </Stack>
  )
};

export const FocusExample: Story = {
  render: () => (
    <FocusTrap active>
      <Stack maw={480}>
        <Title order={2}>Keyboard focus</Title>
        <Text c="dimmed" size="sm">
          포커스 링은 제거하지 않습니다. 키보드 사용자가 현재 위치를 확인할 수 있어야 합니다.
        </Text>
        <Group>
          <Button color="jippin">첫 번째 액션</Button>
          <Button color="gray" variant="light">두 번째 액션</Button>
        </Group>
      </Stack>
    </FocusTrap>
  )
};

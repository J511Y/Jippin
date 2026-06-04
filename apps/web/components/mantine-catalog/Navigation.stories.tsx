import { Anchor, Breadcrumbs, Code, Stack, Table, Tabs, Text, Title } from '@mantine/core';
import type { Meta, StoryObj } from '@storybook/nextjs-vite';

const meta = {
  title: 'Mantine Catalog/Navigation',
  parameters: {
    docs: {
      description: {
        component:
          '모바일에서는 깊은 네비게이션보다 단계 표시와 탭을 제한적으로 사용합니다. 긴 탭 라벨은 피하고 2-4개 수준으로 유지합니다.'
      }
    },
    layout: 'centered'
  },
  tags: ['autodocs']
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const UsageGuide: Story = {
  render: () => (
    <Stack maw={760}>
      <Title order={2}>Navigation guide</Title>
      <Text c="dimmed">
        Navigation 섹션은 사용자가 화면 사이를 이동하거나 같은 화면 안의 관점을 바꾸는 컴포넌트만 둡니다.
        진행 상태는 `Mantine Catalog/Workflow Progress`에서 확인합니다.
      </Text>
      <Table striped withTableBorder withColumnBorders>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Component</Table.Th>
            <Table.Th>Use when</Table.Th>
            <Table.Th>Avoid</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          <Table.Tr>
            <Table.Td><Code>Tabs</Code></Table.Td>
            <Table.Td>요약/도면/근거처럼 같은 결과를 다른 관점으로 볼 때</Table.Td>
            <Table.Td>서로 다른 작업 흐름 이동</Table.Td>
          </Table.Tr>
          <Table.Tr>
            <Table.Td><Code>Breadcrumbs</Code></Table.Td>
            <Table.Td>데스크톱 또는 문서형 화면의 현재 위치 표시</Table.Td>
            <Table.Td>모바일 주요 조작 UI</Table.Td>
          </Table.Tr>
        </Table.Tbody>
      </Table>
    </Stack>
  )
};

export const TabsAndBreadcrumbs: Story = {
  parameters: {
    docs: {
      description: {
        story: '`Tabs`는 한 화면의 관점 전환에만 사용합니다. 모바일에서는 2-4개 탭, 짧은 라벨을 유지합니다.'
      },
      source: {
        code: `<Tabs defaultValue="summary" color="jippin">
  <Tabs.List grow>
    <Tabs.Tab value="summary">요약</Tabs.Tab>
    <Tabs.Tab value="drawing">도면</Tabs.Tab>
    <Tabs.Tab value="law">근거</Tabs.Tab>
  </Tabs.List>
</Tabs>`
      }
    }
  },
  render: () => (
    <Stack w="min(520px, 100vw - 32px)">
      <Breadcrumbs>
        <Anchor href="#">사전검토</Anchor>
        <Anchor href="#">도면</Anchor>
        <Text>후보 확인</Text>
      </Breadcrumbs>
      <Tabs defaultValue="summary" color="jippin">
        <Tabs.List grow>
          <Tabs.Tab value="summary">요약</Tabs.Tab>
          <Tabs.Tab value="drawing">도면</Tabs.Tab>
          <Tabs.Tab value="law">근거</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel pt="md" value="summary">
          <Text size="sm">지금 정보만으로는 판단이 어렵습니다.</Text>
        </Tabs.Panel>
        <Tabs.Panel pt="md" value="drawing">
          <Text size="sm">도면 후보 영역을 확인합니다.</Text>
        </Tabs.Panel>
        <Tabs.Panel pt="md" value="law">
          <Text size="sm">근거 법령을 확인합니다.</Text>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  )
};

import { Button, Code, Group, Pagination, Progress, Stack, Stepper, Table, Text, Title } from '@mantine/core';
import { IconFileUpload, IconMessageCircle, IconReportAnalytics } from '@tabler/icons-react';
import type { Meta, StoryObj } from '@storybook/nextjs-vite';

const meta = {
  title: 'Mantine Catalog/Workflow Progress',
  parameters: {
    docs: {
      description: {
        component:
          'Stepper, Progress, Pagination은 화면 이동 자체보다 진행 상태나 다단계 흐름을 표현합니다. 그래서 Navigation과 분리합니다.'
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
      <Title order={2}>Workflow progress guide</Title>
      <Table striped withTableBorder withColumnBorders>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Component</Table.Th>
            <Table.Th>Use when</Table.Th>
            <Table.Th>Required props</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          <Table.Tr>
            <Table.Td><Code>Stepper</Code></Table.Td>
            <Table.Td>업로드 → 검토 → 상담처럼 순서가 있는 흐름</Table.Td>
            <Table.Td><Code>active</Code>, 각 <Code>Stepper.Step label</Code></Table.Td>
          </Table.Tr>
          <Table.Tr>
            <Table.Td><Code>Progress</Code></Table.Td>
            <Table.Td>분석 진행률, 업로드 진행률</Table.Td>
            <Table.Td><Code>value</Code>, 접근 가능한 주변 설명</Table.Td>
          </Table.Tr>
          <Table.Tr>
            <Table.Td><Code>Pagination</Code></Table.Td>
            <Table.Td>리스트/검색 결과 페이지 이동</Table.Td>
            <Table.Td><Code>total</Code>, <Code>value</Code>, <Code>onChange</Code></Table.Td>
          </Table.Tr>
        </Table.Tbody>
      </Table>
    </Stack>
  )
};

export const StepperFlow: Story = {
  parameters: {
    docs: {
      source: {
        code: `<Stepper active={1} color="jippin">
  <Stepper.Step label="업로드" description="주소·도면" />
  <Stepper.Step label="검토" description="AI 판단" />
  <Stepper.Step label="상담" description="전환" />
</Stepper>`
      }
    }
  },
  render: () => (
    <Stack w="min(560px, 100vw - 32px)">
      <Stepper active={1} color="jippin">
        <Stepper.Step icon={<IconFileUpload size={18} aria-hidden />} label="업로드" description="주소·도면" />
        <Stepper.Step icon={<IconReportAnalytics size={18} aria-hidden />} label="검토" description="AI 판단" />
        <Stepper.Step icon={<IconMessageCircle size={18} aria-hidden />} label="상담" description="전환" />
      </Stepper>
      <Progress aria-label="도면 분석 진행률" color="jippin" value={62} />
    </Stack>
  )
};

export const PaginationForLists: Story = {
  render: () => (
    <Group justify="space-between" w="min(420px, 100vw - 32px)">
      <Text size="sm">검색 결과 2 / 4 페이지</Text>
      <Pagination color="jippin" total={4} value={2} />
      <Button color="jippin">다음</Button>
    </Group>
  )
};

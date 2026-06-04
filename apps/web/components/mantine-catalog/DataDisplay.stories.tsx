import { Accordion, Badge, Card, Grid, Group, Stack, Table, Text, ThemeIcon, Timeline, Title } from '@mantine/core';
import { IconCircleCheck, IconFileReport, IconHome, IconScale } from '@tabler/icons-react';
import type { Meta, StoryObj } from '@storybook/nextjs-vite';

const meta = {
  title: 'Mantine Catalog/Data Display',
  parameters: {
    docs: {
      description: {
        component:
          '결과·근거·리포트 영역은 Card, Badge, Table, Timeline, Accordion을 조합합니다. 모바일 표는 2-3열 이하로 제한하고, 상세는 Accordion으로 접습니다.'
      }
    },
    layout: 'padded'
  },
  tags: ['autodocs']
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const CardsAndTimeline: Story = {
  render: () => (
    <Grid maw={920}>
      <Grid.Col span={{ base: 12, md: 6 }}>
        <Card p="lg" radius="md" shadow="sm" withBorder>
          <Group align="flex-start">
            <ThemeIcon color="jippin" radius="md" size="lg" variant="light">
              <IconHome size={20} aria-hidden />
            </ThemeIcon>
            <Stack gap={4}>
              <Title order={3}>사전검토 요약</Title>
              <Text c="dimmed" size="sm">도면 분석 결과와 법령 근거를 한 화면에서 확인합니다.</Text>
              <Badge color="warning" variant="light">추가 확인 필요</Badge>
            </Stack>
          </Group>
        </Card>
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 6 }}>
        <Timeline active={1} color="jippin" bulletSize={28} lineWidth={2}>
          <Timeline.Item bullet={<IconCircleCheck size={14} aria-hidden />} title="도면 업로드">
            <Text c="dimmed" size="sm">평면도 파일을 받았습니다.</Text>
          </Timeline.Item>
          <Timeline.Item bullet={<IconScale size={14} aria-hidden />} title="법령 검토">
            <Text c="dimmed" size="sm">행위허가 조건과 충돌 여부를 확인합니다.</Text>
          </Timeline.Item>
          <Timeline.Item bullet={<IconFileReport size={14} aria-hidden />} title="리포트 생성">
            <Text c="dimmed" size="sm">결과 요약과 고지를 포함합니다.</Text>
          </Timeline.Item>
        </Timeline>
      </Grid.Col>
    </Grid>
  )
};

export const TableAndAccordion: Story = {
  render: () => (
    <Stack maw={760}>
      <Table striped withTableBorder withColumnBorders>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>항목</Table.Th>
            <Table.Th>상태</Table.Th>
            <Table.Th>근거</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          <Table.Tr>
            <Table.Td>비내력벽 후보</Table.Td>
            <Table.Td><Badge color="success" variant="light">확인</Badge></Table.Td>
            <Table.Td>도면 region-12</Table.Td>
          </Table.Tr>
          <Table.Tr>
            <Table.Td>행위허가 조건</Table.Td>
            <Table.Td><Badge color="warning" variant="light">추가 확인</Badge></Table.Td>
            <Table.Td>관할 행정기관 판단 필요</Table.Td>
          </Table.Tr>
        </Table.Tbody>
      </Table>
      <Accordion variant="separated">
        <Accordion.Item value="law">
          <Accordion.Control>근거 법령</Accordion.Control>
          <Accordion.Panel>공동주택관리법 §35, 시행령 §3 가.</Accordion.Panel>
        </Accordion.Item>
        <Accordion.Item value="notice">
          <Accordion.Control>법적 고지</Accordion.Control>
          <Accordion.Panel>
            본 서비스는 AI 기반 사전 검토 시스템입니다. 최종 행위허가 여부는 관할 행정기관 판단에 따라 달라질 수 있습니다.
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>
    </Stack>
  )
};

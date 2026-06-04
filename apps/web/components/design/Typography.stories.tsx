import { Card, Code, List, Stack, Table, Text, Title } from '@mantine/core';
import type { Meta, StoryObj } from '@storybook/nextjs-vite';

const fontStack =
  "'Pretendard Variable', 'Pretendard', -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', system-ui, 'Segoe UI', Roboto, sans-serif";

const rows = [
  ['display', '1순위 결과 헤더', '24 / 32', '600'],
  ['h1', '페이지 헤더', '22 / 30', '600'],
  ['h2', '섹션 헤더', '18 / 26', '600'],
  ['h3', '카드 헤더·모달 타이틀', '16 / 24', '600'],
  ['body', '본문 기본', '15 / 24', '400'],
  ['caption', '메타·도움말·캡션', '13 / 20', '400'],
  ['legal', '법적 고지 문구', '12 / 20', '400']
] as const;

const meta = {
  title: 'Design System/Typography',
  parameters: {
    docs: {
      description: {
        component:
          '집핀 타이포그래피와 폰트 스택입니다. 모바일 360-414px 폭을 기준으로 하며 docs/design/TYPOGRAPHY.md가 정본입니다.'
      }
    },
    layout: 'padded'
  },
  tags: ['autodocs']
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const FontStack: Story = {
  render: () => (
    <Stack maw={860}>
      <Title order={2}>Font stack</Title>
      <Card withBorder p="lg" radius="md">
        <Text fw={600}>한국어 본문</Text>
        <Code block mt="sm">{fontStack}</Code>
        <Text c="dimmed" mt="md" size="sm">
          Pretendard를 우선 사용하고, 미설치 환경에서는 OS 한국어 산세리프와 system-ui로 fallback합니다.
          외부 CDN 의존 대신 self-host를 권장합니다.
        </Text>
      </Card>
    </Stack>
  )
};

export const TypeScale: Story = {
  render: () => (
    <Stack maw={860}>
      <Title order={2}>Mobile type scale</Title>
      <Table striped withTableBorder withColumnBorders>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Token</Table.Th>
            <Table.Th>Use</Table.Th>
            <Table.Th>Size / line-height</Table.Th>
            <Table.Th>Weight</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map(([token, use, size, weight]) => (
            <Table.Tr key={token}>
              <Table.Td><Code>{token}</Code></Table.Td>
              <Table.Td>{use}</Table.Td>
              <Table.Td>{size}</Table.Td>
              <Table.Td>{weight}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Stack>
  )
};

export const Samples: Story = {
  render: () => (
    <Card p="xl" radius="md" shadow="sm" withBorder maw={860}>
      <Stack gap="md">
        <Title fz={24} lh="2rem" order={1}>display · 지금 정보 기준으로는 가능성이 있습니다.</Title>
        <Title order={1}>h1 · 사전검토 결과</Title>
        <Title order={2}>h2 · 근거 요약</Title>
        <Title order={3}>h3 · 도면 후보 영역</Title>
        <Text size="md">
          body · 집핀은 차분한 전문가가 생활어로 비내력벽 철거의 사전검토를 설명해주는 AI 서비스입니다.
        </Text>
        <Text c="dimmed" size="sm">
          caption · 도면 분석 결과는 제출된 이미지 품질에 따라 달라질 수 있습니다.
        </Text>
        <Text c="var(--jippin-notice-legal)" size="xs">
          legal · 본 서비스는 AI 기반 사전 검토 시스템입니다. 최종 행위허가 여부는 관할 행정기관 판단에 따라 달라질 수 있습니다.
        </Text>
      </Stack>
    </Card>
  )
};

export const WritingRules: Story = {
  render: () => (
    <Stack maw={860}>
      <Title order={2}>Writing rules</Title>
      <List spacing="xs">
        <List.Item>히어로 타이포 금지. 결과 화면에서도 display보다 큰 단계를 만들지 않습니다.</List.Item>
        <List.Item>결과 헤더는 가능/불가/보류를 단정하지 않고 가능성·근거·추가 확인으로 표현합니다.</List.Item>
        <List.Item>버튼·칩·라벨은 한국어 줄바꿈을 고려해 폭을 고정하지 않습니다.</List.Item>
        <List.Item>법적 고지는 정본 문구를 그대로 쓰고 이미지가 아닌 선택 가능한 텍스트로 노출합니다.</List.Item>
      </List>
    </Stack>
  )
};

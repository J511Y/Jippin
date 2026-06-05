import { Badge, Card, Code, Group, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core';
import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { jippinTokens } from '@/lib/mantine-theme';

const brandTokens = [
  ['brand.primary', 'jippin.6', jippinTokens.brand.primary, '주요 인터랙션·선택 상태·포커스'],
  ['brand.ink', 'black', jippinTokens.brand.ink, '헤딩·본문 진한 텍스트'],
  ['brand.copy', 'dimmed', jippinTokens.brand.copy, '부가 설명·캡션'],
  ['brand.surface', '--mantine-color-body', jippinTokens.brand.surface, '페이지 배경'],
  ['brand.border', '--jippin-brand-border', jippinTokens.brand.border, '경계선'],
  ['brand.cta', 'coral.5', jippinTokens.brand.cta, '상담·견적 전환 CTA'],
  ['brand.professional', 'blueprint.6', jippinTokens.brand.professional, '리포트·도면 전문 영역']
] as const;

const statusTokens = [
  ['status.success', 'success.6', jippinTokens.status.success, '가능 / 충족'],
  // danger 만 .5 를 사용한다. .6 (#A52F24) 은 너무 어두워 흰 라벨이 무겁게 보였다.
  // .5 (#C0392B) 위 #FFFFFF 라벨은 WCAG AA (~4.6:1) 를 통과한다. COLOR_SYSTEM §6 의 대비표 참고.
  ['status.danger', 'danger.5', jippinTokens.status.danger, '불가 / 제한 (danger.5 사용 — 흰 라벨 가독성)'],
  ['status.warning', 'warning.6', jippinTokens.status.warning, '보류 / 추가 확인'],
  ['status.info', 'info.6', jippinTokens.status.info, '중립 정보']
] as const;

function TokenGrid({ tokens }: { tokens: readonly (readonly [string, string, string, string])[] }) {
  return (
    <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm" maw={860}>
      {tokens.map(([name, mantineToken, hex, role]) => (
        <Card key={name} p="md" radius="md" shadow="xs" withBorder>
          <Group align="center" gap="sm">
            <div
              aria-hidden
              style={{
                background: hex,
                border: '1px solid var(--jippin-brand-border)',
                borderRadius: 'var(--mantine-radius-md)',
                height: 44,
                width: 44
              }}
            />
            <Stack gap={0}>
              <Text ff="monospace" fw={600} size="sm">{name}</Text>
              <Text c="dimmed" size="xs">{hex}</Text>
              <Code>{mantineToken}</Code>
            </Stack>
          </Group>
          <Text c="dimmed" mt="sm" size="sm">{role}</Text>
        </Card>
      ))}
    </SimpleGrid>
  );
}

const meta = {
  title: 'Design System/Colors',
  parameters: {
    docs: {
      description: {
        component:
          '집핀 색상 토큰과 Mantine theme 매핑입니다. 색상 의미는 docs/design/COLOR_SYSTEM.md가 정본입니다.'
      }
    },
    layout: 'padded'
  },
  tags: ['autodocs']
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const BrandColors: Story = {
  render: () => <TokenGrid tokens={brandTokens} />
};

export const StatusColors: Story = {
  render: () => <TokenGrid tokens={statusTokens} />
};

export const UsageRules: Story = {
  render: () => (
    <Stack maw={860}>
      <Title order={2}>Color usage rules</Title>
      <Table striped withTableBorder withColumnBorders>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Token</Table.Th>
            <Table.Th>Use</Table.Th>
            <Table.Th>Avoid</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          <Table.Tr>
            <Table.Td><Badge color="jippin">jippin</Badge></Table.Td>
            <Table.Td>주요 버튼, 선택 상태, 포커스</Table.Td>
            <Table.Td>본문 텍스트 색</Table.Td>
          </Table.Tr>
          <Table.Tr>
            <Table.Td><Badge color="coral" c="var(--jippin-brand-cta-fg)">coral</Badge></Table.Td>
            <Table.Td>상담 신청, 견적 요청 같은 전환 CTA</Table.Td>
            <Table.Td>한 화면의 여러 버튼에 반복 사용</Table.Td>
          </Table.Tr>
          <Table.Tr>
            <Table.Td><Badge color="blueprint">blueprint</Badge></Table.Td>
            <Table.Td>리포트, 도면 분석, 관리자, 전문 영역</Table.Td>
            <Table.Td>메인 채팅 화면의 과한 강조</Table.Td>
          </Table.Tr>
          <Table.Tr>
            <Table.Td><Badge color="warning">status</Badge></Table.Td>
            <Table.Td>가능/불가/보류/정보 의미 전달</Table.Td>
            <Table.Td>색만으로 의미 전달</Table.Td>
          </Table.Tr>
        </Table.Tbody>
      </Table>
    </Stack>
  )
};

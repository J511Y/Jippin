import { Badge, Button, Card, Group, Stack, Text, Title } from '@mantine/core';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '가격'
};

const plans = [
  {
    name: 'AI 사전검토',
    price: '무료',
    description: '도면과 주소만으로 받는 AI 행위허가 가능성 사전검토.',
    cta: { href: '/sessions/new', label: '사전검토 시작', color: 'jippin' as const }
  },
  {
    name: '전문가 단건 상담',
    price: '문의',
    description: '담당자가 사전검토 결과를 토대로 단건 상담을 진행해요.',
    cta: { href: '/leads/new', label: '상담 신청하기', color: 'coral' as const }
  },
  {
    name: '행위허가 풀 서포트',
    price: '문의',
    description: '현장 확인부터 행위허가 신청까지 전체 과정을 함께해요.',
    cta: { href: '/leads/new', label: '상담 신청하기', color: 'coral' as const }
  }
];

export default function PricesPage() {
  return (
    <Stack gap="lg">
      <Stack gap="xs">
        <Title order={1}>가격</Title>
        <Text c="dimmed" size="sm" style={{ wordBreak: 'keep-all' }}>
          MVP placeholder 가격표입니다. 실제 가격 정책과 상품 구성은 후속 이슈에서
          확정됩니다.
        </Text>
      </Stack>

      <Stack gap="sm">
        {plans.map((plan) => (
          <Card key={plan.name} withBorder radius="md" padding="md">
            <Stack gap="sm">
              <Group justify="space-between" align="flex-start">
                <Text fw={600}>{plan.name}</Text>
                <Badge color="jippin" variant="light" radius="sm">
                  {plan.price}
                </Badge>
              </Group>
              <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
                {plan.description}
              </Text>
              <Button
                component="a"
                href={plan.cta.href}
                size="md"
                color={plan.cta.color}
                radius="md"
                fullWidth
              >
                {plan.cta.label}
              </Button>
            </Stack>
          </Card>
        ))}
      </Stack>
    </Stack>
  );
}

import { Badge, Button, Card, Group, SimpleGrid, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { IconFileReport, IconHome, IconListCheck } from '@tabler/icons-react';
import type { Meta, StoryObj } from '@storybook/nextjs-vite';

const meta = {
  title: 'UI/Card',
  component: Card,
  parameters: {
    layout: 'centered'
  },
  tags: ['autodocs']
} satisfies Meta<typeof Card>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Basic: Story = {
  render: () => (
    <Card p="lg" radius="md" shadow="sm" withBorder w={500}>
      <Group justify="space-between" mb="md">
        <Stack gap={4}>
          <Title order={3}>사전검토 요약</Title>
          <Text c="dimmed" size="sm">도면 분석 결과와 법령 근거를 한 화면에서 확인합니다.</Text>
        </Stack>
        <Button color="jippin" size="xs" variant="light">수정</Button>
      </Group>
      <SimpleGrid cols={2}>
        <Stack gap={2}>
          <Text c="dimmed" size="xs">주소</Text>
          <Text fw={600} size="sm">서울시 송파구 예시동</Text>
        </Stack>
        <Stack gap={2}>
          <Text c="dimmed" size="xs">검토 상태</Text>
          <Badge color="warning" variant="light">추가 확인 필요</Badge>
        </Stack>
      </SimpleGrid>
    </Card>
  )
};

export const ProfessionalReport: Story = {
  render: () => (
    <Card p="lg" radius="md" shadow="sm" withBorder w={500}>
      <Group align="flex-start">
        <ThemeIcon color="blueprint" radius="md" size="lg">
          <IconFileReport size={20} aria-hidden />
        </ThemeIcon>
        <Stack gap="xs" style={{ flex: 1 }}>
          <Title order={3}>전문 검토 영역</Title>
          <Text c="dimmed" size="sm">
            리포트·도면·관리자 영역에서는 Blueprint Navy 보조 축을 제한적으로 사용합니다.
          </Text>
          <Card bg="blueprint.6" c="white" mt="sm" p="md" radius="md">
            <Text fw={600} size="sm">근거 법령</Text>
            <Text mt={6} size="sm">공동주택관리법 §35, 시행령 §3 가.</Text>
          </Card>
        </Stack>
      </Group>
    </Card>
  )
};

export const EmptyState: Story = {
  render: () => (
    <Card p="xl" radius="md" shadow="sm" ta="center" withBorder w={500}>
      <ThemeIcon color="jippin" m="0 auto" radius="md" size={48} variant="light">
        <IconHome size={24} aria-hidden />
      </ThemeIcon>
      <Title mt="md" order={3}>아직 검토할 도면이 없습니다.</Title>
      <Text c="dimmed" mt="xs" size="sm">
        주소와 도면을 알려 주세요. 사전검토를 시작하겠습니다.
      </Text>
      <Button color="jippin" leftSection={<IconListCheck size={16} aria-hidden />} mt="lg">
        사전검토 시작
      </Button>
    </Card>
  )
};

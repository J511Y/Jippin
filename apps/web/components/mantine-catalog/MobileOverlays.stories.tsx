import { Button, Code, Drawer, Group, Modal, Paper, Stack, Table, Text, Title } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconFileReport, IconMapPin, IconX } from '@tabler/icons-react';
import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { LegalNotice } from '@/components/LegalNotice';

const meta = {
  title: 'Mantine Catalog/Mobile Overlays',
  parameters: {
    docs: {
      description: {
        component:
          '모바일 우선 overlay 확인용 Catalog입니다. Drawer는 하단 bottom sheet 패턴을 기본으로, 상세/필터/도면 후보 선택에 사용합니다. Modal은 짧은 확인·다운로드·중요 결정에만 제한적으로 사용합니다.'
      }
    },
    layout: 'centered',
    viewport: {
      defaultViewport: 'mobile1'
    }
  },
  tags: ['autodocs']
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

type OverlayDemoProps = {
  openedByDefault?: boolean;
};

function MobileBottomSheetDemo({ openedByDefault = true }: OverlayDemoProps) {
  const [opened, { open, close }] = useDisclosure(openedByDefault);

  return (
    <Paper p="lg" radius="md" shadow="sm" withBorder w="min(390px, 100vw - 32px)">
      <Stack>
        <Title order={3}>도면 후보 선택</Title>
        <Text c="dimmed" size="sm">
          모바일에서는 하단 bottom sheet를 먼저 사용합니다. 긴 내용은 sheet 내부에서 스크롤됩니다.
        </Text>
        <Button color="jippin" leftSection={<IconMapPin size={16} aria-hidden />} onClick={open} fullWidth>
          하단 sheet 열기
        </Button>
      </Stack>
      <Drawer
        closeButtonProps={{ 'aria-label': '닫기' }}
        opened={opened}
        onClose={close}
        position="bottom"
        radius="lg"
        size="86dvh"
        title="도면 후보 상세"
        transitionProps={{ transition: 'slide-up', duration: 180 }}
      >
        <Stack>
          <Text size="sm">
            평면도에서 비내력벽 후보를 표시했습니다. 색칠된 부분을 눌러 자세히 보세요.
          </Text>
          <Paper bg="jippin.0" p="md" radius="md" withBorder>
            <Text fw={600} size="sm">후보 영역 region-12</Text>
            <Text c="dimmed" mt={4} size="sm">신뢰도 82%, 사용자가 선택한 철거 영역과 일부 겹칩니다.</Text>
          </Paper>
          <Paper bg="warning.0" p="md" radius="md" withBorder>
            <Text fw={600} size="sm">추가 확인 필요</Text>
            <Text c="dimmed" mt={4} size="sm">도면 일부가 흐려 관할 행정기관 제출 전 추가 도면을 확인해야 합니다.</Text>
          </Paper>
          <Button color="jippin" fullWidth>
            이 후보로 계속
          </Button>
          <Button color="gray" fullWidth onClick={close} variant="subtle">
            닫기
          </Button>
        </Stack>
      </Drawer>
    </Paper>
  );
}

function MobileFullScreenDialogDemo({ openedByDefault = true }: OverlayDemoProps) {
  const [opened, { open, close }] = useDisclosure(openedByDefault);

  return (
    <Paper p="lg" radius="md" shadow="sm" withBorder w="min(390px, 100vw - 32px)">
      <Stack>
        <Title order={3}>리포트 다운로드 확인</Title>
        <Text c="dimmed" size="sm">
          모바일에서 중요한 확인은 full screen Modal로 읽기 공간을 확보합니다.
        </Text>
        <Button color="blueprint" leftSection={<IconFileReport size={16} aria-hidden />} onClick={open} fullWidth>
          다운로드 Modal 열기
        </Button>
      </Stack>
      <Modal
        closeButtonProps={{ 'aria-label': '닫기' }}
        fullScreen
        opened={opened}
        onClose={close}
        radius={0}
        title="리포트 다운로드"
        transitionProps={{ transition: 'fade', duration: 160 }}
      >
        <Stack h="100%" justify="space-between">
          <Stack>
            <Title order={2}>다운로드 전에 확인해 주세요.</Title>
            <Text>
              리포트는 AI 기반 사전검토 결과이며 최종 행위허가 판단을 대신하지 않습니다.
            </Text>
            <LegalNotice variant="inline" />
          </Stack>
          <Group grow>
            <Button color="gray" leftSection={<IconX size={16} aria-hidden />} onClick={close} variant="subtle">
              취소
            </Button>
            <Button color="blueprint" leftSection={<IconFileReport size={16} aria-hidden />}>
              다운로드
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Paper>
  );
}

export const UsageGuide: Story = {
  parameters: {
    docs: {
      description: {
        story: '모바일 overlay 선택 기준과 필수 props를 문서화한 가이드입니다. 구현 전 이 표를 먼저 확인합니다.'
      }
    }
  },
  render: () => (
    <Stack maw={880}>
      <Title order={2}>Mobile overlay guide</Title>
      <Text c="dimmed">
        집핀 모바일 화면에서는 사용자의 현재 흐름을 크게 끊지 않는 하단 Drawer를 기본으로 사용합니다.
        사용자가 반드시 읽고 결정해야 하는 짧은 확인에는 full-screen Modal을 사용합니다.
      </Text>
      <Table striped withTableBorder withColumnBorders>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Use case</Table.Th>
            <Table.Th>Component</Table.Th>
            <Table.Th>Required props</Table.Th>
            <Table.Th>Notes</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          <Table.Tr>
            <Table.Td>도면 후보 상세, 필터, 선택 보조</Table.Td>
            <Table.Td><Code>Drawer</Code></Table.Td>
            <Table.Td>
              <Code>{'position="bottom"'}</Code>, <Code>{'size="86dvh"'}</Code>, <Code>title</Code>, <Code>closeButtonProps</Code>
            </Table.Td>
            <Table.Td>긴 내용은 내부 스크롤. 하단 CTA는 한 개를 기본으로 둡니다.</Table.Td>
          </Table.Tr>
          <Table.Tr>
            <Table.Td>다운로드 확인, 중요한 확인, 짧은 의사결정</Table.Td>
            <Table.Td><Code>Modal</Code></Table.Td>
            <Table.Td><Code>fullScreen</Code>, <Code>title</Code>, <Code>closeButtonProps</Code></Table.Td>
            <Table.Td>법적 고지와 취소/확인 액션을 함께 둡니다.</Table.Td>
          </Table.Tr>
        </Table.Tbody>
      </Table>
      <Code block>{`<Drawer
  position="bottom"
  size="86dvh"
  title="도면 후보 상세"
  closeButtonProps={{ 'aria-label': '닫기' }}
  transitionProps={{ transition: 'slide-up', duration: 180 }}
/>`}</Code>
      <Code block>{`<Modal
  fullScreen
  title="리포트 다운로드"
  closeButtonProps={{ 'aria-label': '닫기' }}
  transitionProps={{ transition: 'fade', duration: 160 }}
/>`}</Code>
    </Stack>
  )
};

export const BottomSheet: Story = {
  name: 'Bottom Sheet',
  parameters: {
    docs: {
      description: {
        story: '모바일 도면 후보 상세·필터·선택 보조에 쓰는 기본 패턴입니다. story는 시각 확인을 위해 열린 상태로 시작합니다.'
      },
      source: {
        code: `<Drawer
  opened={opened}
  onClose={close}
  position="bottom"
  size="86dvh"
  radius="lg"
  title="도면 후보 상세"
  closeButtonProps={{ 'aria-label': '닫기' }}
  transitionProps={{ transition: 'slide-up', duration: 180 }}
>
  {/* content */}
</Drawer>`
      }
    },
    viewport: {
      defaultViewport: 'mobile1'
    }
  },
  render: () => <MobileBottomSheetDemo openedByDefault />
};

export const FullScreenDialog: Story = {
  name: 'Full Screen Dialog',
  parameters: {
    docs: {
      description: {
        story: '모바일에서 리포트 다운로드처럼 사용자가 명시적으로 확인해야 하는 짧은 흐름에 사용합니다. story는 시각 확인을 위해 열린 상태로 시작합니다.'
      },
      source: {
        code: `<Modal
  fullScreen
  opened={opened}
  onClose={close}
  title="리포트 다운로드"
  closeButtonProps={{ 'aria-label': '닫기' }}
  transitionProps={{ transition: 'fade', duration: 160 }}
>
  {/* confirmation content */}
</Modal>`
      }
    },
    viewport: {
      defaultViewport: 'mobile1'
    }
  },
  render: () => <MobileFullScreenDialogDemo openedByDefault />
};

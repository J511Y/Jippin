import { Button, Drawer, Group, Modal, Stack, Text } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconArrowRight, IconFileReport } from '@tabler/icons-react';
import type { Meta, StoryObj } from '@storybook/nextjs-vite';

const meta = {
  title: 'UI/Overlay',
  parameters: {
    docs: {
      description: {
        component:
          'Overlay 데모의 트리거 색은 *진입할 영역의 의미*를 따른다. Drawer 는 일반 인터랙션(jippin), Modal 은 "리포트 다운로드" 같은 전문 영역(blueprint) 에서 사용한다. 동일한 의미 영역에서는 같은 색으로 통일한다.'
      }
    },
    layout: 'centered'
  },
  tags: ['autodocs']
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

function DrawerDemo() {
  const [opened, { open, close }] = useDisclosure(false);

  return (
    <>
      <Drawer
        closeButtonProps={{ 'aria-label': '닫기' }}
        opened={opened}
        onClose={close}
        position="right"
        title="도면 후보 상세"
        transitionProps={{ transition: 'slide-left', duration: 180 }}
      >
        <Stack>
          <Text size="sm">
            평면도에서 비내력벽 후보를 표시했습니다. 색칠된 부분을 눌러 자세히 보세요.
          </Text>
          <Button color="jippin" rightSection={<IconArrowRight size={16} aria-hidden />}>
            후보 영역 확인
          </Button>
        </Stack>
      </Drawer>
      <Button color="jippin" onClick={open}>
        Drawer 열기
      </Button>
    </>
  );
}

function ModalDemo() {
  const [opened, { open, close }] = useDisclosure(false);

  return (
    <>
      <Modal
        closeButtonProps={{ 'aria-label': '닫기' }}
        opened={opened}
        onClose={close}
        title="리포트 다운로드"
        transitionProps={{ transition: 'fade', duration: 160 }}
      >
        <Stack>
          <Text size="sm">
            다운로드 산출물에도 법적 고지 문구가 포함됩니다.
          </Text>
          <Group justify="flex-end">
            <Button color="gray" onClick={close} variant="subtle">
              취소
            </Button>
            <Button color="blueprint" leftSection={<IconFileReport size={16} aria-hidden />}>
              다운로드
            </Button>
          </Group>
        </Stack>
      </Modal>
      <Button color="blueprint" onClick={open}>
        Modal 열기
      </Button>
    </>
  );
}

export const DrawerExample: Story = {
  render: () => <DrawerDemo />
};

export const ModalExample: Story = {
  render: () => <ModalDemo />
};

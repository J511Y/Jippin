import { Button, Group, Notification, Stack } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconAlertTriangle, IconCircleCheck, IconInfoCircle } from '@tabler/icons-react';
import type { Meta, StoryObj } from '@storybook/nextjs-vite';

const meta = {
  title: 'UI/Feedback',
  component: Notification,
  parameters: {
    layout: 'centered'
  },
  tags: ['autodocs']
} satisfies Meta<typeof Notification>;

export default meta;
type Story = StoryObj<typeof meta>;

export const NotificationStates: Story = {
  render: () => (
    <Stack w={420}>
      <Notification color="success" icon={<IconCircleCheck size={18} aria-hidden />} title="업로드 완료">
        도면 파일을 받았습니다. 사전검토를 시작합니다.
      </Notification>
      <Notification color="warning" icon={<IconAlertTriangle size={18} aria-hidden />} title="추가 확인 필요">
        도면 일부가 흐려 판단이 어렵습니다.
      </Notification>
      <Notification color="info" icon={<IconInfoCircle size={18} aria-hidden />} title="참고 안내">
        결과는 행정기관의 최종 판단을 대신하지 않습니다.
      </Notification>
    </Stack>
  )
};

export const ToastActions: Story = {
  render: () => (
    <Group>
      <Button
        color="success"
        onClick={() =>
          notifications.show({
            color: 'success',
            icon: <IconCircleCheck size={18} aria-hidden />,
            message: '도면 파일을 받았습니다.',
            title: '업로드 완료'
          })
        }
      >
        성공 Toast
      </Button>
      <Button
        color="warning"
        onClick={() =>
          notifications.show({
            color: 'warning',
            icon: <IconAlertTriangle size={18} aria-hidden />,
            message: '평면도 한 장을 더 올려 주세요.',
            title: '추가 확인 필요'
          })
        }
      >
        보류 Toast
      </Button>
    </Group>
  )
};

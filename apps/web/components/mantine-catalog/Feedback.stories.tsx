import { Alert, Button, Group, Loader, Notification, Progress, Skeleton, Stack, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconAlertTriangle, IconCircleCheck, IconInfoCircle } from '@tabler/icons-react';
import type { Meta, StoryObj } from '@storybook/nextjs-vite';

const meta = {
  title: 'Mantine Catalog/Feedback',
  parameters: {
    docs: {
      description: {
        component:
          '피드백 컴포넌트는 결과 상태를 색과 라벨로 함께 전달합니다. 중요한 판정은 Alert/Card에 남기고 Toast는 보조 피드백으로만 사용합니다.'
      }
    },
    layout: 'centered'
  },
  tags: ['autodocs']
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const AlertsAndNotifications: Story = {
  render: () => (
    <Stack w="min(480px, 100vw - 32px)">
      <Alert color="success" icon={<IconCircleCheck size={18} aria-hidden />} title="업로드 완료" variant="light">
        도면 파일을 받았습니다. 사전검토를 시작합니다.
      </Alert>
      <Alert color="warning" icon={<IconAlertTriangle size={18} aria-hidden />} title="추가 확인 필요" variant="light">
        도면 일부가 흐려 판단이 어렵습니다.
      </Alert>
      <Notification color="info" icon={<IconInfoCircle size={18} aria-hidden />} title="참고 안내">
        결과는 행정기관의 최종 판단을 대신하지 않습니다.
      </Notification>
    </Stack>
  )
};

export const ToastButtons: Story = {
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

export const LoadingStates: Story = {
  render: () => (
    <Stack w={420}>
      <Group>
        <Loader color="jippin" size="sm" />
        <Text size="sm">도면을 분석하고 있습니다.</Text>
      </Group>
      <Progress color="jippin" value={62} />
      <Skeleton height={16} radius="sm" />
      <Skeleton height={16} radius="sm" width="76%" />
    </Stack>
  )
};

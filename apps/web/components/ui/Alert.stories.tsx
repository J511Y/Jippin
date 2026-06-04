import { Alert, Button, Stack } from '@mantine/core';
import {
  IconAlertCircle,
  IconAlertTriangle,
  IconCircleCheck,
  IconInfoCircle
} from '@tabler/icons-react';
import type { Meta, StoryObj } from '@storybook/nextjs-vite';

const meta = {
  title: 'UI/Alert',
  component: Alert,
  parameters: {
    layout: 'centered'
  },
  tags: ['autodocs'],
  args: {
    children: '도면 일부가 흐려 비내력벽 여부 판단이 어렵습니다. 평면도 한 장을 더 올려 주세요.',
    color: 'warning',
    icon: <IconAlertTriangle size={18} aria-hidden />,
    title: '지금 정보만으로는 판단이 어렵습니다.',
    variant: 'light'
  }
} satisfies Meta<typeof Alert>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Playground: Story = {};

export const ResultAlerts: Story = {
  render: () => (
    <Stack w={560}>
      <Alert color="success" icon={<IconCircleCheck size={18} aria-hidden />} title="가능성이 있습니다." variant="light">
        제출하신 도면에서 비내력벽 후보가 확인됩니다.
      </Alert>
      <Alert color="danger" icon={<IconAlertCircle size={18} aria-hidden />} title="제출하신 정보로는 어렵습니다." variant="light">
        관할 행정기관 또는 전문가 확인 없이 진행하기 어렵습니다.
      </Alert>
      <Alert color="warning" icon={<IconAlertTriangle size={18} aria-hidden />} title="추가 확인이 필요합니다." variant="light">
        도면 일부가 흐려 판단이 어렵습니다. 평면도 한 장을 더 올려 주세요.
      </Alert>
      <Alert color="info" icon={<IconInfoCircle size={18} aria-hidden />} title="참고 안내" variant="light">
        사전검토 결과는 행정기관의 최종 판단을 대신하지 않습니다.
      </Alert>
    </Stack>
  )
};

export const WithAction: Story = {
  render: () => (
    <Alert
      color="danger"
      icon={<IconAlertCircle size={18} aria-hidden />}
      title="도면 업로드가 중단됐습니다."
      variant="light"
      w={560}
    >
      <Stack gap="sm">
        파일을 다시 선택해 주세요. 이용자 잘못이 아닙니다.
        <Button color="danger" variant="light">도면 다시 선택</Button>
      </Stack>
    </Alert>
  )
};

import { ActionIcon, Button, Group, Menu, Stack, Text, Tooltip } from '@mantine/core';
import { IconDotsVertical, IconDownload, IconFileReport, IconSend, IconUpload } from '@tabler/icons-react';
import type { Meta, StoryObj } from '@storybook/nextjs-vite';

const meta = {
  title: 'Mantine Catalog/Actions',
  parameters: {
    docs: {
      description: {
        component:
          '액션 컴포넌트는 Button을 기본으로 사용합니다. 상담/견적 전환은 coral, 리포트·전문 영역은 blueprint, 일반 주 액션은 jippin 색을 사용합니다.'
      }
    },
    layout: 'centered'
  },
  tags: ['autodocs']
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const Buttons: Story = {
  render: () => (
    <Stack align="flex-start">
      <Group>
        <Button color="jippin" leftSection={<IconUpload size={16} aria-hidden />}>
          도면 업로드
        </Button>
        <Button color="jippin" variant="light">
          보조 행동
        </Button>
        <Button color="coral" c="var(--jippin-brand-cta-fg)">
          상담 신청
        </Button>
      </Group>
      <Group>
        <Button color="blueprint" leftSection={<IconFileReport size={16} aria-hidden />}>
          리포트 보기
        </Button>
        <Button color="gray" variant="subtle">
          나중에 하기
        </Button>
        <Button color="jippin" loading>
          분석 중
        </Button>
      </Group>
    </Stack>
  )
};

export const IconActionsAndMenu: Story = {
  render: () => (
    <Group>
      <Tooltip label="리포트 다운로드">
        <ActionIcon aria-label="리포트 다운로드" color="blueprint" size="lg" variant="light">
          <IconDownload size={18} aria-hidden />
        </ActionIcon>
      </Tooltip>
      <Tooltip label="메시지 전송">
        <ActionIcon aria-label="메시지 전송" color="jippin" size="lg">
          <IconSend size={18} aria-hidden />
        </ActionIcon>
      </Tooltip>
      <Menu shadow="md" width={220}>
        <Menu.Target>
          <ActionIcon aria-label="추가 작업" color="gray" size="lg" variant="subtle">
            <IconDotsVertical size={18} aria-hidden />
          </ActionIcon>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Label>리포트</Menu.Label>
          <Menu.Item leftSection={<IconFileReport size={16} aria-hidden />}>상세 보기</Menu.Item>
          <Menu.Item leftSection={<IconDownload size={16} aria-hidden />}>다운로드</Menu.Item>
        </Menu.Dropdown>
      </Menu>
      <Text c="dimmed" size="sm">
        아이콘 단독 버튼은 항상 `aria-label`을 둡니다.
      </Text>
    </Group>
  )
};

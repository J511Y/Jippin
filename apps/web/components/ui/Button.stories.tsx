import { Button, Group, Stack } from '@mantine/core';
import { IconChevronRight, IconDownload, IconFileReport } from '@tabler/icons-react';
import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { expect, fn, userEvent, within } from 'storybook/test';

const handleClick = fn();

const meta = {
  title: 'UI/Button',
  component: Button,
  parameters: {
    layout: 'centered'
  },
  tags: ['autodocs'],
  args: {
    children: '사전검토 시작',
    color: 'jippin',
    onClick: handleClick,
    radius: 'md',
    size: 'md'
  }
} satisfies Meta<typeof Button>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Playground: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole('button', { name: '사전검토 시작' }));
    await expect(handleClick).toHaveBeenCalledTimes(1);
  }
};

export const Variants: Story = {
  render: () => (
    <Group>
      <Button color="jippin">기본 행동</Button>
      <Button color="jippin" variant="light">보조 행동</Button>
      <Button color="coral" c="var(--jippin-brand-cta-fg)">상담 신청</Button>
      <Button color="blueprint" leftSection={<IconFileReport size={16} aria-hidden />}>
        리포트 보기
      </Button>
      {/*
        텍스트 전용 tertiary 버튼은 색만으로는 클릭 가능 여부가 모호하다.
        디지털 친숙도가 낮은 사용자를 위해 underline 으로 affordance 를 노출한다.
      */}
      <Button color="gray" td="underline" variant="subtle">
        나중에 하기
      </Button>
    </Group>
  )
};

export const Sizes: Story = {
  render: () => (
    <Stack align="flex-start">
      <Button color="jippin" size="xs">작은 버튼</Button>
      <Button color="jippin" size="sm">보통보다 작은 버튼</Button>
      <Button color="jippin" size="md">기본 버튼</Button>
      <Button color="jippin" rightSection={<IconChevronRight size={16} aria-hidden />} size="lg">
        다음 단계로
      </Button>
    </Stack>
  )
};

export const LoadingAndDisabled: Story = {
  render: () => (
    <Group>
      <Button color="jippin" loading>분석 중</Button>
      <Button color="blueprint" disabled leftSection={<IconDownload size={16} aria-hidden />}>
        다운로드
      </Button>
    </Group>
  )
};

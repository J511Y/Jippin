import type { Meta, StoryObj } from '@storybook/nextjs-vite';
import { Box, Card } from '@mantine/core';
import { LegalNotice } from '@/components/LegalNotice';

const meta = {
  title: 'UI/LegalNotice',
  component: LegalNotice,
  parameters: {
    layout: 'centered'
  },
  tags: ['autodocs'],
  args: {
    variant: 'inline'
  }
} satisfies Meta<typeof LegalNotice>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Inline: Story = {
  render: (args) => (
    <Box w={560}>
      <LegalNotice {...args} />
    </Box>
  )
};

export const Footer: Story = {
  args: {
    variant: 'footer'
  },
  render: (args) => (
    <Card p={0} radius="md" withBorder w={720}>
      <LegalNotice {...args} />
    </Card>
  )
};

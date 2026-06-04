import { Button, Checkbox, Group, Paper, Select, Stack, Textarea, TextInput, Title } from '@mantine/core';
import { useForm } from '@mantine/form';
import type { Meta, StoryObj } from '@storybook/nextjs-vite';

const meta = {
  title: 'UI/Form',
  parameters: {
    layout: 'centered'
  },
  tags: ['autodocs']
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

function MantineFormDemo() {
  const form = useForm({
    initialValues: {
      address: '',
      agreed: false,
      location: '',
      note: ''
    },
    validate: {
      address: (value) => (value.trim().length < 8 ? '주소를 다시 확인해 주세요.' : null),
      agreed: (value) => (value ? null : '고지 확인이 필요합니다.'),
      location: (value) => (value ? null : '철거 위치를 선택해 주세요.')
    }
  });

  return (
    <Paper component="form" onSubmit={form.onSubmit(() => undefined)} p="lg" radius="md" shadow="sm" withBorder w={460}>
      <Stack>
        <Title order={3}>사전검토 요청</Title>
        <TextInput
          label="아파트 주소"
          placeholder="예: 서울시 송파구 ..."
          required
          {...form.getInputProps('address')}
        />
        <Select
          data={['거실-발코니', '방-발코니', '주방-다용도실', '기타']}
          label="철거 위치"
          placeholder="위치를 선택해 주세요"
          required
          {...form.getInputProps('location')}
        />
        <Textarea
          autosize
          label="추가 설명"
          minRows={3}
          placeholder="도면이나 철거 위치를 설명해 주세요."
          {...form.getInputProps('note')}
        />
        <Checkbox
          label="사전검토 결과가 최종 행위허가 판단을 대신하지 않는다는 점을 확인했습니다."
          {...form.getInputProps('agreed', { type: 'checkbox' })}
        />
        <Group justify="flex-end">
          <Button color="jippin" type="submit">검토 요청</Button>
        </Group>
      </Stack>
    </Paper>
  );
}

export const MantineForm: Story = {
  render: () => <MantineFormDemo />
};

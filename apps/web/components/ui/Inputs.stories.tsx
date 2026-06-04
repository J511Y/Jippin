import { Button, Checkbox, NumberInput, Select, Stack, Textarea, TextInput } from '@mantine/core';
import type { Meta, StoryObj } from '@storybook/nextjs-vite';

const meta = {
  title: 'UI/Inputs',
  component: TextInput,
  parameters: {
    layout: 'centered'
  },
  tags: ['autodocs'],
  args: {
    description: '동·호수는 도면 후보를 좁히는 데 사용합니다.',
    label: '아파트 주소',
    placeholder: '예: 서울시 송파구 ...',
    required: true
  }
} satisfies Meta<typeof TextInput>;

export default meta;
type Story = StoryObj<typeof meta>;

export const TextField: Story = {};

export const WithError: Story = {
  args: {
    defaultValue: '서울',
    error: '주소를 다시 확인해 주세요.'
  }
};

export const FormControls: Story = {
  render: () => (
    <Stack w={420}>
      <TextInput label="아파트 주소" placeholder="예: 서울시 송파구 ..." required />
      <Select
        data={['거실-발코니', '방-발코니', '주방-다용도실', '기타']}
        label="철거 위치"
        placeholder="위치를 선택해 주세요"
      />
      <NumberInput label="예상 공사 면적" min={0} suffix=" m²" />
      <Textarea autosize label="추가 설명" minRows={3} placeholder="도면이나 철거 위치를 설명해 주세요." />
      <Checkbox label="사전검토 결과가 최종 행위허가 판단을 대신하지 않는다는 점을 확인했습니다." />
      <Button color="jippin">검토 요청</Button>
    </Stack>
  )
};

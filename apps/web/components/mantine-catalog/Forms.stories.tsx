import {
  Button,
  Checkbox,
  NumberInput,
  Paper,
  SegmentedControl,
  Select,
  Slider,
  Stack,
  Switch,
  Text,
  Textarea,
  TextInput,
  Title
} from '@mantine/core';
import { DateInput } from '@mantine/dates';
import { useForm } from '@mantine/form';
import type { Meta, StoryObj } from '@storybook/nextjs-vite';

const meta = {
  title: 'Mantine Catalog/Forms',
  parameters: {
    docs: {
      description: {
        component:
          '입력 화면은 모바일 1열을 기본으로 구성합니다. Mantine Form은 간단한 로컬 검증에 적합하고, 서버 계약이나 복잡한 스키마는 Zod/RHF와 연결할 수 있습니다.'
      }
    },
    layout: 'centered'
  },
  tags: ['autodocs']
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

function PrecheckFormDemo() {
  const form = useForm({
    initialValues: {
      address: '',
      agreed: false,
      area: 0,
      location: '',
      mode: 'quick',
      note: ''
    },
    validate: {
      address: (value) => (value.trim().length < 8 ? '주소를 다시 확인해 주세요.' : null),
      agreed: (value) => (value ? null : '고지 확인이 필요합니다.'),
      location: (value) => (value ? null : '철거 위치를 선택해 주세요.')
    }
  });

  return (
    <Paper component="form" onSubmit={form.onSubmit(() => undefined)} p="lg" radius="md" shadow="sm" withBorder w="min(420px, 100vw - 32px)">
      <Stack>
        <Title order={3}>모바일 사전검토 입력</Title>
        <Text c="dimmed" size="sm">
          모바일에서는 한 줄에 하나의 입력만 배치합니다.
        </Text>
        <SegmentedControl
          data={[
            { label: '빠른 검토', value: 'quick' },
            { label: '상세 검토', value: 'detail' }
          ]}
          fullWidth
          {...form.getInputProps('mode')}
        />
        <TextInput label="아파트 주소" placeholder="예: 서울시 송파구 ..." required {...form.getInputProps('address')} />
        <Select
          data={['거실-발코니', '방-발코니', '주방-다용도실', '기타']}
          label="철거 위치"
          placeholder="위치를 선택해 주세요"
          required
          {...form.getInputProps('location')}
        />
        <NumberInput label="예상 공사 면적" min={0} suffix=" m²" {...form.getInputProps('area')} />
        <DateInput clearable label="상담 희망일" placeholder="날짜 선택" valueFormat="YYYY-MM-DD" />
        <Textarea autosize label="추가 설명" minRows={3} placeholder="도면이나 철거 위치를 설명해 주세요." {...form.getInputProps('note')} />
        <Switch label="검토 결과를 문자로도 받고 싶습니다." />
        <Slider aria-label="도면 확대 비율" color="jippin" defaultValue={50} label={(value) => `${value}%`} />
        <Checkbox
          label="사전검토 결과가 최종 행위허가 판단을 대신하지 않는다는 점을 확인했습니다."
          {...form.getInputProps('agreed', { type: 'checkbox' })}
        />
        <Button color="jippin" fullWidth type="submit">
          검토 요청
        </Button>
      </Stack>
    </Paper>
  );
}

export const MobilePrecheckForm: Story = {
  parameters: {
    viewport: {
      defaultViewport: 'mobile1'
    }
  },
  render: () => <PrecheckFormDemo />
};

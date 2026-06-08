'use client';

import {
  Alert,
  Button,
  Card,
  FileInput,
  Group,
  Select,
  Stack,
  Text,
  Textarea,
  TextInput,
  UnstyledButton
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { IconPaperclip, IconSearch } from '@tabler/icons-react';
import { useState } from 'react';
import { parseApiError } from '@/lib/api/error';
import {
  createLead,
  searchAddress,
  type AddressItem,
  type ApplicantKind,
  type InflowSource,
  type OwnershipStatus
} from '@/lib/leads/api';
import { ensureAnonymousSession } from '@/lib/leads/ensure-anonymous-session';
import { deleteFloorplan, uploadFloorplan, type UploadedAttachment } from '@/lib/leads/upload';
import { normalizeKoreanPhone, validateKoreanPhone, validateRequiredText } from '@/lib/leads/validation';

interface FullLeadValues {
  applicant_kind: ApplicantKind;
  applicant_name: string;
  applicant_phone: string;
  road_addr_part1: string;
  road_addr_part2: string;
  road_addr_detail: string;
  expansion_location: string;
  ownership_status: OwnershipStatus | '';
  construction_start_date: string;
  construction_end_date: string;
  inflow_source: InflowSource | '';
  message: string;
}

const INFLOW_OPTIONS = [
  { value: 'naver_search', label: '네이버 검색' },
  { value: 'blog', label: '블로그' },
  { value: 'acquaintance', label: '지인 소개' },
  { value: 'cafe', label: '카페' },
  { value: 'etc', label: '기타' }
];

/**
 * 상담 신청 전체 폼 (CMP-DIRECT). 도로명주소 검색 + 평면도 첨부(Supabase Storage) 포함.
 * 비로그인(익명)도 제출 가능.
 */
export function ConsultationLeadForm() {
  const [submitting, setSubmitting] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [keyword, setKeyword] = useState('');
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<AddressItem[]>([]);
  const [searchError, setSearchError] = useState<string | null>(null);

  const form = useForm<FullLeadValues>({
    initialValues: {
      applicant_kind: 'individual',
      applicant_name: '',
      applicant_phone: '',
      road_addr_part1: '',
      road_addr_part2: '',
      road_addr_detail: '',
      expansion_location: '',
      ownership_status: '',
      construction_start_date: '',
      construction_end_date: '',
      inflow_source: '',
      message: ''
    },
    validate: {
      applicant_name: validateRequiredText('이름을 입력해 주세요.'),
      applicant_phone: validateKoreanPhone,
      road_addr_part1: validateRequiredText('주소를 검색해 선택해 주세요.'),
      road_addr_detail: validateRequiredText('상세 주소를 입력해 주세요.'),
      expansion_location: validateRequiredText('확장 위치를 입력해 주세요.'),
      ownership_status: (value) => (value ? null : '상태 구분을 선택해 주세요.'),
      construction_end_date: (value, values) =>
        value && values.construction_start_date && value < values.construction_start_date
          ? '종료일은 시작일보다 빠를 수 없습니다.'
          : null
    }
  });

  async function handleSearch() {
    const trimmed = keyword.trim();
    if (!trimmed) {
      setSearchError('검색어를 입력해 주세요.');
      return;
    }
    setSearching(true);
    setSearchError(null);
    try {
      const result = await searchAddress(trimmed);
      setResults(result.items);
      if (result.items.length === 0) {
        setSearchError('검색 결과가 없습니다. 도로명/건물명으로 다시 검색해 보세요.');
      }
    } catch (error) {
      setSearchError(parseApiError(error).message);
      setResults([]);
    } finally {
      setSearching(false);
    }
  }

  function selectAddress(item: AddressItem) {
    form.setFieldValue('road_addr_part1', item.road_addr_part1);
    form.setFieldValue('road_addr_part2', item.road_addr_part2);
    setResults([]);
    setKeyword(item.road_addr_part1);
  }

  const handleSubmit = form.onSubmit(async (values) => {
    setSubmitting(true);
    let uploaded: UploadedAttachment | null = null;
    try {
      // 세션 보장: 업로드 라우트가 쿠키로 uid 를 읽고, apiClient 가 Bearer 를 부착한다.
      await ensureAnonymousSession();
      if (file) {
        uploaded = await uploadFloorplan(file);
      }
      const attachments = uploaded ? [uploaded] : [];
      await createLead({
        source_form: 'lead_page',
        applicant_kind: values.applicant_kind,
        applicant_name: values.applicant_name.trim(),
        applicant_phone: normalizeKoreanPhone(values.applicant_phone) ?? values.applicant_phone,
        road_addr_part1: values.road_addr_part1.trim(),
        road_addr_part2: values.road_addr_part2.trim() || null,
        road_addr_detail: values.road_addr_detail.trim(),
        expansion_location: values.expansion_location.trim(),
        ownership_status: values.ownership_status || null,
        construction_start_date: values.construction_start_date || null,
        construction_end_date: values.construction_end_date || null,
        inflow_source: values.inflow_source || null,
        message: values.message.trim() || null,
        attachments
      });
      notifications.show({
        color: 'teal',
        title: '상담 신청이 접수되었어요',
        message: '담당자가 영업일 기준 1일 이내에 연락드릴게요.'
      });
      form.reset();
      setFile(null);
      setKeyword('');
    } catch (error) {
      // 업로드는 성공했는데 리드 생성이 실패하면 orphan 평면도(연결 row 없는 PII)가
      // 남는다 — best-effort 로 정리한다(클라이언트엔 삭제 권한이 없어 서버 경로 사용).
      if (uploaded) {
        await deleteFloorplan(uploaded.object_path);
      }
      notifications.show({
        color: 'red',
        title: '상담 신청에 실패했어요',
        message: parseApiError(error).message
      });
    } finally {
      setSubmitting(false);
    }
  });

  return (
    <Card withBorder radius="md" padding="md" component="form" onSubmit={handleSubmit}>
      <Stack gap="md">
        <Group grow>
          <Select
            label="신청 구분"
            withAsterisk
            allowDeselect={false}
            data={[
              { value: 'individual', label: '개인' },
              { value: 'company', label: '업체' }
            ]}
            {...form.getInputProps('applicant_kind')}
          />
          <TextInput label="신청인 이름" withAsterisk placeholder="예: 홍길동" {...form.getInputProps('applicant_name')} />
        </Group>

        <TextInput
          label="신청인 연락처"
          withAsterisk
          placeholder="010-0000-0000"
          inputMode="tel"
          {...form.getInputProps('applicant_phone')}
        />

        <Stack gap="xs">
          <Text size="sm" fw={500}>
            현장 주소 <Text component="span" c="red">*</Text>
          </Text>
          <Group gap="xs" align="flex-end" wrap="nowrap">
            <TextInput
              style={{ flex: 1 }}
              placeholder="도로명 또는 건물명으로 검색"
              value={keyword}
              onChange={(event) => setKeyword(event.currentTarget.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  void handleSearch();
                }
              }}
            />
            <Button
              type="button"
              variant="light"
              color="jippin"
              leftSection={<IconSearch size={16} aria-hidden />}
              loading={searching}
              onClick={() => void handleSearch()}
            >
              주소 검색
            </Button>
          </Group>
          {searchError ? (
            <Text size="xs" c="red">
              {searchError}
            </Text>
          ) : null}
          {results.length > 0 ? (
            <Card withBorder radius="sm" padding="xs">
              <Stack gap={4}>
                {results.map((item) => (
                  <UnstyledButton
                    key={`${item.road_addr}-${item.zip_no ?? ''}`}
                    onClick={() => selectAddress(item)}
                    style={{ padding: '6px 8px', borderRadius: 6 }}
                  >
                    <Text size="sm">{item.road_addr}</Text>
                    {item.jibun_addr ? (
                      <Text size="xs" c="dimmed">
                        {item.jibun_addr}
                      </Text>
                    ) : null}
                  </UnstyledButton>
                ))}
              </Stack>
            </Card>
          ) : null}
          {form.values.road_addr_part1 ? (
            <Text size="xs" c="dimmed">
              선택된 주소: {form.values.road_addr_part1} {form.values.road_addr_part2}
            </Text>
          ) : null}
          {form.errors.road_addr_part1 ? (
            <Text size="xs" c="red">
              {form.errors.road_addr_part1}
            </Text>
          ) : null}
          <TextInput
            placeholder="상세 주소 (예: 101동 1001호)"
            {...form.getInputProps('road_addr_detail')}
          />
        </Stack>

        <TextInput
          label="확장 위치"
          withAsterisk
          placeholder="예: 거실 / 입구방"
          {...form.getInputProps('expansion_location')}
        />

        <Select
          label="상태 구분"
          withAsterisk
          placeholder="선택"
          data={[
            { value: 'in_transaction', label: '매매거래 중' },
            { value: 'owner', label: '소유주' }
          ]}
          {...form.getInputProps('ownership_status')}
        />

        <Group grow>
          <TextInput
            label="공사 시작일"
            type="date"
            {...form.getInputProps('construction_start_date')}
          />
          <TextInput
            label="공사 종료일"
            type="date"
            {...form.getInputProps('construction_end_date')}
          />
        </Group>

        <Select
          label="유입경로"
          placeholder="선택 (선택사항)"
          clearable
          data={INFLOW_OPTIONS}
          {...form.getInputProps('inflow_source')}
        />

        <Textarea
          label="상담 내용"
          placeholder="현장 상황이나 궁금한 점을 적어주세요. (선택)"
          autosize
          minRows={3}
          {...form.getInputProps('message')}
        />

        <FileInput
          label="단위세대 평면도 첨부"
          description="관리사무소 방문 후 해당 도면을 촬영해 첨부해 주세요. (선택)"
          placeholder="이미지 파일 선택"
          accept="image/*"
          clearable
          leftSection={<IconPaperclip size={16} aria-hidden />}
          value={file}
          onChange={setFile}
        />

        <Alert color="jippin" variant="light" radius="md">
          입력하신 정보는 상담 진행을 위해서만 사용돼요.
        </Alert>

        <Button type="submit" size="md" color="coral" radius="md" fullWidth loading={submitting}>
          상담 신청하기
        </Button>
      </Stack>
    </Card>
  );
}

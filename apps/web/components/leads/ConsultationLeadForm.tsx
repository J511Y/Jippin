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
  TextInput
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { IconPaperclip, IconSearch } from '@tabler/icons-react';
import { useEffect, useState } from 'react';
import { PhoneInput } from '@/components/inputs/PhoneInput';
import { parseApiError } from '@/lib/api/error';
import {
  createLead,
  type ApplicantKind,
  type InflowSource,
  type OwnershipStatus
} from '@/lib/leads/api';
import { ensureAnonymousSession } from '@/lib/leads/ensure-anonymous-session';
import { openJusoAddressPopup } from '@/lib/leads/juso-popup';
import { createClient } from '@/lib/supabase/client';
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

const INITIAL_VALUES: FullLeadValues = {
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
};

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
  // 로그인 회원은 이름/연락처가 이미 계정에 있으므로 prefill 후 잠근다(개별 잠금).
  const [nameLocked, setNameLocked] = useState(false);
  const [phoneLocked, setPhoneLocked] = useState(false);

  const form = useForm<FullLeadValues>({
    initialValues: INITIAL_VALUES,
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

  // 로그인(비익명) 세션이 있으면 계정의 이름·연락처를 폼에 미리 채우고 잠근다.
  // 이름은 user_metadata.name, 연락처는 서버가 소유하는 app_metadata.phone(정규화 저장)에서
  // 읽는다 — 회원가입 시 인증한 휴대폰이 이 위치에 보존된다.
  useEffect(() => {
    const supabase = createClient();
    let active = true;
    void supabase.auth.getSession().then(({ data: { session } }) => {
      if (!active) return;
      const user = session?.user;
      if (!user || user.is_anonymous) return;
      const meta = (user.user_metadata ?? {}) as { name?: string; display_name?: string };
      const name = (meta.name ?? meta.display_name ?? '').trim();
      const phone = ((user.app_metadata ?? {}) as { phone?: string }).phone?.trim() ?? '';
      if (!name && !phone) return;
      // prefill 값을 현재값 + initialValues 양쪽에 반영한다. initialValues 에도 넣어야
      // 제출 후 form.reset() 이 잠긴 필드를 빈 값이 아닌 prefill 값으로 되돌린다.
      form.setInitialValues({
        ...INITIAL_VALUES,
        ...(name ? { applicant_name: name } : {}),
        ...(phone ? { applicant_phone: phone } : {})
      });
      if (name) {
        form.setFieldValue('applicant_name', name);
        setNameLocked(true);
      }
      if (phone) {
        form.setFieldValue('applicant_phone', phone);
        setPhoneLocked(true);
      }
    });
    return () => {
      active = false;
    };
    // form 은 useForm 으로부터 안정적이라 마운트 시 1회만 실행한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function openAddressPopup() {
    // 도로명주소 팝업(useDetailAddr=Y)이 기본주소 + 상세주소를 함께 돌려준다.
    const result = await openJusoAddressPopup();
    form.setFieldValue('road_addr_part1', result.roadAddrPart1);
    form.setFieldValue('road_addr_part2', result.roadAddrPart2);
    form.setFieldValue('road_addr_detail', result.addrDetail);
    form.clearFieldError('road_addr_part1');
    form.clearFieldError('road_addr_detail');
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
      // reset() 은 initialValues 로 되돌린다 — 로그인 회원은 prefill 효과에서
      // setInitialValues 로 이름/연락처를 심어둬 잠긴 필드가 그대로 유지된다.
      form.reset();
      setFile(null);
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
          <TextInput
            label="신청인 이름"
            withAsterisk
            placeholder="예: 홍길동"
            disabled={nameLocked}
            {...form.getInputProps('applicant_name')}
          />
        </Group>

        <PhoneInput
          label="신청인 연락처"
          withAsterisk
          disabled={phoneLocked}
          {...form.getInputProps('applicant_phone')}
        />

        <Stack gap="xs">
          <Group justify="space-between" align="center" wrap="nowrap">
            <Text size="sm" fw={600}>
              현장 주소 <Text component="span" c="red">*</Text>
            </Text>
            <Button
              type="button"
              variant="light"
              color="jippin"
              size="xs"
              leftSection={<IconSearch size={16} aria-hidden />}
              onClick={() => void openAddressPopup()}
            >
              주소 검색
            </Button>
          </Group>
          <TextInput
            placeholder="주소 검색을 눌러 도로명주소를 선택하세요"
            disabled
            readOnly
            value={[form.values.road_addr_part1, form.values.road_addr_part2]
              .filter(Boolean)
              .join(' ')}
            error={form.errors.road_addr_part1}
          />
          <TextInput
            placeholder="상세 주소 (주소 검색 시 입력)"
            disabled
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

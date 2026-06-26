'use client';

/**
 * 사전검토 세션 전용 **빠른 상담폼** (CMP-DIRECT).
 *
 * 전체 상담폼(ConsultationLeadForm)은 주소 검색·확장위치·일정 등 입력이 많아 사전검토
 * 대화 흐름에 부담스럽다. 사전검토에선 주소 등 현장 정보를 이미 세션이 알고 있으므로,
 * 이 폼은 **이름/연락처(로그인 시 자동 채움)+선택 메모만** 받아 바로 제출한다.
 * source_form='precheck_session' 으로 저장돼 lead_page(전체폼) 인입과 명확히 구분된다.
 *
 * 판정 결과 카드(JudgmentSummary) 하단 CTA, 그리고 리포트 생성 실패 시 상담 전환 카드
 * (ConsultationHandoff)에서 인라인으로 재사용한다.
 */

import { Alert, Button, Card, Stack, Text, TextInput, Textarea } from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { IconMapPin } from '@tabler/icons-react';
import { useEffect, useState } from 'react';

import { PhoneInput } from '@/components/inputs/PhoneInput';
import { trackLeadSubmit, type LeadCtaId } from '@/lib/analytics/lead-cta';
import { parseApiError } from '@/lib/api/error';
import { createLead } from '@/lib/leads/api';
import { ensureAnonymousSession } from '@/lib/leads/ensure-anonymous-session';
import { createClient } from '@/lib/supabase/client';
import { normalizeKoreanPhone, validateKoreanPhone, validateRequiredText } from '@/lib/leads/validation';

export interface QuickPrecheckConsultFormProps {
  /** 세션에서 확정된 현장 주소(도로명) — 그대로 제출하고 읽기전용으로 보여 준다. */
  prefillAddress?: string;
  /** 인입 식별자 — 제출 추적 cta. */
  ctaId?: LeadCtaId;
  /** 제출 성공 콜백 — 카드가 완료 상태로 전환. */
  onSubmitted?: () => void;
}

interface QuickValues {
  applicant_name: string;
  applicant_phone: string;
  message: string;
}

export function QuickPrecheckConsultForm({
  prefillAddress,
  ctaId,
  onSubmitted
}: QuickPrecheckConsultFormProps) {
  const [submitting, setSubmitting] = useState(false);
  const [nameLocked, setNameLocked] = useState(false);
  const [phoneLocked, setPhoneLocked] = useState(false);

  const form = useForm<QuickValues>({
    initialValues: { applicant_name: '', applicant_phone: '', message: '' },
    validate: {
      applicant_name: validateRequiredText('이름을 입력해 주세요.'),
      applicant_phone: validateKoreanPhone
    }
  });

  // 로그인(비익명) 회원이면 계정의 이름·연락처를 채우고 잠근다 → 사실상 한 번에 제출 가능.
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
    // 마운트 시 1회 — form 은 안정적.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSubmit = form.onSubmit(async (values) => {
    setSubmitting(true);
    try {
      await ensureAnonymousSession();
      await createLead({
        source_form: 'precheck_session',
        applicant_kind: 'individual',
        applicant_name: values.applicant_name.trim(),
        applicant_phone:
          normalizeKoreanPhone(values.applicant_phone) ?? values.applicant_phone,
        road_addr_part1: prefillAddress?.trim() || null,
        message: values.message.trim() || null
      });
      trackLeadSubmit('precheck_session', ctaId);
      notifications.show({
        color: 'teal',
        title: '상담 신청이 접수되었어요',
        message: '담당자가 영업일 기준 1일 이내에 연락드릴게요.'
      });
      onSubmitted?.();
    } catch (error) {
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
    <Card withBorder padding="md" radius="md" component="form" onSubmit={handleSubmit}>
      <Stack gap="sm">
        <TextInput
          label="이름"
          withAsterisk
          placeholder="예: 홍길동"
          disabled={nameLocked}
          {...form.getInputProps('applicant_name')}
        />
        <PhoneInput
          label="연락처"
          withAsterisk
          disabled={phoneLocked}
          {...form.getInputProps('applicant_phone')}
        />
        {prefillAddress?.trim() ? (
          <Stack gap={2}>
            <Text size="xs" c="dimmed">
              현장 주소
            </Text>
            <Text size="sm" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <IconMapPin size={14} aria-hidden />
              {prefillAddress.trim()}
            </Text>
          </Stack>
        ) : null}
        <Textarea
          label="상담 내용 (선택)"
          placeholder="현장 상황이나 궁금한 점을 적어주세요."
          autosize
          minRows={2}
          {...form.getInputProps('message')}
        />
        <Alert color="jippin" variant="light" radius="md" p="xs">
          <Text size="xs">사전검토 내용과 함께 전달돼요. 정보는 상담 진행에만 사용돼요.</Text>
        </Alert>
        <Button type="submit" color="coral" radius="md" fullWidth loading={submitting}>
          상담 신청하기
        </Button>
      </Stack>
    </Card>
  );
}

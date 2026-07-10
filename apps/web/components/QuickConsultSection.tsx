'use client';

import {
  Anchor,
  Badge,
  Box,
  Card,
  Container,
  Group,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  TextInput,
  ThemeIcon,
  Title
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  IconArrowRight,
  IconClockHour4,
  IconShieldLock,
  IconUserCheck
} from '@tabler/icons-react';
import { Controller, useForm } from 'react-hook-form';
import { PhoneInput } from '@/components/inputs/PhoneInput';
import { CtaButton } from '@/components/ui';
import { trackLeadSubmit } from '@/lib/analytics/lead-cta';
import { parseApiError } from '@/lib/api/error';
import { createLead } from '@/lib/leads/api';
import { ensureAnonymousSession } from '@/lib/leads/ensure-anonymous-session';
import {
  normalizeKoreanPhone,
  quickConsultSchema,
  type QuickConsultValues
} from '@/lib/leads/validation';

const POINTS = [
  { icon: IconClockHour4, label: '영업일 1일 내 연락' },
  { icon: IconUserCheck, label: '회원가입 없이 신청' },
  { icon: IconShieldLock, label: '상담 내용은 비공개' }
];

/**
 * 메인 랜딩의 "빠른 상담" CTA 섹션. 비회원(익명 Supabase 세션)도 신청 구분·이름·연락처·
 * 메모만으로 즉시 상담을 신청할 수 있다 (POST /leads, source_form='main_page', CMP-DIRECT).
 */
export function QuickConsultSection() {
  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors, isSubmitting }
  } = useForm<QuickConsultValues>({
    resolver: zodResolver(quickConsultSchema),
    mode: 'onTouched',
    defaultValues: {
      applicant_kind: 'individual',
      applicant_name: '',
      applicant_phone: '',
      message: ''
    }
  });

  async function onSubmit(values: QuickConsultValues) {
    try {
      // 비로그인도 가능: 익명 세션 보장 후 리드 생성.
      await ensureAnonymousSession();
      await createLead({
        source_form: 'main_page',
        applicant_kind: values.applicant_kind,
        applicant_name: values.applicant_name.trim(),
        applicant_phone: normalizeKoreanPhone(values.applicant_phone) ?? values.applicant_phone,
        message: values.message.trim() || null
      });
      // 인라인 폼이라 /leads/new 를 거치지 않는다 — 위치 식별자를 직접 지정.
      trackLeadSubmit('main_page', 'home_quick_form');
      notifications.show({
        color: 'teal',
        title: '상담 신청이 접수되었어요',
        message: `${values.applicant_name.trim()}님, 영업일 기준 1일 이내에 연락드릴게요.`
      });
      reset();
    } catch (error) {
      notifications.show({
        color: 'red',
        title: '상담 신청에 실패했어요',
        message: parseApiError(error).message
      });
    }
  }

  return (
    <Box
      id="quick-consult"
      style={{
        borderTop: '1px solid var(--jippin-brand-border)',
        // 흰 캔버스 기준 재보정 — 틸 틴트만 투명으로 페이드시켜 제도 격자가
        // 여백에서 비치게 한다(옛 회색 #F8F9FA 바탕은 격자와 어긋난 회색 섬이 됨).
        background:
          'radial-gradient(120% 120% at 15% 0%, var(--mantine-color-jippin-0) 0%, rgba(255,255,255,0) 55%)'
      }}
    >
      <Container
        size="lg"
        style={{
          paddingTop: 'var(--jippin-section-py)',
          paddingBottom: 'var(--jippin-section-py)'
        }}
      >
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing={48} verticalSpacing="xl">
          <Stack gap="md" justify="center">
            <Badge color="jippin" variant="outline" radius="sm" size="lg" w="fit-content">
              빠른 상담
            </Badge>
            <Title
              order={2}
              style={{
                fontSize: 'var(--jippin-fz-display)',
                lineHeight: 1.25,
                letterSpacing: '-0.02em',
                wordBreak: 'keep-all'
              }}
            >
              전화 한 통 없이,
              <br />
              여기서 바로 신청하세요
            </Title>
            <Stack gap="xs" mt="xs">
              {POINTS.map((p) => (
                <Group key={p.label} gap="xs" wrap="nowrap">
                  <ThemeIcon size={26} variant="transparent" color="jippin">
                    <p.icon size={18} />
                  </ThemeIcon>
                  <Text size="sm" c="dimmed">
                    {p.label}
                  </Text>
                </Group>
              ))}
            </Stack>
          </Stack>

          <Card
            withBorder
            padding="xl"
            shadow="sm"
            component="form"
            onSubmit={handleSubmit(onSubmit)}
            noValidate
          >
            <Stack gap="md">
              <Controller
                name="applicant_kind"
                control={control}
                render={({ field }) => (
                  <SegmentedControl
                    fullWidth
                    size="md"
                    value={field.value}
                    onChange={field.onChange}
                    data={[
                      { value: 'individual', label: '개인' },
                      { value: 'company', label: '업체' }
                    ]}
                    aria-label="신청 구분"
                  />
                )}
              />
              <TextInput
                label="이름"
                placeholder="예: 홍길동"
                size="md"
                withAsterisk
                error={errors.applicant_name?.message}
                {...register('applicant_name')}
              />
              <Controller
                name="applicant_phone"
                control={control}
                render={({ field }) => (
                  <PhoneInput
                    label="연락처"
                    size="md"
                    withAsterisk
                    value={field.value}
                    onChange={field.onChange}
                    onBlur={field.onBlur}
                    error={errors.applicant_phone?.message}
                  />
                )}
              />
              <Textarea
                label="간단 메모 (선택)"
                placeholder="어떤 점이 궁금하신가요?"
                size="md"
                minRows={2}
                autosize
                error={errors.message?.message}
                {...register('message')}
              />
              {/* 전환 CTA(코랄) — 이 화면(홈 랜딩)의 코랄 1회는 이 제출 버튼이다. */}
              <CtaButton
                type="submit"
                fullWidth
                loading={isSubmitting}
                rightSection={<IconArrowRight size={18} />}
              >
                상담 신청하기
              </CtaButton>
              <Text
                size="xs"
                c="dimmed"
                ta="center"
                style={{ wordBreak: 'keep-all' }}
              >
                신청 시{' '}
                <Anchor href="/terms" size="xs" c="var(--jippin-brand-primary)">
                  이용약관
                </Anchor>{' '}
                및{' '}
                <Anchor href="/privacy" size="xs" c="var(--jippin-brand-primary)">
                  개인정보처리방침
                </Anchor>
                에 동의하는 것으로 간주됩니다.
              </Text>
            </Stack>
          </Card>
        </SimpleGrid>
      </Container>
    </Box>
  );
}

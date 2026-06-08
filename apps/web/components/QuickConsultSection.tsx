'use client';

import {
  Anchor,
  Badge,
  Box,
  Button,
  Card,
  Container,
  Group,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  TextInput,
  ThemeIcon,
  Title
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import {
  IconArrowRight,
  IconClockHour4,
  IconShieldLock,
  IconUserCheck
} from '@tabler/icons-react';
import { useState, type FormEvent } from 'react';

const POINTS = [
  { icon: IconClockHour4, label: '영업일 1일 내 연락' },
  { icon: IconUserCheck, label: '회원가입 없이 신청' },
  { icon: IconShieldLock, label: '상담 내용은 비공개' }
];

/**
 * 메인 랜딩의 "빠른 상담" CTA 섹션. 비회원도 이름·연락처만으로 즉시 상담을 신청할 수 있다.
 * 디자인 단계: 실제 리드 생성 API 연결 전이라 제출 시 접수 알림만 표시한다.
 */
export function QuickConsultSection() {
  const [name, setName] = useState('');
  const [contact, setContact] = useState('');
  const [memo, setMemo] = useState('');

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim() || !contact.trim()) {
      notifications.show({
        color: 'red',
        title: '입력을 확인해 주세요',
        message: '이름과 연락처는 필수입니다.'
      });
      return;
    }
    notifications.show({
      color: 'teal',
      title: '상담 신청이 접수되었어요',
      message: `${name.trim()}님, 영업일 기준 1일 이내에 연락드릴게요.`
    });
    setName('');
    setContact('');
    setMemo('');
  }

  return (
    <Box
      id="quick-consult"
      style={{
        borderTop: '1px solid var(--jippin-brand-border)',
        background:
          'radial-gradient(120% 120% at 15% 0%, #E2F1EF 0%, rgba(248,249,250,0) 55%), #F8F9FA'
      }}
    >
      <Container
        size="lg"
        style={{
          paddingTop: 'clamp(3rem, 6vw, 5rem)',
          paddingBottom: 'clamp(3rem, 6vw, 5rem)'
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
                fontSize: 'clamp(1.6rem, 3.2vw, 2.25rem)',
                lineHeight: 1.2,
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
            radius="lg"
            padding="xl"
            shadow="sm"
            component="form"
            onSubmit={handleSubmit}
          >
            <Stack gap="md">
              <TextInput
                label="이름"
                placeholder="예: 홍길동"
                radius="md"
                size="md"
                withAsterisk
                value={name}
                onChange={(e) => setName(e.currentTarget.value)}
              />
              <TextInput
                label="연락처"
                placeholder="010-0000-0000 또는 이메일"
                radius="md"
                size="md"
                withAsterisk
                value={contact}
                onChange={(e) => setContact(e.currentTarget.value)}
              />
              <Textarea
                label="간단 메모 (선택)"
                placeholder="어떤 점이 궁금하신가요?"
                radius="md"
                size="md"
                minRows={2}
                autosize
                value={memo}
                onChange={(e) => setMemo(e.currentTarget.value)}
              />
              <Button
                type="submit"
                size="md"
                color="coral"
                radius="md"
                fullWidth
                rightSection={<IconArrowRight size={18} />}
              >
                상담 신청하기
              </Button>
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

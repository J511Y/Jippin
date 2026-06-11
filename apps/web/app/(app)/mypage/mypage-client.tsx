'use client';

import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Group,
  Loader,
  Modal,
  PasswordInput,
  Stack,
  Tabs,
  Text,
  ThemeIcon,
  Title
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  IconClipboardList,
  IconInbox,
  IconLogout,
  IconUser
} from '@tabler/icons-react';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';

import {
  AccountApiError,
  changePassword,
  deleteAccount,
  listMyLeads,
  type MyLead
} from '@/lib/auth/account-api';
import { changePasswordSchema, type ChangePasswordValues } from '@/lib/auth/validation';
import { createClient } from '@/lib/supabase/client';

/**
 * 마이페이지 (CMP-DIRECT).
 *
 * '내 정보'(프로필 · 비밀번호 변경 · 회원 탈퇴)와 '상담 현황'(기존 /contacts 에서
 * 이동) 두 탭으로 구성한다. 활성 탭은 URL 쿼리(`?tab=`)와 동기화해 딥링크를
 * 지원한다.
 */

type MyPageTab = 'profile' | 'consultations';

const DEFAULT_TAB: MyPageTab = 'profile';

function isMyPageTab(value: string | null): value is MyPageTab {
  return value === 'profile' || value === 'consultations';
}

const STATUS_LABEL: Record<string, { label: string; color: string }> = {
  new: { label: '접수됨', color: 'jippin' },
  contacted: { label: '연락 완료', color: 'success' },
  in_progress: { label: '진행 중', color: 'success' },
  closed: { label: '완료', color: 'gray' },
  spam: { label: '종료', color: 'gray' }
};

async function logout() {
  await fetch('/auth/logout', { method: 'POST' }).catch(() => undefined);
  window.location.assign('/');
}

function leadTitle(lead: MyLead): string {
  const addr = [lead.road_addr_part1, lead.road_addr_part2].filter(Boolean).join(' ');
  return addr || `${lead.applicant_name}님 상담`;
}

export function MyPageClient() {
  const router = useRouter();
  const pathname = usePathname();

  const [email, setEmail] = useState<string | null>(null);
  const [name, setName] = useState<string | null>(null);
  const [isEmailUser, setIsEmailUser] = useState(false);
  const [authReady, setAuthReady] = useState(false);
  const [tab, setTab] = useState<MyPageTab>(DEFAULT_TAB);

  useEffect(() => {
    const supabase = createClient();
    void supabase.auth.getSession().then(({ data: { session } }) => {
      const user = session?.user;
      setEmail(user?.email ?? null);
      const meta = (user?.user_metadata ?? {}) as { name?: string; display_name?: string };
      setName(meta.name ?? meta.display_name ?? null);
      // 비밀번호 변경은 자체(이메일/비밀번호) 가입자만 가능하다. 카카오 등 소셜 로그인은
      // auth.users 에 비밀번호가 없으므로 해당 영역을 숨긴다.
      const appMeta = (user?.app_metadata ?? {}) as { provider?: string; providers?: string[] };
      const providers = appMeta.providers ?? (appMeta.provider ? [appMeta.provider] : []);
      setIsEmailUser(providers.includes('email'));
      setAuthReady(true);
    });
  }, []);

  // 공유된 URL(`/mypage?tab=`)의 탭 상태는 마운트 후 한 번만 반영한다.
  // FaqBrowser 와 같은 패턴 — useSearchParams 의 Suspense 요구를 피하면서
  // SSR 은 기본 탭으로 렌더한다(외부 시스템 = URL 의 의도된 1회 동기화).
  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect */
    const raw = new URLSearchParams(window.location.search).get('tab');
    if (isMyPageTab(raw)) setTab(raw);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, []);

  const handleTab = (value: string | null) => {
    const next = isMyPageTab(value) ? value : DEFAULT_TAB;
    setTab(next);
    router.replace(next === DEFAULT_TAB ? pathname : `${pathname}?tab=${next}`, {
      scroll: false
    });
  };

  return (
    <Stack gap="lg">
      <Group justify="space-between" align="flex-end" wrap="nowrap">
        <Title order={1} fz="h1">
          마이페이지
        </Title>
        <Button
          variant="subtle"
          color="gray"
          leftSection={<IconLogout size={16} />}
          onClick={() => void logout()}
        >
          로그아웃
        </Button>
      </Group>

      <Tabs value={tab} onChange={handleTab} color="jippin" keepMounted>
        <Tabs.List>
          <Tabs.Tab value="profile" leftSection={<IconUser size={16} />}>
            내 정보
          </Tabs.Tab>
          <Tabs.Tab value="consultations" leftSection={<IconClipboardList size={16} />}>
            상담 현황
          </Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="profile" pt="lg">
          <Stack gap="xl">
            <ProfileCard email={email} name={name} ready={authReady} />
            {isEmailUser ? <PasswordChangeCard /> : null}
            <DeleteAccountCard />
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="consultations" pt="lg">
          <ConsultationsSection />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}

function ProfileCard({
  email,
  name,
  ready
}: {
  email: string | null;
  name: string | null;
  ready: boolean;
}) {
  return (
    <Card withBorder radius="lg" padding="lg">
      <Group gap="md" wrap="nowrap">
        <ThemeIcon size={44} radius="xl" variant="light" color="jippin">
          <IconUser size={22} />
        </ThemeIcon>
        <Stack gap={2}>
          {ready ? (
            <>
              <Text fw={600}>{name ?? '회원'}</Text>
              <Text size="sm" c="dimmed">
                {email ?? '이메일 정보 없음'}
              </Text>
            </>
          ) : (
            <Loader size="sm" />
          )}
        </Stack>
      </Group>
    </Card>
  );
}

function ConsultationsSection() {
  const [leads, setLeads] = useState<MyLead[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    listMyLeads()
      .then((items) => {
        if (active) setLeads(items);
      })
      .catch((err) => {
        if (active)
          setError(err instanceof AccountApiError ? err.message : '상담 현황을 불러오지 못했습니다.');
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <Stack gap="sm">
      <Group justify="space-between" align="center">
        <Title order={2} fz="h3">
          상담 현황
        </Title>
        <Button component="a" href="/leads/new" color="coral" radius="md" size="xs">
          새 상담
        </Button>
      </Group>

      {error ? (
        <Alert color="red" variant="light">
          {error}
        </Alert>
      ) : leads === null ? (
        <Group justify="center" py="lg">
          <Loader size="sm" />
        </Group>
      ) : leads.length === 0 ? (
        <Card withBorder radius="lg" padding="xl">
          <Stack align="center" gap="sm" ta="center" py="md">
            <ThemeIcon size={48} radius="xl" variant="light" color="gray">
              <IconInbox size={24} />
            </ThemeIcon>
            <Text fw={600}>아직 신청한 상담이 없어요</Text>
            <Text size="sm" c="dimmed">
              전문가 상담을 신청하면 여기에서 진행 상태를 확인할 수 있어요.
            </Text>
            <Button component="a" href="/leads/new" color="coral" radius="md" mt="xs">
              상담 신청하기
            </Button>
          </Stack>
        </Card>
      ) : (
        <Stack gap="sm">
          {leads.map((lead) => {
            const status = STATUS_LABEL[lead.status] ?? { label: lead.status, color: 'gray' };
            return (
              <Card key={lead.id} withBorder radius="lg" padding="lg">
                <Stack gap={6}>
                  <Text fw={600} style={{ wordBreak: 'keep-all' }}>
                    {leadTitle(lead)}
                  </Text>
                  <Group gap="xs">
                    <Badge color={status.color} variant="light" radius="sm">
                      {status.label}
                    </Badge>
                    {lead.expansion_location ? (
                      <Text size="xs" c="dimmed">
                        {lead.expansion_location}
                      </Text>
                    ) : null}
                    <Text size="xs" c="dimmed">
                      {lead.created_at.slice(0, 10)} 신청
                    </Text>
                  </Group>
                </Stack>
              </Card>
            );
          })}
        </Stack>
      )}
    </Stack>
  );
}

function PasswordChangeCard() {
  const [serverError, setServerError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting }
  } = useForm<ChangePasswordValues>({
    resolver: zodResolver(changePasswordSchema),
    mode: 'onTouched',
    defaultValues: { current: '', password: '', confirm: '' }
  });

  async function onSubmit(values: ChangePasswordValues) {
    setServerError(null);
    setDone(false);
    try {
      await changePassword(values.current, values.password);
      setDone(true);
      reset();
    } catch (err) {
      setServerError(err instanceof AccountApiError ? err.message : '비밀번호 변경에 실패했습니다.');
    }
  }

  return (
    <Card withBorder radius="lg" padding="lg">
      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <Stack gap="sm">
          <Title order={2} fz="h3">
            비밀번호 변경
          </Title>
          {/* lg 컨테이너에서도 입력 줄 길이는 읽기 좋게 480px 로 제한한다. */}
          <Box maw={480}>
            <Stack gap="sm">
              <PasswordInput
                label="현재 비밀번호"
                autoComplete="current-password"
                error={errors.current?.message}
                {...register('current')}
              />
              <PasswordInput
                label="새 비밀번호"
                description="6자 이상, 영문과 숫자 포함"
                autoComplete="new-password"
                error={errors.password?.message}
                {...register('password')}
              />
              <PasswordInput
                label="새 비밀번호 확인"
                autoComplete="new-password"
                error={errors.confirm?.message}
                {...register('confirm')}
              />
            </Stack>
          </Box>
          {serverError ? (
            <Alert color="red" variant="light" py="xs">
              {serverError}
            </Alert>
          ) : null}
          {done ? (
            <Alert color="teal" variant="light" py="xs">
              비밀번호가 변경되었습니다.
            </Alert>
          ) : null}
          <Button type="submit" color="jippin" radius="md" loading={isSubmitting} w="fit-content">
            비밀번호 변경
          </Button>
        </Stack>
      </form>
    </Card>
  );
}

function DeleteAccountCard() {
  const [opened, { open, close }] = useDisclosure(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    setLoading(true);
    setError(null);
    try {
      await deleteAccount();
      await logout();
    } catch (err) {
      setError(err instanceof AccountApiError ? err.message : '회원 탈퇴에 실패했습니다.');
      setLoading(false);
    }
  }

  return (
    <Card withBorder radius="lg" padding="lg">
      <Stack gap="sm">
        <Title order={2} fz="h3" c="red">
          회원 탈퇴
        </Title>
        <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
          탈퇴하면 계정 정보가 삭제되며 되돌릴 수 없습니다. 신청한 상담 내역은 운영팀
          처리를 위해 익명으로 보존될 수 있습니다.
        </Text>
        <Button variant="light" color="red" radius="md" w="fit-content" onClick={open}>
          회원 탈퇴
        </Button>
      </Stack>

      <Modal opened={opened} onClose={close} title="정말 탈퇴하시겠어요?" centered>
        <Stack gap="md">
          <Text size="sm" style={{ wordBreak: 'keep-all' }}>
            탈퇴 후에는 같은 이메일로 다시 가입해야 하며 계정을 복구할 수 없습니다.
          </Text>
          {error ? (
            <Alert color="red" variant="light" py="xs">
              {error}
            </Alert>
          ) : null}
          <Group justify="flex-end">
            <Button variant="default" onClick={close} disabled={loading}>
              취소
            </Button>
            <Button color="red" loading={loading} onClick={() => void handleDelete()}>
              탈퇴하기
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Card>
  );
}

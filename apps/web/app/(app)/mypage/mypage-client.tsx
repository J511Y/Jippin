'use client';

import {
  Alert,
  Badge,
  Button,
  Card,
  Divider,
  Group,
  Loader,
  Modal,
  PasswordInput,
  Stack,
  Text,
  ThemeIcon,
  Title
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconInbox, IconLogout, IconUser } from '@tabler/icons-react';
import { useEffect, useState } from 'react';

import {
  AccountApiError,
  changePassword,
  deleteAccount,
  listMyLeads,
  type MyLead
} from '@/lib/auth/account-api';
import { createClient } from '@/lib/supabase/client';

/**
 * 마이페이지 (CMP-DIRECT).
 *
 * 프로필 · 상담 현황(기존 /contacts 에서 이동) · 비밀번호 변경 · 로그아웃/회원 탈퇴.
 */

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
  const [email, setEmail] = useState<string | null>(null);
  const [name, setName] = useState<string | null>(null);
  const [authReady, setAuthReady] = useState(false);

  useEffect(() => {
    const supabase = createClient();
    void supabase.auth.getSession().then(({ data: { session } }) => {
      const user = session?.user;
      setEmail(user?.email ?? null);
      const meta = (user?.user_metadata ?? {}) as { name?: string; display_name?: string };
      setName(meta.name ?? meta.display_name ?? null);
      setAuthReady(true);
    });
  }, []);

  return (
    <Stack gap="xl">
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

      <ProfileCard email={email} name={name} ready={authReady} />
      <ConsultationsSection />
      <PasswordChangeCard />
      <DeleteAccountCard />
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

const MIN_PASSWORD = 6;
const HAS_LETTER = /[A-Za-z]/;
const HAS_DIGIT = /\d/;

function passwordError(pw: string): string | null {
  if (pw.length < MIN_PASSWORD) return `비밀번호는 최소 ${MIN_PASSWORD}자 이상이어야 합니다.`;
  if (!HAS_LETTER.test(pw) || !HAS_DIGIT.test(pw)) return '비밀번호는 영문과 숫자를 모두 포함해야 합니다.';
  return null;
}

function PasswordChangeCard() {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setDone(false);
    if (!current) return setError('현재 비밀번호를 입력해 주세요.');
    const pwErr = passwordError(next);
    if (pwErr) return setError(pwErr);
    if (next !== confirm) return setError('새 비밀번호가 일치하지 않습니다.');

    setLoading(true);
    try {
      await changePassword(current, next);
      setDone(true);
      setCurrent('');
      setNext('');
      setConfirm('');
    } catch (err) {
      setError(err instanceof AccountApiError ? err.message : '비밀번호 변경에 실패했습니다.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card withBorder radius="lg" padding="lg">
      <form onSubmit={handleSubmit} noValidate>
        <Stack gap="sm">
          <Title order={2} fz="h3">
            비밀번호 변경
          </Title>
          <PasswordInput
            label="현재 비밀번호"
            value={current}
            onChange={(e) => setCurrent(e.currentTarget.value)}
            autoComplete="current-password"
          />
          <PasswordInput
            label="새 비밀번호"
            description="6자 이상, 영문과 숫자 포함"
            value={next}
            onChange={(e) => setNext(e.currentTarget.value)}
            autoComplete="new-password"
          />
          <PasswordInput
            label="새 비밀번호 확인"
            value={confirm}
            onChange={(e) => setConfirm(e.currentTarget.value)}
            autoComplete="new-password"
          />
          {error ? (
            <Alert color="red" variant="light" py="xs">
              {error}
            </Alert>
          ) : null}
          {done ? (
            <Alert color="teal" variant="light" py="xs">
              비밀번호가 변경되었습니다.
            </Alert>
          ) : null}
          <Button type="submit" color="jippin" radius="md" loading={loading} w="fit-content">
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
        <Divider />
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

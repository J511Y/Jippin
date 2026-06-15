'use client';

import {
  ActionIcon,
  AppShell,
  Box,
  Burger,
  Button,
  Container,
  Drawer,
  Group,
  Stack,
  Text,
  Tooltip,
  UnstyledButton
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconLogout, IconUser } from '@tabler/icons-react';
import Image from 'next/image';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState, type ReactNode } from 'react';

import { createClient } from '@/lib/supabase/client';

const HEADER_HEIGHT = 60;

type NavItem = {
  href: string;
  label: string;
  match: (pathname: string) => boolean;
};

// '상담'(/contacts) 메뉴는 제거됨 — 상담 현황은 마이페이지로 이동했다(CMP-DIRECT).
const NAV_ITEMS: NavItem[] = [
  { href: '/sessions', label: '사전검토', match: (p) => p.startsWith('/sessions') },
  { href: '/home-check', label: '우리집 체크', match: (p) => p.startsWith('/home-check') },
  { href: '/prices', label: '가격', match: (p) => p.startsWith('/prices') },
  { href: '/faq', label: '자주묻는질문', match: (p) => p.startsWith('/faq') }
];

// 목록·상세 중심 페이지(검토/자주묻는질문/마이페이지)는 PC 에서 lg 로 넓게,
// 입력 폼(로그인·상담 신청·새 검토)과 약관류는 가독성을 위해 sm 을 유지한다.
const WIDE_ROUTE_PREFIXES = ['/sessions', '/faq', '/mypage', '/home-check'];

function mainContainerSize(pathname: string): 'sm' | 'lg' {
  // 입력 폼 페이지는 가독성을 위해 좁게(sm) 유지한다.
  if (pathname.startsWith('/sessions/new') || pathname.startsWith('/home-check/new')) {
    return 'sm';
  }
  return WIDE_ROUTE_PREFIXES.some((prefix) => pathname.startsWith(prefix))
    ? 'lg'
    : 'sm';
}

/**
 * 헤더 인증 상태 — 영구(비익명) Supabase 세션이 있으면 '마이페이지', 아니면 '로그인'.
 */
function useIsMember(): boolean {
  const [isMember, setIsMember] = useState(false);

  useEffect(() => {
    const supabase = createClient();
    let active = true;

    const evaluate = (session: { user?: { is_anonymous?: boolean } } | null) => {
      if (!active) return;
      const user = session?.user;
      setIsMember(Boolean(user) && user?.is_anonymous !== true);
    };

    void supabase.auth.getSession().then(({ data }) => evaluate(data.session));
    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) =>
      evaluate(session)
    );

    return () => {
      active = false;
      sub.subscription.unsubscribe();
    };
  }, []);

  return isMember;
}

async function logout() {
  await fetch('/auth/logout', { method: 'POST' }).catch(() => undefined);
  window.location.assign('/');
}

function NavLink({
  item,
  active,
  onNavigate
}: {
  item: NavItem;
  active: boolean;
  onNavigate?: () => void;
}) {
  return (
    <UnstyledButton
      component={Link}
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? 'page' : undefined}
      style={{
        display: 'block',
        padding: '8px 12px',
        borderRadius: 'var(--mantine-radius-md)',
        fontSize: 'var(--mantine-font-size-md)',
        fontWeight: active ? 600 : 500,
        color: active
          ? 'var(--jippin-brand-primary)'
          : 'var(--jippin-brand-copy)',
        backgroundColor: active ? 'var(--mantine-color-jippin-0)' : 'transparent',
        lineHeight: 1.4
      }}
    >
      {item.label}
    </UnstyledButton>
  );
}

function BrandMark({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <UnstyledButton
      component={Link}
      href="/"
      onClick={onNavigate}
      aria-label="집핀 홈"
      style={{ display: 'flex', alignItems: 'center', gap: 8 }}
    >
      <Image
        src="/logo.png"
        alt="집핀"
        width={36}
        height={36}
        priority
        style={{ display: 'block', width: 36, height: 36 }}
      />
      <Text
        component="span"
        fw={700}
        fz="1.125rem"
        c="var(--jippin-brand-ink)"
        style={{ letterSpacing: '-0.01em' }}
      >
        집핀
      </Text>
    </UnstyledButton>
  );
}

export function SiteShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? '/';
  const [drawerOpened, drawer] = useDisclosure(false);
  const isMember = useIsMember();

  return (
    <AppShell
      header={{ height: HEADER_HEIGHT }}
      padding={0}
      // 외부 footer 와 함께 sticky-footer 가 되도록 Main 의 viewport 기반 min-height 를 해제한다.
      styles={{ main: { minHeight: 0 } }}
    >
      <AppShell.Header
        withBorder
        style={{ backgroundColor: 'var(--jippin-brand-surface-alt)' }}
      >
        <Container size="lg" h="100%">
          <Group h="100%" justify="space-between" wrap="nowrap" gap="md">
            <BrandMark />

            <Group gap={4} visibleFrom="sm" wrap="nowrap">
              {NAV_ITEMS.map((item) => (
                <NavLink
                  key={item.href}
                  item={item}
                  active={item.match(pathname)}
                />
              ))}
            </Group>

            <Group gap="xs" wrap="nowrap">
              {isMember ? (
                <Group gap={4} wrap="nowrap" visibleFrom="sm">
                  <Tooltip label="마이페이지" withArrow position="bottom">
                    <ActionIcon
                      component={Link}
                      href="/mypage"
                      size="lg"
                      radius="xl"
                      variant="subtle"
                      color="jippin"
                      aria-label="마이페이지"
                    >
                      <IconUser size={20} />
                    </ActionIcon>
                  </Tooltip>
                  <Button
                    size="sm"
                    variant="subtle"
                    color="gray"
                    radius="md"
                    leftSection={<IconLogout size={16} />}
                    onClick={() => void logout()}
                  >
                    로그아웃
                  </Button>
                </Group>
              ) : (
                <Button
                  component={Link}
                  href="/login"
                  size="sm"
                  variant="subtle"
                  color="jippin"
                  radius="md"
                  visibleFrom="sm"
                >
                  로그인
                </Button>
              )}
              <Burger
                opened={drawerOpened}
                onClick={drawer.toggle}
                size="sm"
                hiddenFrom="sm"
                aria-label="메뉴 열기"
              />
            </Group>
          </Group>
        </Container>
      </AppShell.Header>

      <AppShell.Main>
        {pathname === '/' || pathname === '/prices' ? (
          // 랜딩(홈·가격)은 풀블리드 섹션을 직접 제어한다.
          children
        ) : (
          <Container size={mainContainerSize(pathname)} py="xl">
            {children}
          </Container>
        )}
      </AppShell.Main>

      <Drawer
        opened={drawerOpened}
        onClose={drawer.close}
        position="right"
        size="78%"
        padding="md"
        title={<BrandMark onNavigate={drawer.close} />}
        hiddenFrom="sm"
        zIndex={200}
      >
        <Stack gap={4} mt="sm">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.href}
              item={item}
              active={item.match(pathname)}
              onNavigate={drawer.close}
            />
          ))}
          <Box mt="md">
            {isMember ? (
              <Stack gap="xs">
                <Button
                  component={Link}
                  href="/mypage"
                  onClick={drawer.close}
                  fullWidth
                  variant="light"
                  color="jippin"
                  radius="md"
                  leftSection={<IconUser size={18} />}
                >
                  마이페이지
                </Button>
                <Button
                  fullWidth
                  variant="subtle"
                  color="gray"
                  radius="md"
                  leftSection={<IconLogout size={18} />}
                  onClick={() => {
                    drawer.close();
                    void logout();
                  }}
                >
                  로그아웃
                </Button>
              </Stack>
            ) : (
              <Button
                component={Link}
                href="/login"
                onClick={drawer.close}
                fullWidth
                variant="light"
                color="jippin"
                radius="md"
              >
                로그인
              </Button>
            )}
          </Box>
        </Stack>
      </Drawer>
    </AppShell>
  );
}

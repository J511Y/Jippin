'use client';

import {
  AppShell,
  Box,
  Burger,
  Button,
  Container,
  Drawer,
  Group,
  Stack,
  Text,
  UnstyledButton
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
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
  { href: '/sessions', label: '검토', match: (p) => p.startsWith('/sessions') },
  { href: '/prices', label: '가격', match: (p) => p.startsWith('/prices') }
];

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
        fontSize: 'var(--mantine-font-size-sm)',
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
        visibleFrom="sm"
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
  const accountHref = isMember ? '/mypage' : '/login';
  const accountLabel = isMember ? '마이페이지' : '로그인';

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
              <Button
                component={Link}
                href={accountHref}
                size="sm"
                variant="subtle"
                color="jippin"
                radius="md"
                visibleFrom="sm"
              >
                {accountLabel}
              </Button>
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
          <Container size="sm" py="xl">
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
            <Button
              component={Link}
              href={accountHref}
              onClick={drawer.close}
              fullWidth
              variant="light"
              color="jippin"
              radius="md"
            >
              {accountLabel}
            </Button>
          </Box>
        </Stack>
      </Drawer>
    </AppShell>
  );
}

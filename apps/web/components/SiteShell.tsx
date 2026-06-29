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

import { LegalNotice } from '@/components/LegalNotice';
import { createClient } from '@/lib/supabase/client';

const HEADER_HEIGHT = 60;

type NavItem = {
  href: string;
  label: string;
  match: (pathname: string) => boolean;
};

// '상담'(/contacts) 메뉴는 제거됨 — 상담 현황은 마이페이지로 이동했다(CMP-DIRECT).
// '사전검토'는 사이트 내 사용자를 곧장 채팅 진입(`/sessions`)으로 보낸다. 색인 가능한
// 안내 페이지(`/sessions/landing`)는 외부 마케팅 인입 전용이라 내비에 노출하지 않는다.
const NAV_ITEMS: NavItem[] = [
  { href: '/sessions', label: '사전검토', match: (p) => p.startsWith('/sessions') },
  { href: '/home-check', label: '우리집 체크', match: (p) => p.startsWith('/home-check') },
  { href: '/prices', label: '가격', match: (p) => p.startsWith('/prices') },
  { href: '/faq', label: '자주묻는질문', match: (p) => p.startsWith('/faq') }
];

// 목록·상세 중심 페이지(검토/자주묻는질문/마이페이지)는 PC 에서 lg 로 넓게,
// 메인 컨테이너 폭 규칙(정본: docs/design/DESIGN.md §"레이아웃 컨테이너 폭").
// 기능 페이지(목록·상세·리포트·우리집 체크 전반)는 헤더와 같은 lg 를 쓴다.
// sm 은 "단일 입력 폼" 한정 — 좁은 폭이 입력 가독성에 유리한 경우에만 명시적으로 좁힌다.
const WIDE_ROUTE_PREFIXES = ['/sessions', '/faq', '/mypage', '/home-check'];

// 대화형 채팅 경로 — 헤더 아래 남는 viewport 를 풀높이로 쓰도록 컨테이너 세로 패딩을
// 없애고 100dvh 기반 풀높이 레이아웃을 허용한다. 채팅 진입(/sessions)과 세션 상세
// (/sessions/[id])가 동일 폭(lg)·풀높이를 갖게 해 compose→대화 전환 시 폭/높이 점프를
// 막는다. 안내 랜딩(/sessions/landing)·리포트(/sessions/[id]/report)는 일반 문서 레이아웃.
function isChatRoute(pathname: string): boolean {
  // 공개 안내 랜딩은 일반 문서 레이아웃(스크롤 + 세로 패딩).
  if (pathname === '/sessions/landing') return false;
  // 채팅 진입(/sessions) 과 세션 상세(/sessions/[id]) 가 풀높이 채팅 화면이다.
  if (pathname === '/sessions' || pathname === '/sessions/') return true;
  if (!pathname.startsWith('/sessions/')) return false;
  // 리포트(/sessions/[id]/report)는 일반 문서 레이아웃을 유지한다.
  if (pathname.endsWith('/report')) return false;
  return true;
}

function mainContainerSize(pathname: string): 'sm' | 'lg' {
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
        {pathname === '/' ||
        pathname === '/prices' ||
        pathname === '/sessions/landing' ? (
          // 마케팅 랜딩(홈·가격·사전검토 랜딩)은 풀블리드 섹션을 직접 제어한다.
          children
        ) : isChatRoute(pathname) ? (
          // 대화형 채팅 — 헤더 아래 viewport 를 '정확히' 채우고(고정 높이 + overflow:hidden),
          // 내부 .chat-scroll 이 스스로 스크롤한다(페이지가 아닌 메시지 영역만 스크롤).
          // 이래야 모바일 진행계획 sticky·"맨 아래로" 버튼·하단 도크가 ChatGPT 처럼 동작한다.
          // 데스크톱 외부 footer 는 이 풀스크린 채팅 아래에 위치(페이지 스크롤로 노출).
          <Container
            size={mainContainerSize(pathname)}
            py={0}
            style={{
              display: 'flex',
              flexDirection: 'column',
              height: `calc(100dvh - ${HEADER_HEIGHT}px)`,
              overflow: 'hidden'
            }}
          >
            {children}
          </Container>
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

        {/* 푸터(법적 고지·사업자 표기)는 메인 화면 대신 이 메뉴 안에서 노출한다(모바일 영역 확보). */}
        <Box mt="xl" mx="calc(var(--mantine-spacing-md) * -1)">
          <LegalNotice />
        </Box>
      </Drawer>
    </AppShell>
  );
}

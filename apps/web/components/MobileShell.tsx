'use client';

import { Box, Container, UnstyledButton } from '@mantine/core';
import {
  IconBuildingSkyscraper,
  IconHome,
  IconReportMedical,
  IconTag
} from '@tabler/icons-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, type ReactNode } from 'react';

const BOTTOM_NAV_HEIGHT = 64;

type Tab = {
  href: string;
  label: string;
  match: (pathname: string) => boolean;
  Icon: typeof IconHome;
};

const tabs: Tab[] = [
  {
    href: '/',
    label: '홈',
    match: (p) => p === '/',
    Icon: IconHome
  },
  {
    href: '/sessions',
    label: '검토',
    match: (p) => p === '/sessions' || p.startsWith('/sessions/'),
    Icon: IconReportMedical
  },
  {
    href: '/contacts',
    label: '상담',
    match: (p) => p === '/contacts' || p.startsWith('/contacts/'),
    Icon: IconBuildingSkyscraper
  },
  {
    href: '/prices',
    label: '가격',
    match: (p) => p === '/prices',
    Icon: IconTag
  }
];

export function MobileShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? '/';

  useEffect(() => {
    // globals.css 의 body[data-mobile-shell='true'] padding 룰과 짝.
    // root layout 의 <LegalNotice />(footer 위치) 가 fixed bottom nav 위로 올라온다.
    document.body.dataset.mobileShell = 'true';
    return () => {
      delete document.body.dataset.mobileShell;
    };
  }, []);

  return (
    <Box
      style={{
        display: 'flex',
        flexDirection: 'column',
        minHeight: '100dvh',
        background: 'var(--mantine-color-body)'
      }}
    >
      <Container
        size={480}
        px="md"
        py="lg"
        style={{
          flex: 1,
          width: '100%',
          paddingBottom: `calc(${BOTTOM_NAV_HEIGHT}px + env(safe-area-inset-bottom, 0px) + var(--mantine-spacing-lg))`
        }}
      >
        {children}
      </Container>

      <Box
        component="nav"
        aria-label="모바일 주 내비게이션"
        data-testid="mobile-bottom-nav"
        style={{
          position: 'fixed',
          left: 0,
          right: 0,
          bottom: 0,
          paddingBottom: 'env(safe-area-inset-bottom, 0px)',
          background: 'var(--jippin-brand-surface-alt)',
          borderTop: '1px solid var(--jippin-brand-border)',
          zIndex: 50
        }}
      >
        <Box
          style={{
            display: 'grid',
            gridTemplateColumns: `repeat(${tabs.length}, 1fr)`,
            maxWidth: 480,
            margin: '0 auto',
            height: BOTTOM_NAV_HEIGHT
          }}
        >
          {tabs.map((tab) => {
            const active = tab.match(pathname);
            const { Icon } = tab;
            return (
              <UnstyledButton
                key={tab.href}
                component={Link}
                href={tab.href}
                aria-label={tab.label}
                aria-current={active ? 'page' : undefined}
                data-active={active ? 'true' : undefined}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 2,
                  color: active
                    ? 'var(--jippin-brand-primary)'
                    : 'var(--jippin-brand-copy)',
                  fontSize: 11,
                  fontWeight: active ? 600 : 500
                }}
              >
                <Icon size={22} stroke={active ? 2.2 : 1.7} aria-hidden />
                <span>{tab.label}</span>
              </UnstyledButton>
            );
          })}
        </Box>
      </Box>
    </Box>
  );
}

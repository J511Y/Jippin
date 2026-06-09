import { ColorSchemeScript, mantineHtmlProps } from '@mantine/core';
import type { Metadata, Viewport } from 'next';
import type { ReactNode } from 'react';
import { AnonymousLeadClaimer } from '@/components/AnonymousLeadClaimer';
import { LegalNotice } from '@/components/LegalNotice';
import { WebVitals } from '@/components/WebVitals';
import { Providers } from '@/lib/providers';
import {
  SITE_DESCRIPTION,
  SITE_KEYWORDS,
  SITE_NAME,
  SITE_NAME_FULL,
  SITE_OG_IMAGE,
  SITE_URL
} from '@/lib/site';
import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';
import '@mantine/dates/styles.css';
import './globals.css';

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: '집핀 (Jippin) — 베란다 확장·벽 철거 사전검토',
    template: `%s · ${SITE_NAME}`
  },
  description: SITE_DESCRIPTION,
  keywords: SITE_KEYWORDS,
  applicationName: SITE_NAME_FULL,
  // 마케팅/정보 페이지는 색인 허용이 기본값. 앱·인증 등 비공개 라우트는
  // 각 page 의 `robots: { index: false }` 와 robots.ts 의 disallow 로 덮어쓴다.
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true, 'max-image-preview': 'large' }
  },
  openGraph: {
    type: 'website',
    siteName: SITE_NAME_FULL,
    locale: 'ko_KR',
    url: SITE_URL,
    title: '집핀 (Jippin) — 베란다 확장·벽 철거 사전검토',
    description: SITE_DESCRIPTION,
    images: [{ url: SITE_OG_IMAGE, alt: SITE_NAME_FULL }]
  },
  twitter: {
    card: 'summary_large_image',
    title: '집핀 (Jippin) — 베란다 확장·벽 철거 사전검토',
    description: SITE_DESCRIPTION,
    images: [SITE_OG_IMAGE]
  },
  icons: {
    icon: [
      { url: '/favicon/favicon.ico', sizes: 'any' },
      { url: '/favicon/favicon.svg', type: 'image/svg+xml' },
      { url: '/favicon/favicon-96x96.png', type: 'image/png', sizes: '96x96' }
    ],
    apple: '/favicon/apple-touch-icon.png'
  },
  manifest: '/favicon/site.webmanifest'
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#147A73'
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // mantineHtmlProps: data-mantine-color-scheme + suppressHydrationWarning.
    // 브라우저 확장프로그램이 <html>/<body> 에 속성을 주입해도 hydration mismatch 로
    // 컴포넌트가 깨지지 않게 한다(뒤로가기 캐시 복원 포함). ColorSchemeScript 는 paint 전 적용.
    <html lang="ko" {...mantineHtmlProps}>
      <head>
        <ColorSchemeScript defaultColorScheme="light" />
      </head>
      <body>
        <Providers>
          <main style={{ flex: '1 0 auto' }}>{children}</main>
          <LegalNotice />
        </Providers>
        <AnonymousLeadClaimer />
        <WebVitals />
      </body>
    </html>
  );
}

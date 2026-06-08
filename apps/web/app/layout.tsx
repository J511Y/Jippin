import { ColorSchemeScript, mantineHtmlProps } from '@mantine/core';
import { Analytics } from '@vercel/analytics/next';
import { SpeedInsights } from '@vercel/speed-insights/next';
import type { Metadata, Viewport } from 'next';
import type { ReactNode } from 'react';
import { LegalNotice } from '@/components/LegalNotice';
import { Providers } from '@/lib/providers';
import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';
import '@mantine/dates/styles.css';
import './globals.css';

export const metadata: Metadata = {
  title: {
    default: '집핀 (Jippin)',
    template: '%s · 집핀'
  },
  description: '베란다 확장 가능여부 사전검토 AI 서비스',
  robots: { index: false, follow: false },
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
        <Analytics />
        <SpeedInsights />
      </body>
    </html>
  );
}

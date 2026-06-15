import { ColorSchemeScript, mantineHtmlProps } from '@mantine/core';
import { GoogleTagManager } from '@next/third-parties/google';
import type { Metadata, Viewport } from 'next';
import type { ReactNode } from 'react';
import { AnonymousLeadClaimer } from '@/components/AnonymousLeadClaimer';
import { LegalNotice } from '@/components/LegalNotice';
import { WebVitals } from '@/components/WebVitals';
import { Providers } from '@/lib/providers';
import {
  GTM_CONTAINER_ID,
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
        {/* paint 전 <html> 에 js-reveal 클래스를 붙여, JS 가 있을 때만 진입(reveal)
            대상을 SSR 단계부터 숨긴다. no-JS 사용자는 클래스가 없어 콘텐츠가 그대로
            보인다(점진적 향상). 콘텐츠가 보였다가 사라지며 올라오는 깜빡임을 막는다. */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "try{document.documentElement.classList.add('js-reveal')}catch(e){}"
          }}
        />
      </head>
      <body>
        <Providers>
          <main style={{ flex: '1 0 auto' }}>{children}</main>
          <LegalNotice />
        </Providers>
        <AnonymousLeadClaimer />
        <WebVitals />
      </body>
      {/* GTM(gtag.js). next/script 로 afterInteractive 주입하고 noscript iframe 도
          함께 렌더한다. GA4 등 실제 태그는 GTM 컨테이너 안에서 관리한다.

          운영 도메인(jippin.ai)에서만 켠다. NODE_ENV 는 Vercel 의 모든 빌드에서
          'production' 이라 dev.jippin.ai(Preview)·로컬을 구분하지 못한다. Vercel 이
          환경별로 주입하는 NEXT_PUBLIC_VERCEL_ENV 로 게이트해야 Production 만 잡힌다. */}
      {process.env.NEXT_PUBLIC_VERCEL_ENV === 'production' && GTM_CONTAINER_ID ? (
        <GoogleTagManager gtmId={GTM_CONTAINER_ID} />
      ) : null}
    </html>
  );
}

import { Box, ColorSchemeScript, mantineHtmlProps } from '@mantine/core';
import { GoogleTagManager } from '@next/third-parties/google';
import type { Metadata, Viewport } from 'next';
import type { ReactNode } from 'react';
import { AnonymousLeadClaimer } from '@/components/AnonymousLeadClaimer';
import { LegalNotice } from '@/components/LegalNotice';
import { MobileLegalFooter } from '@/components/MobileLegalFooter';
import { WebVitals } from '@/components/WebVitals';
import { Providers } from '@/lib/providers';
import {
  GTM_CONTAINER_ID,
  NAVER_SITE_VERIFICATION,
  SITE_DESCRIPTION,
  SITE_KEYWORDS,
  SITE_NAME,
  SITE_NAME_FULL,
  SITE_OG_IMAGE,
  SITE_URL
} from '@/lib/site';
/* 정본 폰트 Pretendard Variable — self-host(dynamic subset, font-display:swap).
   TYPOGRAPHY.md §1 은 Pretendard 를 정본으로 정하지만 지금까지 로딩 소스가 없어
   전 사용자가 폴백(맑은 고딕 등)을 보고 있었다. npm 패키지의 dynamic subset 은
   사용 글리프 범위만 분할 로드해 한국어 초기 페인트 회귀를 막는다. */
import 'pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css';
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
  manifest: '/favicon/site.webmanifest',
  // 검색엔진 사이트 소유확인. 네이버는 Next 가 1급 키(google/yandex 등)로 지원하지
  // 않으므로 `other` 로 넣는다 → <meta name="naver-site-verification" content="…" />.
  verification: {
    other: { 'naver-site-verification': NAVER_SITE_VERIFICATION }
  }
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#147A73',
  // 노치/홈 인디케이터 영역까지 그리고 env(safe-area-inset-*) 로 여백을 제어한다
  // (채팅·퍼널 하단 도크, 모바일 탭바). 가상 키보드가 올라오면 레이아웃 높이를
  // 줄여(resizes-content) 100dvh 기반 채팅 도크가 키보드 위에 붙게 한다.
  viewportFit: 'cover',
  interactiveWidget: 'resizes-content'
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
          {/* 푸터 게이트 — 데스크톱(sm+)=풀 푸터, 모바일=compact 상시 노출.
              사업자 표기는 표시 의무라 모바일에서 화면 전체를 숨기면(이전 동작)
              컴플라이언스 리스크다. 주소 포함 풀 표기는 모바일에선 햄버거 메뉴
              (Drawer) 안에서 계속 노출된다. 모바일 compact 푸터는 채팅(고정 100dvh)
              라우트를 제외해야 sticky 입력 도크가 밀리지 않으므로 pathname 을 아는
              MobileLegalFooter(클라이언트)가 게이트한다. */}
          <Box visibleFrom="sm">
            <LegalNotice />
          </Box>
          <MobileLegalFooter />
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

import type { Metadata, Viewport } from 'next';
import type { ReactNode } from 'react';
import { LegalNotice } from '@/components/LegalNotice';
import { Providers } from '@/lib/providers';
import './globals.css';

export const metadata: Metadata = {
  title: {
    default: '집핀 (Jippin)',
    template: '%s · 집핀'
  },
  description: '비내력벽 철거 사전검토 AI 서비스',
  robots: { index: false, follow: false }
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#147A73'
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body className="flex min-h-full flex-col">
        <Providers>
          <main className="flex-1">{children}</main>
          <LegalNotice />
        </Providers>
      </body>
    </html>
  );
}

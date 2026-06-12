import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import './globals.css';
import { Geist } from "next/font/google";
import { cn } from "@/lib/utils";

const geist = Geist({subsets:['latin'],variable:'--font-sans'});

export const metadata: Metadata = {
  title: '집핀 관리자',
  robots: { index: false, follow: false },
  icons: {
    icon: [
      { url: '/favicon.ico', sizes: 'any' },
      { url: '/favicon.svg', type: 'image/svg+xml' },
      { url: '/favicon-96x96.png', type: 'image/png', sizes: '96x96' }
    ],
    apple: '/apple-touch-icon.png'
  },
  manifest: '/site.webmanifest'
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko" className={cn("font-sans", geist.variable)}>
      <body>{children}</body>
    </html>
  );
}

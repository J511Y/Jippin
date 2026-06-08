import type { ReactNode } from 'react';
import { SiteShell } from '@/components/SiteShell';

export default function AppShellLayout({ children }: { children: ReactNode }) {
  return <SiteShell>{children}</SiteShell>;
}

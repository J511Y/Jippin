import type { ReactNode } from 'react';
import { MobileShell } from '@/components/MobileShell';

export default function AppShellLayout({ children }: { children: ReactNode }) {
  return <MobileShell>{children}</MobileShell>;
}

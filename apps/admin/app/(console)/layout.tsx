import { LogOut } from 'lucide-react';
import Link from 'next/link';
import type { ReactNode } from 'react';

import { SidebarNav } from '@/components/console/sidebar-nav';
import { Button } from '@/components/ui/button';
import { Toaster } from '@/components/ui/sonner';
import { requireAdminUser } from '@/lib/auth';
import { createServerComponentClient } from '@/lib/supabase/server';

/**
 * 관리자 콘솔 셸 — 좌측 고정 사이드바 + 콘텐츠 영역 (CMP-DIRECT).
 * proxy 게이트와 별개로 레이아웃에서 requireAdminUser 이중 방어.
 */
export default async function ConsoleLayout({ children }: { children: ReactNode }) {
  const supabase = await createServerComponentClient();
  const {
    data: { user }
  } = await supabase.auth.getUser();
  const admin = requireAdminUser(user);

  return (
    <div className="flex min-h-screen">
      <aside className="bg-sidebar fixed inset-y-0 left-0 flex w-60 flex-col border-r">
        <div className="flex h-14 items-center border-b px-4">
          <Link href="/" className="flex items-center gap-2 text-sm font-semibold">
            <span className="bg-foreground text-background flex size-6 items-center justify-center rounded-md text-[13px] font-bold">
              집
            </span>
            집핀 관리자
          </Link>
        </div>
        <div className="flex-1 overflow-y-auto px-2 py-4">
          <SidebarNav />
        </div>
        <div className="border-t p-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-muted-foreground truncate text-xs" title={admin.email ?? ''}>
              {admin.email}
            </p>
            <form action="/auth/logout" method="post">
              <Button
                type="submit"
                variant="ghost"
                size="icon-sm"
                title="로그아웃"
                className="text-muted-foreground"
              >
                <LogOut className="size-4" />
              </Button>
            </form>
          </div>
        </div>
      </aside>
      <main className="ml-60 min-w-0 flex-1">
        <div className="mx-auto max-w-6xl px-8 py-8">{children}</div>
      </main>
      <Toaster position="bottom-right" />
    </div>
  );
}

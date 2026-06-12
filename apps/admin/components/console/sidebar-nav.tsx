'use client';

import { Images, LayoutDashboard, MessagesSquare, ScanSearch } from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { cn } from '@/lib/utils';

/**
 * 콘솔 사이드바 내비게이션 (CMP-DIRECT).
 * active 판정은 정확 일치 또는 하위 경로 prefix — `/leads-foo` 류 오매칭 방지.
 */

const SECTIONS: Array<{
  label: string;
  items: Array<{ href: string; title: string; icon: typeof LayoutDashboard }>;
}> = [
  {
    label: '개요',
    items: [{ href: '/', title: '대시보드', icon: LayoutDashboard }]
  },
  {
    label: '운영',
    items: [{ href: '/leads', title: '상담', icon: MessagesSquare }]
  },
  {
    label: '사전검토',
    items: [
      { href: '/sessions', title: '세션', icon: ScanSearch },
      { href: '/floorplans', title: '업로드 도면', icon: Images }
    ]
  }
];

function isActive(pathname: string, href: string): boolean {
  if (href === '/') return pathname === '/';
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function SidebarNav() {
  const pathname = usePathname();

  return (
    <nav className="flex flex-col gap-5">
      {SECTIONS.map((section) => (
        <div key={section.label}>
          <p className="text-muted-foreground mb-1.5 px-2 text-[11px] font-medium tracking-wide uppercase">
            {section.label}
          </p>
          <ul className="flex flex-col gap-0.5">
            {section.items.map((item) => {
              const Icon = item.icon;
              const active = isActive(pathname, item.href);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className={cn(
                      'flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors',
                      active
                        ? 'bg-secondary text-foreground font-medium'
                        : 'text-muted-foreground hover:bg-secondary/60 hover:text-foreground'
                    )}
                  >
                    <Icon className="size-4" strokeWidth={1.75} />
                    {item.title}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

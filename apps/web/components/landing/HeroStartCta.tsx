'use client';

import { Button, type ButtonProps } from '@mantine/core';
import Link from 'next/link';

/**
 * 랜딩 히어로 1차 액션(제품 기능 진입) 링크 버튼.
 *
 * Server Component(랜딩 page.tsx)에서 Mantine `component={Link}` 를 직접 쓰면
 * SSG prerender 가 깨지므로(LeadCtaButton 주석·CMP-DIRECT 회귀 사례), 이 'use client'
 * 경계 안에서 next/link 를 결합한다 — 내부 내비게이션은 component="a" 대신
 * 클라이언트 내비게이션(프리페치 포함)을 쓴다는 규칙을 RSC 에서도 지키기 위함.
 */
export function HeroStartCta({
  href,
  ...buttonProps
}: ButtonProps & { href: string }) {
  return <Button component={Link} href={href} {...buttonProps} />;
}

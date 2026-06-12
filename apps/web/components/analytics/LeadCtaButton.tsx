'use client';

import { Button, type ButtonProps } from '@mantine/core';
import Link from 'next/link';
import {
  leadsNewHref,
  trackLeadCtaClick,
  type LeadCtaId
} from '@/lib/analytics/lead-cta';

/**
 * `/leads/new` 인입 CTA 공용 버튼 (CMP-DIRECT).
 *
 * - href 에 인입 식별자(`cta=`)를 부착하고, 클릭 시 dataLayer `cta_click` 을 push 한다.
 * - Server Component 페이지에서도 그대로 import 해 쓰는 클라이언트 경계 컴포넌트다.
 *   `component={Link}` 는 Server Component 에서 직접 쓰면 SSG prerender 가 깨지므로
 *   (CMP-DIRECT 회귀 사례) 반드시 이 'use client' 경계 안에만 둔다.
 * - 클라이언트 내비게이션(Link)이라 클릭 push 가 페이지 언로드로 유실되지 않는다.
 */
export function LeadCtaButton({
  cta,
  fromSession,
  ...buttonProps
}: ButtonProps & {
  /** 인입 지점 식별자 — `lib/analytics/lead-cta.ts` 의 표 참고. */
  cta: LeadCtaId;
  /** 리포트 → 상담 전환 컨텍스트(기존 파라미터)와 공존시킬 때 전달. */
  fromSession?: string;
}) {
  return (
    <Button
      component={Link}
      href={leadsNewHref(cta, { fromSession })}
      onClick={() => trackLeadCtaClick(cta)}
      {...buttonProps}
    />
  );
}

'use client';

import { Button, createPolymorphicComponent, type ButtonProps } from '@mantine/core';
import { forwardRef, type ReactNode } from 'react';

export type CtaButtonProps = ButtonProps & { children: ReactNode };

/**
 * 전환 CTA 표준 버튼 (DESIGN.md 버튼 위계 §1).
 *
 * 상담·견적·다운로드 등 "전환" 액션 전용. 정본 brand.cta(#F26B4F) 배경에
 * autoContrast 가 brand.ctaFg(진갈색) 라벨을 얹어 WCAG AA 를 만족한다.
 * 규칙: 한 화면에 1회만. 제품 기능 진입(사전검토 시작 등)은 CtaButton 이 아니라
 * jippin filled(1차 액션)를 쓴다 — 코랄이 여러 곳에 보이면 전환 신호가 흐려진다.
 */
export const CtaButton = createPolymorphicComponent<'button', CtaButtonProps>(
  forwardRef<HTMLButtonElement, CtaButtonProps>(function CtaButton(
    { children, ...rest },
    ref
  ) {
    return (
      <Button
        ref={ref}
        color="coral"
        variant="filled"
        size="md"
        radius="md"
        fw={700}
        {...rest}
      >
        {children}
      </Button>
    );
  })
);

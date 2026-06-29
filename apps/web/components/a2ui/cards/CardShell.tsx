'use client';

/**
 * A2UI 카드 공통 프리미티브 (CMP-DIRECT).
 *
 * 네 카드(도면 요청·주소 후보·판단 요약·도면 확인)가 한 가족으로 보이도록 헤더
 * 패턴(아이콘 칩 + 작은 eyebrow + 제목)과 본문 들여쓰기·구분선을 공유한다. 색은
 * 전부 브랜드/상태 토큰(CSS 변수)만 쓰며, 카드별 강조색은 `accent` prop 으로 주입한다.
 *
 * 시각 스타일 자체는 globals.css 의 `.a2ui-card*` 블록이 소유한다. 본 컴포넌트는
 * 마크업 구조와 접근성(헤더 텍스트 연결)만 담당해 카드들이 일관되게 조립되게 한다.
 */

import type { CSSProperties, ReactNode } from 'react';

/** 카드 강조색 축 — 브랜드 보조(전문)와 상태색을 의미대로만 쓴다. */
export type CardAccent = 'blueprint' | 'primary' | 'success' | 'warning' | 'danger';

const ACCENT_VARS: Record<CardAccent, { accent: string; soft: string }> = {
  blueprint: {
    accent: 'var(--jippin-brand-professional)',
    soft: 'var(--mantine-color-blueprint-0)'
  },
  primary: {
    accent: 'var(--jippin-brand-primary)',
    soft: 'var(--mantine-color-jippin-0)'
  },
  success: {
    accent: 'var(--mantine-color-success-6)',
    soft: 'var(--mantine-color-success-0)'
  },
  warning: {
    accent: 'var(--mantine-color-warning-6)',
    soft: 'var(--mantine-color-warning-0)'
  },
  danger: {
    accent: 'var(--mantine-color-danger-6)',
    soft: 'var(--mantine-color-danger-0)'
  }
};

type AccentStyle = CSSProperties & {
  '--a2ui-accent': string;
  '--a2ui-accent-soft': string;
};

/** accent → CSS 변수 인라인 스타일. globals.css 의 `.a2ui-card` 가 이 변수를 읽는다. */
export function accentStyle(accent: CardAccent): AccentStyle {
  const { accent: a, soft } = ACCENT_VARS[accent];
  return { '--a2ui-accent': a, '--a2ui-accent-soft': soft };
}

export function CardHeader({
  icon,
  eyebrow,
  title,
  titleId
}: {
  icon: ReactNode;
  /** 작은 상단 라벨(카드 종류). 카드 목적을 한눈에. */
  eyebrow: string;
  /** 카드 1차 제목 — 지금 사용자가 무엇을 해야/봐야 하는가. */
  title: string;
  /** 제목 element id — 카드 컨테이너의 aria-labelledby 와 연결. */
  titleId?: string;
}) {
  return (
    <div className="a2ui-card__head">
      <span className="a2ui-card__icon" aria-hidden>
        {icon}
      </span>
      <span style={{ minWidth: 0 }}>
        <span className="a2ui-card__eyebrow">{eyebrow}</span>
        <span className="a2ui-card__title" id={titleId}>
          {title}
        </span>
      </span>
    </div>
  );
}

/** 헤더와 본문 사이 옅은 구분선. */
export function CardRule() {
  return <div className="a2ui-card__rule" aria-hidden />;
}

/**
 * 카드 프레임 — 보더·라운드·그림자·좌측 강조 레일을 가진 공통 표면.
 * `accent` 로 강조색 축을 정하고, 내부는 `a2ui-card__body` 패딩 안에 조립된다.
 */
export function CardShell({
  accent,
  labelledBy,
  children
}: {
  accent: CardAccent;
  /** 카드 제목 element id — figure 의 aria-labelledby 와 연결(스크린리더 맥락). */
  labelledBy?: string;
  children: ReactNode;
}) {
  return (
    <section
      className="a2ui-card"
      role="figure"
      aria-labelledby={labelledBy}
      aria-label={labelledBy ? undefined : 'A2UI 카드'}
      style={accentStyle(accent)}
    >
      <div className="a2ui-card__body">{children}</div>
    </section>
  );
}

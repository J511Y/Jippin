import {
  Anchor,
  Card,
  createTheme,
  InputWrapper,
  type CSSVariablesResolver,
  type MantineColorsTuple
} from '@mantine/core';

const jippin: MantineColorsTuple = [
  '#E7F5F4',
  '#D0ECE9',
  '#A8D8D4',
  '#7FC1BC',
  '#4EA49E',
  '#2D8F87',
  '#147A73',
  '#0F5F59',
  '#0B4844',
  '#073532'
];

const blueprint: MantineColorsTuple = [
  '#E8F0F7',
  '#D3E1EC',
  '#A9C2D6',
  '#7DA0BD',
  '#547FA3',
  '#33638A',
  '#153B5C',
  '#102F49',
  '#0C2338',
  '#071826'
];

// 코랄 램프는 primaryShade(6)가 정본 brand.cta(#F26B4F)를 정확히 선택하도록
// 6번 칸에 정본색을 둔다. 이전 램프는 6번이 #D85338 이라 color="coral" filled 가
// 정본과 다른 색으로 렌더되던 문제(감사 HIGH)가 있었다.
const coral: MantineColorsTuple = [
  '#FFF0EC',
  '#FFE0D8',
  '#FFC1B1',
  '#FFA087',
  '#FF9070',
  '#FA7D58',
  '#F26B4F',
  '#D85338',
  '#B8422B',
  '#943321'
];

const success: MantineColorsTuple = [
  '#E8F5EE',
  '#D1EBDD',
  '#A8D8BC',
  '#80C49C',
  '#58AD7B',
  '#31965D',
  '#1B7F46',
  '#156637',
  '#104D2A',
  '#0B351D'
];

const danger: MantineColorsTuple = [
  '#FBEAE8',
  '#F6D5D1',
  '#EDABA3',
  '#E17F74',
  '#D6584C',
  '#C0392B',
  '#A52F24',
  '#84261D',
  '#661D16',
  '#48140F'
];

const warning: MantineColorsTuple = [
  '#FFF3E0',
  '#FFE6BF',
  '#FFCF80',
  '#F5B247',
  '#D99015',
  '#B97600',
  '#995D00',
  '#7A4A00',
  '#5C3800',
  '#3D2500'
];

const info: MantineColorsTuple = [
  '#E8F1F5',
  '#D1E3EA',
  '#A7CBD7',
  '#7DB1C3',
  '#5599B0',
  '#337F98',
  '#1F6F8B',
  '#18576D',
  '#124252',
  '#0C2C37'
];

export const jippinTokens = {
  brand: {
    primary: '#147A73',
    primaryFg: '#FFFFFF',
    ink: '#0D1B2A',
    copy: '#48606A',
    surface: '#F7FBFA',
    surfaceAlt: '#FFFFFF',
    border: '#D9E3E1',
    cta: '#F26B4F',
    ctaFg: '#FFFFFF',
    professional: '#153B5C',
    professionalFg: '#FFFFFF',
    // 페이지 캔버스 — 흰 바탕 + 약한 제도(製圖) 격자 2중 그리드(도면 정체성).
    // 격자선은 Blueprint Navy(#153B5C) 알파 — 표면(카드·헤더)은 불투명이라
    // 격자는 여백에서만 보인다. COLOR_SYSTEM.md §2 brand.canvas 참조.
    canvas: '#FFFFFF',
    gridMinor: 'rgba(21, 59, 92, 0.05)',
    gridMajor: 'rgba(21, 59, 92, 0.085)'
  },
  status: {
    success: '#1B7F46',
    successSurface: '#E8F5EE',
    danger: '#C0392B',
    dangerSurface: '#FBEAE8',
    warning: '#995D00',
    warningSurface: '#FFF3E0',
    info: '#1F6F8B',
    infoSurface: '#E8F1F5'
  },
  notice: {
    legal: '#48606A'
  },
  // 비활성 입력 상태 토큰 (COLOR_SYSTEM.md §3.1). prefill 된 실제 데이터가 또렷이
  // 읽히도록 진한 텍스트색을 둔다 — 일반 비활성 텍스트(content.subtle)와 구분.
  form: {
    disabledSurface: '#F0F0F0',
    disabledText: '#1C1C1C'
  }
} as const;

export const jippinTheme = createTheme({
  activeClassName: 'mantine-active',
  // filled 버튼 라벨은 흰색(Mantine 기본). 코랄 CTA 도 흰 라벨을 쓴다 — 운영자
  // 결정(2026-07): 코랄 위 어두운 라벨이 채도 높은 배경에 묻혀 가독성이 떨어진다는
  // 판단으로 흰 라벨을 채택. 흰 on coral6 대비는 3.0:1(WCAG AA 4.5:1 미달)이라
  // autoContrast 를 끄고 흰 라벨을 명시적으로 유지한다. 대비를 함께 만족시키려면
  // 코랄 배경을 coral8 수준으로 낮춰야 하는데(브랜드 코랄 톤 변경) 별도 결정 사항.
  black: jippinTokens.brand.ink,
  colors: {
    blueprint,
    coral,
    danger,
    info,
    jippin,
    success,
    warning
  },
  defaultRadius: 'md',
  fontFamily:
    "'Pretendard Variable', 'Pretendard', -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', system-ui, 'Segoe UI', Roboto, sans-serif",
  fontFamilyMonospace:
    "ui-monospace, SFMono-Regular, 'Cascadia Code', 'Source Code Pro', Menlo, Consolas, monospace",
  // 본문 스케일 (TYPOGRAPHY.md §2 동기화): body=md 15px. 15px 토큰이 없어
  // 본문이 sm(14px)으로 도피하던 구조를 제거한다. caption=xs 13px, legal 은
  // CSS 변수 --jippin-fz-legal(12px)로 별도 제공.
  fontSizes: {
    xs: '0.8125rem',
    sm: '0.875rem',
    md: '0.9375rem',
    lg: '1.0625rem',
    xl: '1.25rem'
  },
  headings: {
    fontFamily: 'inherit',
    fontWeight: '600',
    // 페이지 타이틀(h1)~카드 타이틀(h4) 스케일 SSOT — TYPOGRAPHY.md §2 와 동기.
    // 모바일→데스크톱 clamp 로 페이지별 임의 clamp 발명을 종식한다.
    // 랜딩 히어로(hero)·판정 한 줄(display)은 CSS 변수
    // --jippin-fz-hero / --jippin-fz-display 를 사용한다(아래 resolver).
    sizes: {
      h1: { fontSize: 'clamp(1.375rem, 1.9vw, 1.625rem)', lineHeight: '1.4' },
      h2: { fontSize: 'clamp(1.125rem, 1.6vw, 1.25rem)', lineHeight: '1.45' },
      h3: { fontSize: '1.0625rem', lineHeight: '1.5' },
      h4: { fontSize: '0.9375rem', lineHeight: '1.5' }
    }
  },
  components: {
    // 본문 링크는 밑줄 기본 (COLOR_SYSTEM.md §6.2 — 색만으로 링크를 구분하지 않는다).
    Anchor: Anchor.extend({
      defaultProps: { underline: 'always' }
    }),
    // 표면 카드 기본값 SSOT — 라디우스(lg)·패딩(lg)·보더 컬러(브랜드 토큰) 고정.
    // 카드 내부 패딩이 md/lg/xl 로 갈라지고 Mantine 기본 보더(gray-3 #DEE2E6)와
    // 브랜드 보더(#D9E3E1)가 한 화면에 섞이던 문제를 막는다.
    Card: Card.extend({
      defaultProps: { radius: 'lg', padding: 'lg' },
      styles: {
        root: { borderColor: 'var(--jippin-brand-border)' }
      }
    }),
    // 입력 label–input 간격/크기 보정. Mantine 기본은 label margin 0 + 다소 큰 폰트라
    // 답답해 보인다. TextInput·Textarea·Select 등은 내부적으로 InputWrapper 로 label 을
    // 렌더하므로 본 오버라이드가 모든 입력에 전역 적용된다.
    InputWrapper: InputWrapper.extend({
      styles: {
        label: {
          marginBottom: '0.375rem',
          fontSize: '0.875rem'
        }
      }
    })
  },
  primaryColor: 'jippin',
  primaryShade: { light: 6, dark: 6 },
  white: '#FFFFFF'
});

export const jippinCssVariablesResolver: CSSVariablesResolver = () => ({
  variables: {
    '--jippin-brand-primary': jippinTokens.brand.primary,
    '--jippin-brand-primary-fg': jippinTokens.brand.primaryFg,
    '--jippin-brand-ink': jippinTokens.brand.ink,
    '--jippin-brand-copy': jippinTokens.brand.copy,
    '--jippin-brand-surface': jippinTokens.brand.surface,
    '--jippin-brand-surface-alt': jippinTokens.brand.surfaceAlt,
    '--jippin-brand-border': jippinTokens.brand.border,
    '--jippin-brand-cta': jippinTokens.brand.cta,
    '--jippin-brand-cta-fg': jippinTokens.brand.ctaFg,
    '--jippin-brand-professional': jippinTokens.brand.professional,
    '--jippin-brand-professional-fg': jippinTokens.brand.professionalFg,
    '--jippin-notice-legal': jippinTokens.notice.legal,
    '--jippin-form-disabled-surface': jippinTokens.form.disabledSurface,
    '--jippin-form-disabled-text': jippinTokens.form.disabledText,
    // 제도 격자 캔버스 토큰 — globals.css body 배경이 소비한다.
    '--jippin-grid-minor': jippinTokens.brand.gridMinor,
    '--jippin-grid-major': jippinTokens.brand.gridMajor,
    // 타입 스케일 확장 토큰 (TYPOGRAPHY.md §2): hero 는 마케팅 랜딩 전용 1토큰,
    // display 는 판정(결과) 한 줄 전용. 페이지별 임의 clamp 발명 금지.
    '--jippin-fz-hero': 'clamp(2rem, 4vw, 2.75rem)',
    '--jippin-fz-display': 'clamp(1.5rem, 2.6vw, 1.75rem)',
    '--jippin-fz-legal': '0.75rem',
    // mark 는 스케일에서 유일한 12px 미만 단계 — 15px 이상 라벨 옆 첨자(내비 BETA)
    // 전용, 문장·캡션·단독 라벨 금지 (TYPOGRAPHY.md §2.1, DESIGN.md §4.7 베타 표시).
    '--jippin-fz-mark': '0.625rem',
    // 랜딩 섹션 세로 패딩 공용 상수 — 3개 랜딩(홈·가격·사전검토)이 공유.
    '--jippin-section-py': 'clamp(3rem, 6vw, 5rem)'
  },
  light: {
    // 페이지 캔버스: 흰 바탕 (격자는 globals.css 의 body background-image).
    // 이전의 미문서화 회색(#F8F9FA)을 정본 brand.canvas 로 교체 (감사 HIGH).
    '--mantine-color-body': jippinTokens.brand.canvas,
    '--mantine-color-text': jippinTokens.brand.ink,
    '--mantine-color-dimmed': jippinTokens.brand.copy
  },
  dark: {}
});

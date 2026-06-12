import {
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

const coral: MantineColorsTuple = [
  '#FFF0EC',
  '#FFE0D8',
  '#FFC1B1',
  '#FFA087',
  '#FF8060',
  '#F26B4F',
  '#D85338',
  '#B8422B',
  '#943321',
  '#6F2619'
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
    ctaFg: '#1A0F0B',
    professional: '#153B5C',
    professionalFg: '#FFFFFF'
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
  headings: {
    fontFamily: 'inherit',
    fontWeight: '600',
    // 페이지 타이틀(h1)~카드 타이틀(h3) 스케일 SSOT. 페이지별 fz 오버라이드로
    // 18/22/24/28px 가 혼재하던 것을 본 스케일로 통일한다 (CMP-DIRECT UI 정비).
    sizes: {
      h1: { fontSize: '1.75rem', lineHeight: '2.375rem' },
      h2: { fontSize: '1.375rem', lineHeight: '1.875rem' },
      h3: { fontSize: '1.125rem', lineHeight: '1.625rem' },
      h4: { fontSize: '1rem', lineHeight: '1.5rem' }
    }
  },
  components: {
    // 표면 카드 기본값 SSOT — 라디우스(lg)와 보더 컬러(브랜드 토큰)를 고정한다.
    // Mantine 기본 보더(gray-3 #DEE2E6)와 브랜드 보더(#D9E3E1)가 한 화면에 섞여
    // 미묘하게 다른 두 회색 선이 보이던 문제를 막는다.
    Card: Card.extend({
      defaultProps: { radius: 'lg' },
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
    '--jippin-notice-legal': jippinTokens.notice.legal,
    '--jippin-form-disabled-surface': jippinTokens.form.disabledSurface,
    '--jippin-form-disabled-text': jippinTokens.form.disabledText
  },
  light: {
    // 앱 배경은 중립 라이트 그레이 (브랜드 틸 틴트 제거). 표면(카드)은 화이트로 대비.
    '--mantine-color-body': '#F8F9FA',
    '--mantine-color-text': jippinTokens.brand.ink,
    '--mantine-color-dimmed': jippinTokens.brand.copy
  },
  dark: {}
});

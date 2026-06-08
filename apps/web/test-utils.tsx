// 유닛 테스트용 공용 render — 앱과 동일하게 Mantine 테마 Provider 로 감싼다.
// 컴포넌트를 렌더하는 테스트는 '@testing-library/react' 대신 본 모듈에서 render 를 import 한다.
import { MantineProvider } from '@mantine/core';
import { render as rtlRender, type RenderOptions } from '@testing-library/react';
import type { ReactElement, ReactNode } from 'react';

import { jippinTheme } from '@/lib/mantine-theme';

function Providers({ children }: { children: ReactNode }) {
  return <MantineProvider theme={jippinTheme}>{children}</MantineProvider>;
}

function render(ui: ReactElement, options?: Omit<RenderOptions, 'wrapper'>) {
  return rtlRender(ui, { wrapper: Providers, ...options });
}

export * from '@testing-library/react';
export { render };

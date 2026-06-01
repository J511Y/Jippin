import { defineConfig } from 'vitest/config';
import path from 'node:path';

/**
 * Vitest 설정 (CMP-580).
 *
 * Next.js App Router Route Handler 단위 테스트만 대상 — 본 PR 범위는 R2/R10 어댑터 검증.
 * 실 Supabase / DB 의존 테스트는 별도 트랙 (E2E / Playwright) 으로 분리한다.
 */
export default defineConfig({
  resolve: {
    alias: {
      '@': path.resolve(__dirname, '.'),
      '@contracts': path.resolve(__dirname, '../../packages/contracts/ts'),
    },
  },
  test: {
    environment: 'node',
    include: ['**/*.test.ts', '**/*.test.tsx'],
    exclude: ['node_modules/**', '.next/**'],
    pool: 'forks',
  },
});

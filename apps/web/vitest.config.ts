import react from '@vitejs/plugin-react';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, '.'),
      '@contracts': path.resolve(__dirname, '../../packages/contracts/ts'),
    },
  },
  test: {
    environment: 'node',
    environmentMatchGlobs: [['**/*.test.tsx', 'jsdom']],
    include: ['**/*.test.ts', '**/*.test.tsx', '**/*.spec.ts'],
    exclude: ['node_modules/**', '.next/**'],
    pool: 'forks',
  },
});

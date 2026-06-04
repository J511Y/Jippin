'use client';

import { MantineProvider } from '@mantine/core';
import { ModalsProvider } from '@mantine/modals';
import { Notifications } from '@mantine/notifications';
import { QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { jippinCssVariablesResolver, jippinTheme } from '@/lib/mantine-theme';
import { getQueryClient } from '@/lib/query-client';

export function Providers({ children }: { children: ReactNode }) {
  const queryClient = getQueryClient();
  return (
    <QueryClientProvider client={queryClient}>
      <MantineProvider
        cssVariablesResolver={jippinCssVariablesResolver}
        defaultColorScheme="light"
        theme={jippinTheme}
      >
        <ModalsProvider>
          <Notifications position="top-right" />
          {children}
        </ModalsProvider>
      </MantineProvider>
    </QueryClientProvider>
  );
}

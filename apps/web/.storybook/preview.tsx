import type { Preview } from '@storybook/nextjs-vite';
import { MantineProvider } from '@mantine/core';
import { ModalsProvider } from '@mantine/modals';
import { Notifications } from '@mantine/notifications';
import { jippinCssVariablesResolver, jippinTheme } from '../lib/mantine-theme';
import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';
import '@mantine/dates/styles.css';
import '../app/globals.css';

const preview: Preview = {
  decorators: [
    (Story) => (
      <MantineProvider
        cssVariablesResolver={jippinCssVariablesResolver}
        defaultColorScheme="light"
        theme={jippinTheme}
      >
        <ModalsProvider>
          <Notifications position="top-right" />
          <Story />
        </ModalsProvider>
      </MantineProvider>
    )
  ],
  parameters: {
    a11y: {
      test: 'todo'
    },
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i
      }
    },
    docs: {
      toc: true
    },
    layout: 'centered',
    nextjs: {
      appDirectory: true
    }
  }
};

export default preview;

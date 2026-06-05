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
      // docs page 의 각 story preview 가 콘텐츠 높이에 맞춰 늘어나도록 한다.
      // 고정 높이일 때 긴 폼/카드가 잘리고 docs 본문 스크롤이 끊겨 보이는 문제를 막는다.
      story: {
        inline: true,
        iframeHeight: 'auto'
      },
      toc: true
    },
    layout: 'centered',
    nextjs: {
      appDirectory: true
    }
  }
};

export default preview;

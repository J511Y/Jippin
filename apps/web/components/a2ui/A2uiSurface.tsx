'use client';

/**
 * A2UI 서피스 — 에이전트가 보낸 UI 컴포넌트 1건을 json-render 로 렌더한다.
 *
 * 자체 `{kind,payload}` 레지스트리를 대체하는 정본 렌더러. `JSONUIProvider` 컨텍스트
 * 안에서 `<Renderer>` 로 카탈로그 컴포넌트만 안전하게 렌더한다(임의 HTML 불가).
 * 변환 불가/미등록이면 raw JSON 폴백으로 떨어뜨려 디버깅 가시성을 유지한다.
 *
 * 카드 프레임(보더·라운드·그림자·강조 레일)은 각 카드가 `CardShell` 로 직접 소유한다
 * — 카드별로 강조색(blueprint/상태색)이 다르기 때문. 따라서 서피스는 카탈로그 카드는
 * 그대로 통과시키고, JSON 폴백일 때만 차분한 Paper 래퍼를 씌운다. 카드의 인터랙션
 * (업로드/선택)은 카드 내부의 `useChatActions()`(상위 ChatActionsProvider)로 이어진다.
 */

import { Code, Paper, Stack, Text } from '@mantine/core';
import { JSONUIProvider, Renderer } from '@json-render/react';

import { toSpec } from './adapt';
import { a2uiRegistry } from './jsonrender';

function FallbackJson({ component }: { component: unknown }) {
  return (
    <Paper
      role="figure"
      aria-label="A2UI 컴포넌트"
      bg="var(--jippin-brand-surface-alt, #FFFFFF)"
      p="sm"
      radius="md"
      style={{ border: '1px solid var(--jippin-brand-border)' }}
    >
      <Stack gap={4}>
        <Text c="var(--jippin-brand-copy)" fw={600} size="xs">
          [A2UI]
        </Text>
        <Code block c="dimmed" fz="xs">
          {JSON.stringify(component, null, 2)}
        </Code>
      </Stack>
    </Paper>
  );
}

export function A2uiSurface({ component }: { component: unknown }) {
  const spec = toSpec(component);
  if (!spec) {
    return <FallbackJson component={component} />;
  }
  return (
    <JSONUIProvider registry={a2uiRegistry}>
      <Renderer spec={spec} registry={a2uiRegistry} />
    </JSONUIProvider>
  );
}

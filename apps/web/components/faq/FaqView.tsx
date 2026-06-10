'use client';

import {
  Accordion,
  Anchor,
  Box,
  Group,
  Stack,
  Text,
  Title,
  Typography
} from '@mantine/core';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import type { FaqGroup } from '@/lib/faq';

/**
 * 자주묻는질문 본문 — 카테고리별 섹션 + 아코디언 + 마크다운 답변.
 *
 * 서버 컴포넌트(`/faq`)에서 그룹 데이터를 받아 렌더한다. 답변은 마크다운이라
 * react-markdown(+remark-gfm)으로 렌더하고 Mantine `TypographyStylesProvider` 로
 * 링크·목록·이미지 등 기본 마크업에 스타일을 입힌다.
 */
export function FaqView({ groups }: { groups: FaqGroup[] }) {
  return (
    <Stack gap="xl">
      {/* 카테고리 빠른 이동 */}
      <Group gap="xs" wrap="wrap">
        {groups.map((group) => (
          <Anchor
            key={group.category}
            href={`#faq-${group.category}`}
            size="sm"
            fw={600}
            underline="never"
            c="var(--jippin-brand-primary)"
            style={{
              padding: '4px 12px',
              borderRadius: 'var(--mantine-radius-xl)',
              border: '1px solid var(--jippin-brand-border)'
            }}
          >
            {group.label}
          </Anchor>
        ))}
      </Group>

      {groups.map((group) => (
        <Stack key={group.category} gap="sm" id={`faq-${group.category}`}>
          <Title order={2} fz="1.25rem" style={{ scrollMarginTop: 80 }}>
            {group.label}
          </Title>
          <Accordion variant="separated" radius="md" multiple>
            {group.items.map((item) => (
              <Accordion.Item key={item.id} value={item.id}>
                <Accordion.Control>
                  <Text fw={600} style={{ wordBreak: 'keep-all' }}>
                    {item.question}
                  </Text>
                </Accordion.Control>
                <Accordion.Panel>
                  <Typography>
                    <Box
                      fz="sm"
                      c="var(--jippin-brand-copy)"
                      style={{ wordBreak: 'keep-all' }}
                    >
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {item.answer}
                      </ReactMarkdown>
                    </Box>
                  </Typography>
                </Accordion.Panel>
              </Accordion.Item>
            ))}
          </Accordion>
        </Stack>
      ))}
    </Stack>
  );
}

'use client';

import { Box, Typography } from '@mantine/core';
import ReactMarkdown from 'react-markdown';
import rehypeRaw from 'rehype-raw';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import remarkGfm from 'remark-gfm';

/**
 * FAQ 답변에 허용하는 HTML — rehype-sanitize 기본(GitHub 스타일) 허용 목록에
 * 표 셀 줄바꿈용 ``<br>``/``<small>`` 만 보탠다. 그 외 태그·속성(script, 이벤트
 * 핸들러 등)은 제거된다.
 */
const FAQ_SANITIZE_SCHEMA = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames ?? []), 'br', 'small']
};

/**
 * FAQ 답변 마크다운 렌더러 — 상세 페이지(`/faq/[faqId]`)가 사용한다.
 *
 * 답변에는 GFM 표·링크와 함께 인라인 HTML(`<br>`, `<small>`)이 들어올 수 있어
 * rehype-raw 로 파싱하되, Phase 3 관리자 편집 등 저장 경로를 통한 HTML 주입에
 * 대비해 rehype-sanitize 허용 목록으로 정화한 뒤 렌더한다.
 */
export function FaqAnswer({ markdown }: { markdown: string }) {
  return (
    <Typography>
      <Box
        className="faq-answer"
        fz="md"
        lh={1.7}
        c="var(--jippin-brand-copy)"
        style={{ wordBreak: 'keep-all' }}
      >
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeRaw, [rehypeSanitize, FAQ_SANITIZE_SCHEMA]]}
        >
          {markdown}
        </ReactMarkdown>
      </Box>
    </Typography>
  );
}

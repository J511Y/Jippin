'use client';

import { Box, Typography } from '@mantine/core';
import ReactMarkdown from 'react-markdown';
import rehypeRaw from 'rehype-raw';
import remarkGfm from 'remark-gfm';

/**
 * FAQ 답변 마크다운 렌더러 — 상세 페이지(`/faq/[faqId]`)가 사용한다.
 *
 * 답변에는 GFM 표·링크와 함께 표 셀 줄바꿈용 인라인 HTML(`<br>`, `<small>`)이
 * 들어올 수 있어 rehype-raw 를 켠다. 콘텐츠는 운영자가 관리하는 시드/관리자
 * 입력만 거치므로(외부 입력 아님) raw HTML 허용이 안전하다.
 */
export function FaqAnswer({ markdown }: { markdown: string }) {
  return (
    <Typography>
      <Box
        fz="md"
        lh={1.7}
        c="var(--jippin-brand-copy)"
        style={{ wordBreak: 'keep-all' }}
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
          {markdown}
        </ReactMarkdown>
      </Box>
    </Typography>
  );
}

'use client';

/**
 * 어시스턴트 메시지 마크다운 렌더러 (CMP-DIRECT 채팅 UX).
 *
 * `react-markdown` 으로 `**굵게**`·목록·링크·코드를 렌더한다. 보안상 raw HTML 은
 * 비활성(기본값) — `rehype-raw` 를 쓰지 않는다. 스타일은 `globals.css` 의
 * `.chat-markdown` 블록(브랜드 토큰)이 담당한다. 링크는 새 탭 + noopener 로 연다.
 */

import Markdown from 'react-markdown';
import type { ComponentProps } from 'react';

type AnchorProps = ComponentProps<'a'>;

export function ChatMarkdown({ content }: { content: string }) {
  return (
    <div className="chat-markdown">
      <Markdown
        components={{
          a: ({ href, children, ...rest }: AnchorProps) => (
            <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>
              {children}
            </a>
          )
        }}
      >
        {content}
      </Markdown>
    </div>
  );
}

'use client';

import { clsx } from 'clsx';
import type { ChatMessage } from '@/components/a2ui/types';
import { DynamicComponent } from '@/components/a2ui/DynamicComponent';

type Props = {
  messages: ChatMessage[];
  className?: string;
};

export function MessageList({ messages, className }: Props) {
  if (messages.length === 0) {
    return (
      <div
        className={clsx(
          'flex h-full items-center justify-center text-sm text-slate-400',
          className
        )}
      >
        대화를 시작해 주세요.
      </div>
    );
  }

  return (
    <ol
      data-testid="a2ui-message-list"
      className={clsx('flex flex-col gap-3', className)}
    >
      {messages.map((message) => (
        <li
          key={message.id}
          className={clsx(
            'rounded-lg px-3 py-2 text-sm',
            message.role === 'user'
              ? 'self-end bg-brand text-brand-fg'
              : 'self-start bg-slate-100 text-slate-900'
          )}
        >
          <div className="whitespace-pre-wrap">{message.content}</div>
          {message.dynamic ? (
            <div className="mt-2">
              <DynamicComponent spec={message.dynamic} />
            </div>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

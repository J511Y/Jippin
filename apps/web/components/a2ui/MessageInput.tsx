'use client';

import { useState, type FormEvent } from 'react';
import { clsx } from 'clsx';

type Props = {
  onSubmit: (text: string) => void | Promise<void>;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
};

export function MessageInput({
  onSubmit,
  disabled,
  placeholder = '메시지를 입력하세요…',
  className
}: Props) {
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || busy || disabled) return;
    setBusy(true);
    try {
      await onSubmit(trimmed);
      setValue('');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      data-testid="a2ui-message-input"
      className={clsx('flex items-center gap-2', className)}
    >
      <label htmlFor="a2ui-input" className="sr-only">
        메시지 입력
      </label>
      <input
        id="a2ui-input"
        type="text"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder={placeholder}
        disabled={disabled || busy}
        className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none"
        autoComplete="off"
      />
      <button
        type="submit"
        disabled={disabled || busy || value.trim().length === 0}
        className="rounded-md bg-brand px-3 py-2 text-sm font-medium text-brand-fg disabled:opacity-50"
      >
        보내기
      </button>
    </form>
  );
}

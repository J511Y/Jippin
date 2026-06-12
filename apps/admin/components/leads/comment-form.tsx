'use client';

import { useRouter } from 'next/navigation';
import { useState, useTransition, type FormEvent } from 'react';
import { toast } from 'sonner';

import { addLeadComment } from '@/app/(console)/leads/actions';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';

/** 상담 댓글 작성 폼 (CMP-DIRECT). */
export function CommentForm({ leadId }: { leadId: string }) {
  const router = useRouter();
  const [body, setBody] = useState('');
  const [pending, startTransition] = useTransition();

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = body.trim();
    if (!trimmed) return;
    startTransition(async () => {
      const result = await addLeadComment(leadId, trimmed);
      if (!result.ok) {
        toast.error(result.error ?? '댓글 작성에 실패했습니다.');
        return;
      }
      setBody('');
      router.refresh();
    });
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-2">
      <Textarea
        value={body}
        onChange={(event) => setBody(event.target.value)}
        placeholder="운영 메모를 남겨주세요 (고객에게 노출되지 않습니다)"
        rows={3}
        maxLength={4000}
      />
      <div className="flex justify-end">
        <Button type="submit" size="sm" disabled={pending || !body.trim()}>
          {pending ? '작성 중…' : '댓글 작성'}
        </Button>
      </div>
    </form>
  );
}

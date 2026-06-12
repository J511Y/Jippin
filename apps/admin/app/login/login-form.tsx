'use client';

import { useState, type CSSProperties, type FormEvent } from 'react';

/**
 * 관리자 로그인 폼 (CMP-DIRECT).
 *
 * 비밀번호는 서버측 Route Handler(`/auth/login`)로만 전송하고 클라이언트
 * 스토리지에 남기지 않는다 (apps/web password-login 과 동일 원칙).
 */

const inputStyle: CSSProperties = {
  width: '100%',
  padding: '10px 12px',
  fontSize: 15,
  border: '1px solid #d4d7dc',
  borderRadius: 8
};

export function LoginForm({ next }: { next?: string }) {
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);

    const form = new FormData(event.currentTarget);
    try {
      const res = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: form.get('email'),
          password: form.get('password'),
          next
        })
      });
      const body = (await res.json()) as { redirect?: string; error?: string };
      if (!res.ok || !body.redirect) {
        setError(body.error ?? '로그인에 실패했습니다. 잠시 후 다시 시도해 주세요.');
        return;
      }
      window.location.assign(body.redirect);
    } catch {
      setError('로그인에 실패했습니다. 잠시 후 다시 시도해 주세요.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={onSubmit}
      style={{
        width: 360,
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
        padding: 32,
        background: '#fff',
        border: '1px solid #e3e5e9',
        borderRadius: 12
      }}
    >
      <h1 style={{ margin: 0, fontSize: 20 }}>집핀 관리자</h1>
      <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 13 }}>
        이메일
        <input name="email" type="email" autoComplete="username" required style={inputStyle} />
      </label>
      <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 13 }}>
        비밀번호
        <input
          name="password"
          type="password"
          autoComplete="current-password"
          required
          style={inputStyle}
        />
      </label>
      {error ? <p style={{ margin: 0, fontSize: 13, color: '#c92a2a' }}>{error}</p> : null}
      <button
        type="submit"
        disabled={submitting}
        style={{
          padding: '10px 12px',
          fontSize: 15,
          fontWeight: 600,
          color: '#fff',
          background: submitting ? '#868e96' : '#1a1c1f',
          border: 'none',
          borderRadius: 8,
          cursor: submitting ? 'default' : 'pointer'
        }}
      >
        {submitting ? '로그인 중…' : '로그인'}
      </button>
    </form>
  );
}

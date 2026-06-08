'use client';

import { useEffect } from 'react';

/**
 * 최종 폴백 경계. 루트 레이아웃(`app/layout.tsx`)·Providers 자체에서 난 에러를 잡는다.
 * 이 컴포넌트는 루트 레이아웃을 통째로 대체하므로 자체 `<html>/<body>` 를 렌더해야 하고,
 * MantineProvider 바깥이라 브랜드 토큰을 쓸 수 없어 인라인 스타일로 자립시킨다.
 *
 * 일반 페이지/데이터 에러는 `app/error.tsx` 가 먼저 잡으므로, 여기까지 오는 경우는 드물다.
 */

const BRAND_PRIMARY = '#147A73';

export default function GlobalError({
  error,
  reset
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('[global-error]', error);
  }, [error]);

  return (
    <html lang="ko">
      <body
        style={{
          margin: 0,
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '24px',
          background: '#F8F9FA',
          fontFamily:
            "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif",
          color: '#1A1B1E'
        }}
      >
        <div
          style={{
            maxWidth: 420,
            width: '100%',
            textAlign: 'center',
            background: '#FFFFFF',
            border: '1px solid #E9ECEF',
            borderRadius: 16,
            padding: '40px 28px',
            boxShadow: '0 16px 40px -24px rgba(0,0,0,0.3)'
          }}
        >
          <h1 style={{ fontSize: 20, fontWeight: 700, margin: '0 0 8px', wordBreak: 'keep-all' }}>
            일시적인 오류가 발생했어요
          </h1>
          <p style={{ fontSize: 14, color: '#868E96', margin: '0 0 24px', wordBreak: 'keep-all' }}>
            페이지를 불러오는 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.
          </p>
          <button
            type="button"
            onClick={reset}
            style={{
              appearance: 'none',
              border: 'none',
              cursor: 'pointer',
              width: '100%',
              padding: '12px 16px',
              borderRadius: 8,
              background: BRAND_PRIMARY,
              color: '#FFFFFF',
              fontSize: 15,
              fontWeight: 600
            }}
          >
            다시 시도
          </button>
          {/* 의도적 하드 내비게이션: 깨진 React 트리를 전체 새로고침으로 폐기한다. */}
          {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
          <a
            href="/"
            style={{
              display: 'inline-block',
              marginTop: 12,
              fontSize: 13,
              color: BRAND_PRIMARY,
              textDecoration: 'none'
            }}
          >
            홈으로 가기
          </a>
        </div>
      </body>
    </html>
  );
}

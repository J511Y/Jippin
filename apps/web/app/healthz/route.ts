import { NextResponse } from 'next/server';

/**
 * BFF 헬스체크.
 *
 * - 본 핸들러는 Next.js 자체의 헬스 상태만 응답한다.
 *   백엔드(`apps/api`)의 `/healthz`는 별도로 호출자가 직접 점검하거나,
 *   추후 본 핸들러가 `NEXT_PUBLIC_API_BASE_URL`을 통해 위임 호출하도록 확장한다.
 * - ADR-0001 §2 / CMP-529 §검증.
 */
export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

type HealthResponse = {
  status: 'ok';
  service: 'jippin-web';
  timestamp: string;
};

export async function GET(): Promise<NextResponse<HealthResponse>> {
  return NextResponse.json(
    {
      status: 'ok',
      service: 'jippin-web',
      timestamp: new Date().toISOString()
    },
    { status: 200 }
  );
}

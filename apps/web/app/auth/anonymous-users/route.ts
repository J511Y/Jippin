import { NextResponse } from 'next/server';

export async function POST(): Promise<NextResponse> {
  return NextResponse.json(
    {
      error: {
        code: 'AUTH_LEGACY_FLOW_REMOVED',
        message:
          'Legacy anonymous user issuance was removed; use Supabase anonymous sign-in.',
      },
    },
    { status: 410 }
  );
}

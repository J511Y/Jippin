import Link from 'next/link';

/**
 * 소셜 OAuth 진입 스텁 (CMP-529).
 *
 * - 실제 OAuth 콜백 처리, PKCE 흐름, JWT 발급은 백엔드(`apps/api`)의 AUTH 모듈이 담당.
 * - 본 페이지는 클라이언트에서 백엔드의 `/auth/{provider}/start` 로 redirect 하는 트리거만 노출.
 * - 콜백 처리는 후속 [Frontend] 자식 이슈에서 추가 (`apps/web/app/(auth)/callback/route.ts`).
 */

const PROVIDERS = [
  { id: 'kakao', label: '카카오로 로그인' },
  { id: 'google', label: 'Google 로 로그인' }
] as const;

export const metadata = {
  title: '로그인'
};

export default function LoginPage() {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
  return (
    <section className="mx-auto flex max-w-md flex-col gap-6 px-6 py-20">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">집핀 로그인</h1>
        <p className="text-sm text-slate-600">
          소셜 OAuth 로 로그인하면 백엔드가 자체 JWT 를 발급합니다.
        </p>
      </header>
      <ul className="grid gap-2">
        {PROVIDERS.map((p) => (
          <li key={p.id}>
            <a
              href={`${apiBase}/auth/${p.id}/start`}
              className="block rounded-md border border-slate-300 px-4 py-3 text-center text-sm font-medium hover:bg-slate-50"
            >
              {p.label}
            </a>
          </li>
        ))}
      </ul>
      <p className="text-xs text-slate-500">
        <Link href="/" className="underline underline-offset-2">
          홈으로
        </Link>
      </p>
    </section>
  );
}

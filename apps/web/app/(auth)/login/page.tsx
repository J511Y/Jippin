import Link from 'next/link';

import { LoginButtons } from './login-buttons';

/**
 * 간편가입 로그인 페이지 (CMP-557, CMP-564).
 *
 * - 정책: 자체 가입 / 아이디 찾기 / 비밀번호 찾기 UI 는 제공하지 않는다.
 *   소셜 OAuth provider 3종(Kakao / Naver / Google) 만 노출한다.
 * - `/login?next=/app/foo` 형태로 들어오면 `next` 경로를 OAuth start 의 `return_url` 로 전달한다.
 */

export const metadata = {
  title: '로그인'
};

type LoginPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

function pickNext(value: string | string[] | undefined): string | null {
  if (Array.isArray(value)) {
    return value[0] ?? null;
  }
  return value ?? null;
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const resolved = (await searchParams) ?? {};
  const nextPath = pickNext(resolved.next);
  return (
    <section className="mx-auto flex max-w-md flex-col gap-6 px-6 py-20">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">집핀 간편가입</h1>
        <p className="text-sm text-slate-600">
          소셜 계정으로 1초 만에 시작하세요. 별도의 아이디 / 비밀번호는 없습니다.
        </p>
      </header>
      <LoginButtons nextPath={nextPath} />
      <p className="text-xs text-slate-500">
        <Link href="/" className="underline underline-offset-2">
          홈으로
        </Link>
      </p>
    </section>
  );
}

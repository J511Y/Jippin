import { LoginForm } from './login-form';

/**
 * 관리자 로그인 페이지 (CMP-DIRECT).
 *
 * proxy 게이트가 미인증 진입 시 `?next=<원래 경로>` 를 붙여 보낸다. 검증은
 * 서버측(auth/login Route Handler)의 safeNext 가 다시 수행하므로 여기서는 전달만 한다.
 */
export default async function LoginPage({
  searchParams
}: {
  searchParams: Promise<{ next?: string | string[] }>;
}) {
  const { next } = await searchParams;
  return (
    <main className="bg-secondary/40 flex min-h-screen items-center justify-center p-6">
      <LoginForm next={typeof next === 'string' ? next : undefined} />
    </main>
  );
}

import Link from 'next/link';

export const metadata = {
  title: '로그인 완료',
};

export default function AuthSuccessPage() {
  return (
    <main className="mx-auto flex max-w-md flex-col gap-6 px-6 py-20">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold text-slate-950">로그인이 완료되었습니다</h1>
        <p className="text-sm leading-6 text-slate-600">
          집핀 사전검토를 이어서 진행할 수 있습니다.
        </p>
      </header>
      <Link
        href="/"
        className="w-fit rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white"
      >
        홈으로 이동
      </Link>
    </main>
  );
}

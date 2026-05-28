import Link from 'next/link';

export default function HomePage() {
  return (
    <section className="mx-auto flex max-w-2xl flex-col gap-6 px-6 py-16">
      <header className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-widest text-brand">
          Jippin · MVP skeleton
        </p>
        <h1 className="text-3xl font-semibold">집핀 — 비내력벽 철거 사전검토</h1>
        <p className="text-sm text-slate-600">
          본 페이지는 CMP-529 이슈의 Next.js 16.2 LTS 골격입니다. 도면 업로드·채팅·오버레이는
          후속 자식 이슈에서 추가됩니다.
        </p>
      </header>

      <div className="grid gap-3 rounded-lg border border-slate-200 p-4 text-sm">
        <p>
          상태 확인:{' '}
          <Link
            href="/healthz"
            className="font-medium text-brand underline underline-offset-2"
          >
            /healthz
          </Link>
        </p>
        <p className="text-slate-500">
          백엔드 BFF 경유 호출은 <code>NEXT_PUBLIC_API_BASE_URL</code> 환경변수에 의존합니다.
        </p>
      </div>
    </section>
  );
}

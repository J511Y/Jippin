import { requireAdminUser } from '@/lib/auth';
import { createServerComponentClient } from '@/lib/supabase/server';

/**
 * 관리자 대시보드 플레이스홀더 (CMP-DIRECT).
 *
 * proxy 가 이미 게이트하지만, 호출 지점에서 requireAdminUser 로 한 번 더 방어한다.
 * 실제 관리 화면(리드/FAQ/사용자)은 후속 트랙에서 붙는다.
 */
export default async function DashboardPage() {
  const supabase = await createServerComponentClient();
  const {
    data: { user }
  } = await supabase.auth.getUser();
  const admin = requireAdminUser(user);

  return (
    <main style={{ maxWidth: 960, margin: '0 auto', padding: 32 }}>
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 24
        }}
      >
        <h1 style={{ margin: 0, fontSize: 22 }}>집핀 관리자</h1>
        <form action="/auth/logout" method="post" style={{ margin: 0 }}>
          <button
            type="submit"
            style={{
              padding: '8px 14px',
              fontSize: 13,
              background: '#fff',
              border: '1px solid #d4d7dc',
              borderRadius: 8,
              cursor: 'pointer'
            }}
          >
            로그아웃
          </button>
        </form>
      </header>
      <section
        style={{
          padding: 24,
          background: '#fff',
          border: '1px solid #e3e5e9',
          borderRadius: 12
        }}
      >
        <p style={{ margin: 0 }}>
          <strong>{admin.email}</strong> 계정으로 로그인했습니다. 관리 메뉴는 후속 작업에서
          추가됩니다.
        </p>
      </section>
    </main>
  );
}

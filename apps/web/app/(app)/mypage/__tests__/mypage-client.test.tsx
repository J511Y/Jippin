import { cleanup, render, screen } from '@/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const accountApiMocks = vi.hoisted(() => ({
  listMyLeads: vi.fn(() => Promise.resolve([])),
  listMyHomeChecks: vi.fn(() => Promise.resolve([]))
}));

const sessionApiMocks = vi.hoisted(() => ({
  syncExistingToken: vi.fn(() => Promise.resolve(true)),
  listSessions: vi.fn()
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/mypage',
  useRouter: () => ({ replace: vi.fn() })
}));

vi.mock('@/lib/auth/account-api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/auth/account-api')>();
  return {
    ...actual,
    listMyLeads: accountApiMocks.listMyLeads,
    listMyHomeChecks: accountApiMocks.listMyHomeChecks
  };
});

vi.mock('@/lib/sessions/api', () => ({
  syncExistingToken: sessionApiMocks.syncExistingToken,
  listSessions: sessionApiMocks.listSessions
}));

vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({
    auth: {
      getSession: vi.fn(() =>
        Promise.resolve({
          data: {
            session: {
              user: {
                email: 'member@example.com',
                created_at: '2026-08-01T00:00:00Z',
                user_metadata: { name: '회원' },
                app_metadata: { provider: 'kakao', providers: ['kakao'] }
              }
            }
          }
        })
      )
    }
  })
}));

import { MyPageClient } from '../mypage-client';

describe('마이페이지 사전검토 목록', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/mypage?tab=prechecks');
    sessionApiMocks.listSessions.mockResolvedValue([
      {
        id: 'session-1',
        user_id: 'user-1',
        status: 'collecting_info',
        address_id: 'address-1',
        address: {
          road_address: '서울특별시 영등포구 여의대방로 1',
          jibun_address: null,
          apartment_name: '집핀아파트',
          building_dong: '101',
          unit_ho: '1403'
        },
        selected_floorplan_asset_id: 'asset-1',
        judgment_schema: {},
        completion_decision: null,
        has_report: true,
        last_activity_at: '2026-09-03T09:10:00Z',
        expires_at: null,
        created_at: '2026-09-01T00:00:00Z',
        updated_at: '2026-09-03T09:10:00Z'
      }
    ]);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('주소·진행상태를 표시하고 클릭 시 기존 세션 상세로 이동한다', async () => {
    render(<MyPageClient />);

    const title = await screen.findByText('집핀아파트');
    const card = title.closest('a');

    expect(sessionApiMocks.syncExistingToken).toHaveBeenCalledOnce();
    expect(sessionApiMocks.listSessions).toHaveBeenCalledOnce();
    expect(screen.getByText('101동 1403호')).toBeDefined();
    expect(screen.getByText('결과 확인 가능')).toBeDefined();
    expect(card?.getAttribute('href')).toBe('/sessions/session-1');
  });
});

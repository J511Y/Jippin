import { cleanup, render, screen, waitFor } from '@/test-utils';
import { AxiosError } from 'axios';
import { afterEach, describe, expect, it, vi } from 'vitest';

const apiMocks = vi.hoisted(() => ({
  syncExistingToken: vi.fn(() => Promise.resolve(true)),
  getSessionReport: vi.fn(),
  getSession: vi.fn(),
  issueSessionReportPdf: vi.fn(),
  getFloorplanAssetSignedUrl: vi.fn(() => Promise.reject(new Error('no image')))
}));

vi.mock('next/navigation', () => ({
  useParams: () => ({ sessionId: 'sess-1' }),
  usePathname: () => '/sessions/sess-1/report',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() })
}));

vi.mock('@/lib/sessions/api', () => apiMocks);

vi.mock('@/lib/analytics/sessions-funnel', () => ({
  trackPrecheckReportView: vi.fn()
}));

vi.mock('@/components/analytics/LeadCtaButton', () => ({
  LeadCtaButton: ({ children }: { children: React.ReactNode }) => (
    <button type="button">{children}</button>
  )
}));

import SessionReportPage, { addressLineOf } from '../page';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const REPORT = {
  schema_version: '1.0.0',
  session_id: 'sess-1',
  status: 'report_ready',
  evaluated_at: '2026-06-29T03:00:00Z',
  address: {
    road_address: '서울특별시 강남구 테헤란로 101',
    apartment_name: '래미안아파트',
    building_dong: '103',
    unit_ho: '1201'
  },
  estimate: {
    items: [{ code: 'PERMIT', label: '행위허가 대행', amount_min: 330000 }],
    total_range: { min: 330000, max: 330000 },
    vat_included: true
  },
  rule_eval_result: {
    verdict: 'WARN',
    permit_required: true,
    user_message: '조건부로 가능해요.',
    required_facilities: [{ label: '방화판', measurement_basis: '90cm 이상' }],
    legal_basis: [{ statute: '공동주택관리법', article: '제35조', summary: '행위허가' }],
    additional_checks: ['관리규약 확인'],
    ruleset_version: '2018-775.v3'
  }
};

describe('addressLineOf', () => {
  it('도로명 + 단지 + 동/호 접미를 조립한다(PDF _address_line 과 동일 규칙)', () => {
    expect(addressLineOf(REPORT.address)).toBe(
      '서울특별시 강남구 테헤란로 101 래미안아파트 103동 1201호'
    );
    expect(addressLineOf(null)).toBeNull();
  });
});

describe('SessionReportPage (2026-09 재설계)', () => {
  it('결론 한 장: 판정 h1 · 주소 · 3행 요약 · 액션 2개 · 법적 근거 기본 펼침', async () => {
    apiMocks.getSessionReport.mockResolvedValueOnce(REPORT);
    apiMocks.getSession.mockResolvedValueOnce({
      selected_floorplan_asset_id: null,
      judgment_schema: { selected_walls: ['w1', 'w2'] }
    });
    render(<SessionReportPage />);

    const h1 = await screen.findByRole('heading', { level: 1 });
    expect(h1.textContent).toContain('조건부 가능');
    // 판정은 한 번만 — 옛 화면의 '판단 결과' 카드 중복 제거.
    expect(screen.getAllByText('조건부 가능')).toHaveLength(1);
    expect(screen.getByText('서울특별시 강남구 테헤란로 101 래미안아파트 103동 1201호')).toBeTruthy();
    expect(screen.getByText('2곳 선택')).toBeTruthy();
    expect(screen.getByText('필요')).toBeTruthy();
    expect(screen.getByText('1건')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'PDF 리포트 받기' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '전문가 상담 신청하기' })).toBeTruthy();
    // 근거는 결론과 같은 시야(기본 펼침).
    expect(screen.getByText('공동주택관리법 제35조')).toBeTruthy();
    expect(screen.getByText('관리규약 확인')).toBeTruthy();
    // 봉인 법적 고지.
    expect(screen.getByText(/AI 기반 사전 검토 시스템/)).toBeTruthy();
  });

  it('HOLD 판정은 행위허가를 미정으로 표기한다', async () => {
    apiMocks.getSessionReport.mockResolvedValueOnce({
      ...REPORT,
      rule_eval_result: { ...REPORT.rule_eval_result, verdict: 'HOLD', permit_required: true }
    });
    apiMocks.getSession.mockResolvedValueOnce({ selected_floorplan_asset_id: null, judgment_schema: {} });
    render(<SessionReportPage />);
    expect(await screen.findByText('미정 · 추가 확인 필요')).toBeTruthy();
  });

  it('DENY 판정에는 예상 견적 섹션을 싣지 않는다(PDF 게이팅과 동일)', async () => {
    apiMocks.getSessionReport.mockResolvedValueOnce({
      ...REPORT,
      rule_eval_result: { ...REPORT.rule_eval_result, verdict: 'DENY' }
    });
    apiMocks.getSession.mockResolvedValueOnce({ selected_floorplan_asset_id: null, judgment_schema: {} });
    render(<SessionReportPage />);
    await screen.findByRole('heading', { level: 1 });
    expect(screen.queryByText('예상 견적')).toBeNull();
  });

  it('REPORT_NOT_READY 면 대화로 돌아가기 안내를 보여준다', async () => {
    apiMocks.getSessionReport.mockRejectedValueOnce(
      new AxiosError('not ready', 'ERR_BAD_REQUEST', undefined, undefined, {
        status: 404,
        statusText: 'Not Found',
        headers: {},
        config: { headers: {} } as never,
        data: { error: { code: 'REPORT_NOT_READY', message: 'x' } }
      })
    );
    render(<SessionReportPage />);
    await waitFor(() => expect(screen.getByText('리포트가 아직 준비되지 않았어요')).toBeTruthy());
    expect(screen.getByRole('link', { name: '대화로 돌아가기' })).toBeTruthy();
  });
});

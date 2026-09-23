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

import SessionReportPage, { addressLineOf, sameVerdictSnapshot } from '../page';

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
    // 도로명에 단지명이 이미 있으면 반복하지 않는다(PDF _address_line 동일).
    expect(addressLineOf({ road_address: '서울 강남구 테헤란로 101 래미안아파트', apartment_name: '래미안아파트' })).toBe('서울 강남구 테헤란로 101 래미안아파트');
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

    // 페이지 h1 은 항상 '리포트' 정체성, 판정은 h2(display) — 실패/미준비 상태에서도 헤딩이 남는다.
    const h2 = await screen.findByRole('heading', { level: 2, name: /조건부 가능/ });
    expect(h2.textContent).toContain('조건부 가능');
    expect(screen.getByRole('heading', { level: 1, name: 'AI 사전검토 리포트' })).toBeTruthy();
    // 판정은 한 번만 — 옛 화면의 '판단 결과' 카드 중복 제거.
    expect(screen.getAllByText('조건부 가능')).toHaveLength(1);
    // PageHeader 부제: 판정 일시만(날짜 + 시각, '판정' 접미 없음).
    expect(screen.getByText('2026년 6월 29일 12:00')).toBeTruthy();
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
    await screen.findByRole('heading', { level: 2, name: /어려움/ });
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
    expect(screen.getByRole('heading', { level: 1, name: 'AI 사전검토 리포트' })).toBeTruthy();
  });

  it('일반 오류(네트워크·5xx)면 다시 시도와 대화로 돌아가기를 제공한다', async () => {
    apiMocks.getSessionReport.mockRejectedValueOnce(new Error('network down'));
    render(<SessionReportPage />);
    await waitFor(() => expect(screen.getByRole('button', { name: '다시 시도' })).toBeTruthy());
    expect(screen.getByRole('link', { name: '대화로 돌아가기' })).toBeTruthy();
    expect(screen.getByRole('heading', { level: 1, name: 'AI 사전검토 리포트' })).toBeTruthy();
  });
});

describe('sameVerdictSnapshot (리포트·세션 스냅샷 대조)', () => {
  it('evaluated_at 과 verdict_revision 이 같은 판정을 가리키면 통과(2ms 허용)', () => {
    const at = '2026-06-29T03:00:00.123Z';
    const rev = Date.parse(at);
    expect(sameVerdictSnapshot({ evaluated_at: at }, { has_report: true, verdict_revision: rev })).toBe(true);
    expect(sameVerdictSnapshot({ evaluated_at: at }, { has_report: true, verdict_revision: rev + 1 })).toBe(true);
  });
  it('세션이 더 새 판정(다른 리비전)이거나 판정이 지워졌으면 불일치', () => {
    const at = '2026-06-29T03:00:00Z';
    expect(
      sameVerdictSnapshot({ evaluated_at: at }, { has_report: true, verdict_revision: Date.parse(at) + 5000 })
    ).toBe(false);
    expect(sameVerdictSnapshot({ evaluated_at: at }, { has_report: false, verdict_revision: null })).toBe(false);
  });
  it('구 API(리비전 없음)는 대조 불가 → 통과', () => {
    expect(sameVerdictSnapshot({ evaluated_at: '2026-06-29T03:00:00Z' }, { has_report: true })).toBe(true);
  });
});

describe('리포트 스냅샷 재시도', () => {
  it('세션 리비전이 리포트와 어긋나면 리포트를 다시 읽고, 그래도 어긋나면 옛 결론 대신 갱신 안내를 보여준다', async () => {
    const stale = { ...REPORT, evaluated_at: '2026-06-29T03:00:00Z' };
    apiMocks.getSessionReport.mockResolvedValueOnce(stale).mockResolvedValueOnce(stale);
    apiMocks.getSession.mockResolvedValue({
      has_report: true,
      verdict_revision: Date.parse('2026-06-29T04:00:00Z'),
      selected_floorplan_asset_id: 'asset-1',
      judgment_schema: { selected_walls: ['w1'] }
    });
    render(<SessionReportPage />);
    await screen.findByText('판정이 방금 갱신됐어요');
    expect(apiMocks.getSessionReport).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('heading', { level: 2 })).toBeNull();
    expect(screen.getByRole('heading', { level: 1, name: 'AI 사전검토 리포트' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'PDF 리포트 받기' })).toBeNull();
    expect(screen.getByRole('button', { name: '최신 리포트 불러오기' })).toBeTruthy();
    apiMocks.getSession.mockReset();
  });

  it('세션 메타 조회가 실패하면 도면 구역을 조용히 빼지 않고 불러올 수 없음 상태를 보여준다', async () => {
    apiMocks.getSessionReport.mockResolvedValueOnce(REPORT);
    apiMocks.getSession.mockRejectedValueOnce(new Error('network'));
    render(<SessionReportPage />);
    await screen.findByRole('heading', { level: 2 });
    expect(screen.getByText('도면 이미지를 지금 불러올 수 없어요')).toBeTruthy();
    expect(screen.getByRole('button', { name: '다시 시도' })).toBeTruthy();
    // 선택 수도 0 을 사실처럼 말하지 않는다.
    expect(screen.getByText('불러올 수 없음')).toBeTruthy();
    expect(screen.queryByText('선택 정보 없음')).toBeNull();
  });
});

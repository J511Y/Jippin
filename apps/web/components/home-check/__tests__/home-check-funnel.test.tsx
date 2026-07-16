import { cleanup, fireEvent, render, screen, waitFor } from '@/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() })
}));

import { HomeCheckFunnel } from '../HomeCheckFunnel';
import type { AddressSearchResult } from '@/lib/leads/api';

afterEach(() => {
  cleanup();
});

const MOCK_RESULT: AddressSearchResult = {
  total_count: 1,
  page: 1,
  per_page: 10,
  items: [
    {
      road_addr: '서울특별시 영등포구 여의대방로43나길 25 (신길동, 삼환아파트)',
      road_addr_part1: '서울특별시 영등포구 여의대방로43나길 25',
      road_addr_part2: '(신길동, 삼환아파트)',
      jibun_addr: '서울특별시 영등포구 신길동 897-2',
      zip_no: '07360',
      bd_nm: '삼환아파트',
      si_nm: '서울특별시',
      sgg_nm: '영등포구',
      emd_nm: '신길동'
    }
  ]
};

function renderFunnel(
  searchAddressOverride: (keyword: string) => Promise<AddressSearchResult> = () =>
    Promise.resolve(MOCK_RESULT)
) {
  // onSubmitOverride 를 넘겨 워커 warm-up 등 실제 네트워크 경로를 전부 끊는다.
  return render(
    <HomeCheckFunnel
      searchAddressOverride={searchAddressOverride}
      onSubmitOverride={() => Promise.resolve()}
    />
  );
}

/** 검색 → 첫 결과 선택으로 동 스텝까지 진행하는 공통 헬퍼. */
async function goToDongStep() {
  const searchInput = screen.getByLabelText('도로명주소 검색어');
  fireEvent.change(searchInput, { target: { value: '여의대방로43나길 25' } });
  fireEvent.keyDown(searchInput, { key: 'Enter' });
  const item = await screen.findByText(/삼환아파트/);
  fireEvent.click(item);
  await screen.findByText('동이 어떻게 되나요?');
}

describe('HomeCheckFunnel — 인앱 주소 검색 (팝업 상세주소 화면 제거)', () => {
  it('주소 스텝은 검색 입력칸에 자동 포커스된다', () => {
    renderFunnel();
    const searchInput = screen.getByLabelText('도로명주소 검색어');
    expect(document.activeElement).toBe(searchInput);
  });

  it('엔터로 검색하고 결과를 선택하면 곧장 동 스텝으로 진행한다', async () => {
    renderFunnel();
    await goToDongStep();
    // 상세주소를 묻는 표면이 어디에도 없다 — 동·호는 전용 스텝이 전담한다.
    expect(screen.queryByText(/상세주소/)).toBeNull();
  });

  it('검색 프록시 실패 시 juso 팝업 폴백 버튼을 노출한다', async () => {
    renderFunnel(() => Promise.reject(new Error('JUSO_API_ERROR')));
    const searchInput = screen.getByLabelText('도로명주소 검색어');
    fireEvent.change(searchInput, { target: { value: '테헤란로 123' } });
    fireEvent.keyDown(searchInput, { key: 'Enter' });
    await screen.findByText('주소 검색 팝업으로 찾기');
  });
});

describe('HomeCheckFunnel — 동/호 입력 포커스·엔터 진행', () => {
  it('주소 선택 직후 동 입력칸에 자동 포커스된다', async () => {
    renderFunnel();
    await goToDongStep();
    await waitFor(() => {
      expect(document.activeElement).toBe(screen.getByLabelText('동'));
    });
  });

  it('동 입력 후 엔터를 치면 호 스텝으로 넘어가고 호 입력칸에 포커스된다', async () => {
    renderFunnel();
    await goToDongStep();
    const dongInput = screen.getByLabelText('동');
    fireEvent.change(dongInput, { target: { value: '104' } });
    fireEvent.keyDown(dongInput, { key: 'Enter' });
    await screen.findByText('우리 집은 몇 호인가요?');
    await waitFor(() => {
      expect(document.activeElement).toBe(screen.getByLabelText('호'));
    });
  });

  it('IME 조합 중 엔터(isComposing)로는 다음 스텝으로 넘어가지 않는다', async () => {
    renderFunnel();
    await goToDongStep();
    const dongInput = screen.getByLabelText('동');
    fireEvent.change(dongInput, { target: { value: '10' } });
    fireEvent.keyDown(dongInput, { key: 'Enter', isComposing: true });
    // 조합 확정 엔터는 무시 — 여전히 동 스텝.
    expect(screen.getByText('동이 어떻게 되나요?')).toBeDefined();
    expect(screen.queryByText('우리 집은 몇 호인가요?')).toBeNull();
  });
});

describe('HomeCheckFunnel — 동/호는 숫자만 받는다', () => {
  // 세움터 조회는 동/호를 숫자로 매칭한다 — 한글·영문·기호가 섞이면 매칭이 깨져 조회가
  // 실패하므로, 입력 시점에 걸러 숫자만 통과시킨다(붙여넣기 포함).
  it('동 입력의 한글·기호를 걸러 숫자만 남긴다', async () => {
    renderFunnel();
    await goToDongStep();
    const dongInput = screen.getByLabelText('동') as HTMLInputElement;
    fireEvent.change(dongInput, { target: { value: '가10-3동' } });
    expect(dongInput.value).toBe('103');
  });

  it('호 입력의 문자를 걸러 숫자만 남긴다', async () => {
    renderFunnel();
    await goToDongStep();
    const dongInput = screen.getByLabelText('동');
    fireEvent.change(dongInput, { target: { value: '103' } });
    fireEvent.keyDown(dongInput, { key: 'Enter' });
    const hoInput = (await screen.findByLabelText('호')) as HTMLInputElement;
    fireEvent.change(hoInput, { target: { value: '303호' } });
    expect(hoInput.value).toBe('303');
  });
});

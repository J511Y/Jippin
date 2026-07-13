'use client';

/**
 * 우리집 체크 UI/UX 미리보기 (개발용, 백엔드 불필요).
 *
 * 두 가지를 백엔드 없이 눈으로 확인한다:
 *   1) 입력 퍼널(HomeCheckFunnel) — 토스/삼쩜삼식 한 화면 한 질문 흐름을 mock 주소·mock
 *      제출로 클릭해 본다(실제 juso 팝업·네트워크 없음).
 *   2) 결과 리포트(HomeCheckReportView) — 5개 verdict 상태를 mock 리포트로 렌더한다.
 * 모바일 폭·라이트/다크도 함께 토글할 수 있다. 인증/Supabase 가 필요 없어 클라이언트 전용.
 *
 * 경로: /preview/home-check
 */

import {
  Box,
  Container,
  Group,
  SegmentedControl,
  Stack,
  Text,
  Title,
  useMantineColorScheme
} from '@mantine/core';
import { useState } from 'react';
import type { HomeCheckReport } from '@contracts/home-check';

import { HomeCheckFunnel } from '@/components/home-check/HomeCheckFunnel';
import { HomeCheckReportView } from '@/components/home-check/HomeCheckReportView';
import { VERDICT_META, type Verdict } from '@/lib/home-check/display';
import type { AddressSearchResult } from '@/lib/leads/api';

const DISCLAIMER =
  '본 결과는 건축물대장(전유부·표제부) 조회 시점 기준의 참고 정보예요. 최종 판단은 관할 행정청이나 전문가 확인이 필요해요.';

const BASE_ADDRESS = {
  road_addr: '서울특별시 강남구 테헤란로 123',
  jibun_addr: '역삼동 678-9',
  dong: '101',
  ho: '1502'
};

const BASE_EXCLUSIVE = {
  area_m2: 84.97,
  use_type: '공동주택(아파트)',
  structure: '철근콘크리트구조',
  floor: '15층'
};

const BASE_BUILDING = {
  main_use: '공동주택(아파트)',
  floors: '지하 2층 지상 20층',
  approval_date: '2005-08-11',
  permit_date: '2003-04-02',
  comm_unique_no: '1168010100-3-06780009'
};

const BASE_DOCS = [
  { kind: 'exclusive_part' as const, url: 'https://example.com/exclusive.pdf' },
  { kind: 'building_heading' as const, url: 'https://example.com/heading.pdf' }
];

/** 5개 verdict 상태를 자체 완결 mock 리포트로. HomeCheckReportView 만 렌더한다. */
const MOCK_REPORTS: Record<Verdict, HomeCheckReport> = {
  illegal: {
    signal: 'violation',
    violation: { is_violation: true, exclusive: true, heading: false, raw: '위반건축물' },
    address: BASE_ADDRESS,
    exclusive_part: BASE_EXCLUSIVE,
    building: BASE_BUILDING,
    change_history: [
      { date: '2005-08-11', reason: '신규 사용승인', source: 'heading' },
      { date: '2018-06-02', reason: '위반건축물 표시 (베란다 불법 증축)', source: 'exclusive' }
    ],
    extension_check: {
      verdict: 'violation',
      reason: '베란다 증축이 위반건축물로 등재돼 있고, 신고하신 확장도 적법 등재가 확인되지 않아요.',
      reported_areas: ['거실 발코니 확장'],
      matched_areas: [],
      unrecorded_areas: ['거실 발코니 확장']
    },
    documents: BASE_DOCS,
    caution_reasons: [],
    disclaimer: DISCLAIMER
  },

  unrecorded_ext: {
    signal: 'violation',
    violation: { is_violation: false, exclusive: false, heading: false, raw: null },
    address: BASE_ADDRESS,
    exclusive_part: BASE_EXCLUSIVE,
    building: BASE_BUILDING,
    change_history: [
      { date: '2005-08-11', reason: '신규 사용승인', source: 'heading' },
      { date: '2019-03-15', reason: '침실2 발코니 확장 (전유부 변동)', source: 'exclusive' }
    ],
    extension_check: {
      verdict: 'violation',
      reason: '침실2 확장은 2019-03-15 변동사항에 등재돼 있지만, 거실 발코니 확장은 대장 변동이력에서 확인되지 않아요.',
      reported_areas: ['거실 발코니 확장', '침실2 확장'],
      matched_areas: ['침실2 확장'],
      unrecorded_areas: ['거실 발코니 확장']
    },
    documents: BASE_DOCS,
    caution_reasons: [],
    disclaimer: DISCLAIMER
  },

  caution: {
    signal: 'caution',
    violation: { is_violation: false, exclusive: false, heading: false, raw: null },
    address: BASE_ADDRESS,
    exclusive_part: BASE_EXCLUSIVE,
    building: BASE_BUILDING,
    change_history: [
      { date: '2005-08-11', reason: '신규 사용승인', source: 'heading' },
      { date: '2016-11-20', reason: '용도변경 (근린생활시설 → 주택)', source: 'heading' }
    ],
    extension_check: {
      verdict: 'uncertain',
      reason: '다용도실 확장은 대장 변동사항 표현이 모호해 등재 여부를 단정하기 어려워요.',
      reported_areas: ['다용도실 확장'],
      matched_areas: [],
      unrecorded_areas: []
    },
    documents: BASE_DOCS,
    caution_reasons: [
      '전유부 기준 조회라 건물 전체(표제부) 위반표시는 별도 확인이 필요해요.',
      '용도변경 이력이 있어 현재 용도와 실제 사용이 일치하는지 확인이 필요해요.'
    ],
    disclaimer: DISCLAIMER
  },

  normal: {
    signal: 'normal',
    violation: { is_violation: false, exclusive: false, heading: false, raw: null },
    address: BASE_ADDRESS,
    exclusive_part: BASE_EXCLUSIVE,
    building: BASE_BUILDING,
    change_history: [
      { date: '2005-08-11', reason: '신규 사용승인', source: 'heading' },
      { date: '2019-03-15', reason: '발코니 확장 (전유부 변동)', source: 'exclusive' }
    ],
    extension_check: {
      verdict: 'legal',
      reason: '신고하신 발코니 확장이 2019-03-15 변동사항에 등재돼 있어요.',
      reported_areas: ['발코니 확장'],
      matched_areas: ['발코니 확장'],
      unrecorded_areas: []
    },
    documents: BASE_DOCS,
    caution_reasons: [],
    disclaimer: DISCLAIMER
  },

  not_checked: {
    signal: 'normal',
    violation: { is_violation: false, exclusive: false, heading: false, raw: null },
    address: BASE_ADDRESS,
    exclusive_part: BASE_EXCLUSIVE,
    building: BASE_BUILDING,
    change_history: [{ date: '2005-08-11', reason: '신규 사용승인', source: 'heading' }],
    extension_check: null,
    documents: BASE_DOCS,
    caution_reasons: [],
    disclaimer: DISCLAIMER
  }
};

const VERDICT_ORDER: Verdict[] = [
  'illegal',
  'unrecorded_ext',
  'caution',
  'normal',
  'not_checked'
];

/** 미리보기용 mock 주소 검색 — 실제 검색 API 없이 살짝 지연 후 고정 결과를 돌려준다. */
function mockSearchAddress(): Promise<AddressSearchResult> {
  const items: AddressSearchResult['items'] = [
    {
      road_addr: '서울특별시 강남구 테헤란로 123 (역삼동, 집핀타워)',
      road_addr_part1: '서울특별시 강남구 테헤란로 123',
      road_addr_part2: '(역삼동, 집핀타워)',
      jibun_addr: '서울특별시 강남구 역삼동 678-9',
      zip_no: '06133',
      bd_nm: '집핀타워',
      si_nm: '서울특별시',
      sgg_nm: '강남구',
      emd_nm: '역삼동'
    },
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
  ];
  return new Promise((resolve) => {
    setTimeout(
      () => resolve({ total_count: items.length, page: 1, per_page: 10, items }),
      450
    );
  });
}

/** 미리보기용 mock 제출 — 실제 네트워크/이동 없이 로딩 화면을 잠깐 보여 준 뒤 완료 처리. */
function mockSubmit(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 1800));
}

type PreviewMode = 'funnel' | 'report';

export default function HomeCheckPreviewPage() {
  const [mode, setMode] = useState<PreviewMode>('funnel');
  const [verdict, setVerdict] = useState<Verdict>('illegal');
  const [width, setWidth] = useState<'mobile' | 'full'>('mobile');
  const { colorScheme, setColorScheme } = useMantineColorScheme();

  const report = MOCK_REPORTS[verdict];
  const isMobile = width === 'mobile';

  return (
    <Container size="md" py="xl">
      <Stack gap="xl">
        <Stack gap="xs">
          <Title order={1} fz="h2">
            우리집 체크 · UI 미리보기
          </Title>
          <Text size="sm" c="dimmed" style={{ wordBreak: 'keep-all' }}>
            백엔드 없이 입력 퍼널과 결과 리포트를 확인하는 개발용 페이지예요. mock
            데이터로 렌더돼요.
          </Text>
        </Stack>

        {/* 컨트롤 바 */}
        <Stack gap="sm">
          <SegmentedControl
            value={mode}
            onChange={(v) => setMode(v as PreviewMode)}
            data={[
              { value: 'funnel', label: '입력 퍼널' },
              { value: 'report', label: '결과 리포트' }
            ]}
          />

          {mode === 'report' ? (
            <Box style={{ overflowX: 'auto' }}>
              <SegmentedControl
                value={verdict}
                onChange={(v) => setVerdict(v as Verdict)}
                data={VERDICT_ORDER.map((v) => ({
                  value: v,
                  label: `${VERDICT_META[v].emoji} ${VERDICT_META[v].label}`
                }))}
              />
            </Box>
          ) : (
            <Text size="xs" c="dimmed" style={{ wordBreak: 'keep-all' }}>
              주소 검색은 mock 주소로 대체돼요. 확장 여부에서 &lsquo;있어요&rsquo;를
              고르면 부위 선택 단계가 나오고, 제출하면 로딩 후 완료 화면이 떠요.
            </Text>
          )}

          <Group gap="md">
            <SegmentedControl
              size="xs"
              value={width}
              onChange={(v) => setWidth(v as 'mobile' | 'full')}
              data={[
                { value: 'mobile', label: '모바일 (390)' },
                { value: 'full', label: '전체 폭' }
              ]}
            />
            <SegmentedControl
              size="xs"
              value={colorScheme === 'dark' ? 'dark' : 'light'}
              onChange={(v) => setColorScheme(v as 'light' | 'dark')}
              data={[
                { value: 'light', label: '라이트' },
                { value: 'dark', label: '다크' }
              ]}
            />
          </Group>
        </Stack>

        {/* 렌더 무대 — 모바일이면 390px 로 감싸 실제 화면폭을 흉내낸다. */}
        <Box
          style={{
            maxWidth: isMobile ? 390 : '100%',
            marginInline: isMobile ? 'auto' : undefined,
            width: '100%',
            padding: 'var(--mantine-spacing-md)',
            border: '1px dashed var(--jippin-brand-border)',
            borderRadius: 'var(--mantine-radius-lg)',
            background: 'var(--mantine-color-body)'
          }}
        >
          {mode === 'funnel' ? (
            <HomeCheckFunnel
              searchAddressOverride={mockSearchAddress}
              onSubmitOverride={mockSubmit}
            />
          ) : (
            // verdict 를 key 로 줘 상태 전환 시 useId·내부 상태를 확실히 리셋.
            <HomeCheckReportView key={verdict} report={report} checkId="preview-mock" />
          )}
        </Box>
      </Stack>
    </Container>
  );
}

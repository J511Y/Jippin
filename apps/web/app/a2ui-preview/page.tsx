'use client';

// A2UI(json-render) 렌더 미리보기 — 카탈로그 컴포넌트가 어떻게 보이는지 확인용.
// A2uiSurface 가 json-render 엔진으로 (1) 네이티브 spec, (2) 레거시 {kind,payload}
// 둘 다 렌더하는지 보여 준다.
import { Badge, Container, Stack, Text, Title } from '@mantine/core';

import { A2uiSurface } from '@/components/a2ui';

// (1) json-render 네이티브 스펙 — 백엔드가 새로 방출할 포맷.
const NATIVE_SPECS: { label: string; component: Record<string, unknown> }[] = [
  {
    label: 'FloorplanRequest (native spec)',
    component: {
      root: 'fp',
      elements: {
        fp: {
          type: 'FloorplanRequest',
          props: { reason: '거실 벽이 내력벽인지 정확히 보려면 평면도가 필요해요.' }
        }
      }
    }
  },
  {
    label: 'AddressCandidates (native spec)',
    component: {
      root: 'addr',
      elements: {
        addr: {
          type: 'AddressCandidates',
          props: {
            candidates: [
              { id: '1', road_address: '서울 강남구 테헤란로 12', building_name: 'OO타워' },
              { id: '2', road_address: '서울 강남구 테헤란로 14', jibun_address: '역삼동 123-4' }
            ]
          }
        }
      }
    }
  },
  {
    label: 'JudgmentSummary (native spec)',
    component: {
      root: 'j',
      elements: {
        j: {
          type: 'JudgmentSummary',
          props: {
            decision: 'conditional',
            title: '조건부 철거 가능',
            summary: '거실 벽은 비내력벽 후보로 보여 철거 가능성이 있어요. 상부 구조 확인이 필요합니다.',
            risks: ['상부 보 위치 확인 필요', '관리사무소 동의 필요']
          }
        }
      }
    }
  }
];

// (2) 레거시 {kind,payload} — 어댑터가 spec 으로 변환해 렌더되어야 함.
const LEGACY: { label: string; component: Record<string, unknown> }[] = [
  {
    label: 'floorplan-confirm (legacy {kind,payload})',
    component: { kind: 'floorplan-confirm', payload: { selectedRegionId: '거실-북측벽', confidence: 0.91 } }
  },
  {
    label: 'judgment-summary (legacy {kind,payload})',
    component: {
      kind: 'judgment-summary',
      payload: { decision: 'needs_expert', title: '전문가 확인 권장', summary: '도면만으로 단정하기 어려워요.', risks: ['현장 실측 필요'] }
    }
  }
];

export default function A2uiPreviewPage() {
  return (
    <Container size="sm" py="xl">
      <Stack gap="lg">
        <Title order={2}>A2UI · json-render 렌더 검증</Title>
        <Badge color="jippin" variant="light" w="fit-content">
          @json-render/react 엔진
        </Badge>
        {[...NATIVE_SPECS, ...LEGACY].map((item) => (
          <Stack key={item.label} gap={4}>
            <Text size="sm" fw={600} c="dimmed">
              {item.label}
            </Text>
            <A2uiSurface component={item.component} />
          </Stack>
        ))}
      </Stack>
    </Container>
  );
}

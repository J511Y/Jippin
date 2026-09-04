'use client';

// A2UI(json-render) 렌더 미리보기 — 카탈로그 컴포넌트가 어떻게 보이는지 확인용.
// A2uiSurface 가 json-render 엔진으로 (1) 네이티브 spec, (2) 레거시 {kind,payload}
// 둘 다 렌더하는지 보여 준다.
import { Badge, Container, Stack, Text, Title } from '@mantine/core';

import { A2uiSurface } from '@/components/a2ui';
import { ChatActionsProvider, type ChatActions } from '@/components/agent/chat-actions';

// 미리보기용 스텁 액션 — 채팅 컨텍스트 밖에서는 카드가 "대화 화면에서…" 안내만 보여 주므로,
// `interactive` 로 표시한 항목만 이 스텁으로 감싸 실제 인터랙티브 상태(도면 드롭존 등)를
// 확인한다. 전송/조회는 no-op(세션 없음).
const PREVIEW_ACTIONS: ChatActions = {
  sessionId: 'preview',
  busy: false,
  sendMessage: () => {},
  selectedFloorplanAssetId: null
};

type PreviewItem = { label: string; component: Record<string, unknown>; interactive?: boolean };

// 오버레이 미리보기용 합성 평면도(1000x800). 미리보기엔 세션이 없어 실제 도면 이미지는
// 안 뜨고 폴리곤/범례/줌/선택 UI 만 확인된다(실서비스에선 서명 URL 로 도면 위에 겹친다).
const OVERLAY_REGIONS = [
  { region_id: 's1', class_name: 'space_living_room', polygon: [60, 60, 500, 60, 500, 400, 60, 400], score: 0.95 },
  { region_id: 's2', class_name: 'space_kitchen', polygon: [520, 60, 940, 60, 940, 400, 520, 400], score: 0.93 },
  { region_id: 's3', class_name: 'space_bedroom', polygon: [60, 420, 500, 420, 500, 740, 60, 740], score: 0.94 },
  { region_id: 's4', class_name: 'space_bathroom', polygon: [520, 420, 740, 420, 740, 740, 520, 740], score: 0.9 },
  { region_id: 's5', class_name: 'space_balcony', polygon: [740, 420, 940, 420, 940, 740, 740, 740], score: 0.92 },
  { region_id: 'w1', class_name: 'wall_reinforced_concrete', polygon: [40, 40, 960, 40, 960, 60, 40, 60], score: 0.7, requires_hitl: true },
  { region_id: 'w2', class_name: 'wall_reinforced_concrete', polygon: [40, 740, 960, 740, 960, 760, 40, 760], score: 0.68, requires_hitl: true },
  { region_id: 'w3', class_name: 'wall_reinforced_concrete', polygon: [40, 40, 60, 40, 60, 760, 40, 760], score: 0.66, requires_hitl: true },
  { region_id: 'w4', class_name: 'wall_reinforced_concrete', polygon: [940, 40, 960, 40, 960, 760, 940, 760], score: 0.69, requires_hitl: true },
  { region_id: 'w5', class_name: 'wall_nonbearing', polygon: [500, 60, 520, 60, 520, 400, 500, 400], score: 0.62, requires_hitl: true },
  { region_id: 'w6', class_name: 'wall_nonbearing', polygon: [60, 400, 500, 400, 500, 420, 60, 420], score: 0.6, requires_hitl: true },
  { region_id: 'w7', class_name: 'wall_other', polygon: [520, 400, 740, 400, 740, 420, 520, 420], score: 0.44, requires_hitl: true },
  { region_id: 'd1', class_name: 'door', polygon: [240, 400, 300, 400, 300, 420, 240, 420], score: 0.8 },
  { region_id: 'g1', class_name: 'window', polygon: [740, 740, 860, 740, 860, 760, 740, 760], score: 0.75 }
];

// (1) json-render 네이티브 스펙 — 백엔드가 새로 방출할 포맷.
const NATIVE_SPECS: PreviewItem[] = [
  {
    label: 'FloorplanOverlay (native spec) — 폴리곤 오버레이 + 비내력벽·미확정 벽 선택',
    component: {
      root: 'ov',
      elements: {
        ov: {
          type: 'FloorplanOverlay',
          // vocab_version 은 서버가 싣는 벽 어휘 판별자 — 없으면 카드가 v3 저장분으로
          // 보고 wall_other 를 비내력 후보로 되돌린다. 미리보기는 현행(v4) 기준.
          props: {
            asset_id: '',
            image: { width: 1000, height: 800 },
            vocab_version: 4,
            regions: OVERLAY_REGIONS
          }
        }
      }
    }
  },
  {
    // 하위호환 확인용 — vocab_version 이 없는 v3 저장분은 wall_other 를 초록 비내력
    // 후보로 되돌려 그린다(옛 세션을 다시 열었을 때 사용자가 본 의미 그대로).
    label: 'FloorplanOverlay (v3 저장분) — vocab_version 없음 → 옛 어휘로 렌더',
    component: {
      root: 'ov3',
      elements: {
        ov3: {
          type: 'FloorplanOverlay',
          props: {
            asset_id: '',
            image: { width: 1000, height: 800 },
            regions: OVERLAY_REGIONS
          }
        }
      }
    }
  },
  {
    // 비내력 후보가 0곳인 도면 — v4 는 판단 보류를 별도 클래스로 내므로 실제로 나온다.
    // 안내 문구가 없는 초록색을 가리키지 않고 회색 벽으로 유도하는지 확인하는 케이스.
    label: 'FloorplanOverlay (미확정 벽만) — 초록 후보 0곳일 때 안내 문구',
    component: {
      root: 'ovu',
      elements: {
        ovu: {
          type: 'FloorplanOverlay',
          props: {
            asset_id: '',
            image: { width: 1000, height: 800 },
            vocab_version: 4,
            regions: OVERLAY_REGIONS.filter((r) => r.class_name !== 'wall_nonbearing')
          }
        }
      }
    }
  },
  {
    // 내력벽만 잡힌 도면(#bearing-only-copy) — 선택 가능 영역·제출 버튼이 없으므로
    // 선택 지시 대신 상황 설명만 나오는지, 집계 라인이 내력벽 개수를 보여 주는지 확인.
    label: 'FloorplanOverlay (내력벽만) — 선택 가능 영역 0곳일 때 안내 문구',
    component: {
      root: 'ovb',
      elements: {
        ovb: {
          type: 'FloorplanOverlay',
          props: {
            asset_id: '',
            image: { width: 1000, height: 800 },
            vocab_version: 4,
            regions: OVERLAY_REGIONS.filter(
              (r) => r.class_name === 'wall_reinforced_concrete'
            )
          }
        }
      }
    }
  },
  {
    label: 'FloorplanRequest (native spec) — 드래그앤드롭 업로드 카드(인터랙티브 스텁)',
    interactive: true,
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
const LEGACY: PreviewItem[] = [
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
            {item.interactive ? (
              <ChatActionsProvider value={PREVIEW_ACTIONS}>
                <A2uiSurface component={item.component} />
              </ChatActionsProvider>
            ) : (
              <A2uiSurface component={item.component} />
            )}
          </Stack>
        ))}
      </Stack>
    </Container>
  );
}

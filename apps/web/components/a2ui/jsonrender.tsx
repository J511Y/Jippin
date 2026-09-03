'use client';

/**
 * json-render 카탈로그 + 레지스트리 (A2UI 렌더 엔진).
 *
 * 자체 `{kind,payload}` 레지스트리를 대체한다. 에이전트가 보내는 UI 를 json-render
 * (@json-render/react)의 카탈로그/`<Renderer>` 로 안전하게 렌더한다 — 임의 HTML 불가,
 * 카탈로그에 정의한 컴포넌트만 인스턴스화, props 는 Zod 로 검증.
 *
 * 컴포넌트 타입 이름은 a2ui.org 컨벤션(PascalCase)을 따른다(FloorplanRequest 등).
 * Zod 스키마는 관대하게(문자열/옵셔널) 둬 LLM 출력이 최대한 렌더되게 하고, 세부 정합·
 * 폴백은 각 카드 컴포넌트의 자체 정규화에 맡긴다.
 */

import { defineCatalog } from '@json-render/core';
import { defineRegistry, schema } from '@json-render/react';
import { z } from 'zod';

import {
  AddressCandidatesCard,
  type AddressCandidatesPayload
} from '@/components/a2ui/cards/AddressCandidatesCard';
import {
  ConsultationHandoffCard,
  type ConsultationHandoffPayload
} from '@/components/a2ui/cards/ConsultationHandoffCard';
import {
  FloorplanConfirmCard,
  type FloorplanConfirmPayload
} from '@/components/a2ui/cards/FloorplanConfirmCard';
import {
  FloorplanOverlayCard,
  type FloorplanOverlayPayload
} from '@/components/a2ui/cards/FloorplanOverlayCard';
import {
  FloorplanRequestCard,
  type FloorplanRequestPayload
} from '@/components/a2ui/cards/FloorplanRequestCard';
import {
  JudgmentSummaryCard,
  type JudgmentSummaryPayload
} from '@/components/a2ui/cards/JudgmentSummaryCard';

const addressCandidate = z.object({
  id: z.string(),
  road_address: z.string(),
  jibun_address: z.string().optional(),
  building_name: z.string().optional()
});

const overlayRegion = z.object({
  region_id: z.string(),
  class_name: z.string(),
  polygon: z.array(z.number()),
  bbox: z.array(z.number()).optional(),
  score: z.number().optional(),
  requires_hitl: z.boolean().optional()
});

export const a2uiCatalog = defineCatalog(schema, {
  components: {
    FloorplanRequest: {
      props: z.object({
        reason: z.string().optional(),
        // 카드 발행 시점의 selected_floorplan_asset_id(서버 스탬프). 카탈로그에 선언해야
        // Zod 가 strip 하지 않고 카드에 닿는다 — 재업로드 요청 카드가 "이 카드 이후 새
        // asset 이 붙었는가"를 판정하는 근거(#floorplan-request-prior-asset).
        prior_asset_id: z.string().nullable().optional()
      }),
      description:
        '도면(평면도) 업로드를 사용자에게 요청하는 카드. reason 에 왜 필요한지 한 문장. prior_asset_id 는 발행 시점에 이미 선택돼 있던 asset(서버 스탬프, 재업로드 판정용).'
    },
    AddressCandidates: {
      props: z.object({ candidates: z.array(addressCandidate) }),
      description: '주소 후보 목록을 사용자가 선택하도록 보여 주는 카드.'
    },
    JudgmentSummary: {
      props: z.object({
        decision: z.string(),
        title: z.string(),
        summary: z.string(),
        risks: z.array(z.string()).optional(),
        rule_backed: z.boolean().optional(),
        session_id: z.string().optional(),
        prefill_address: z.string().optional(),
        // 이 결과가 유래한 도면 asset(서버 스탬프) — 도면 교체 시 '이전 도면 기준'
        // 표시 + 상담 CTA 차단 근거(#judgment-asset-stamp). 카탈로그에 선언해야
        // Zod 가 strip 하지 않는다.
        asset_id: z.string().optional(),
        // 결과가 근거한 선택 지문(서버 스탬프, 정렬된 selected_walls|selected_windows) —
        // 같은 도면에서 벽/창호를 다시 골라 verdict 가 무효화되면 '이전 선택 기준'으로
        // 표시하고 CTA 를 막는 근거(#judgment-selection-stamp). 카탈로그 선언 필수.
        selection_key: z.string().optional()
      }),
      description:
        '최종 판단 요약 카드. decision: possible|conditional|not_possible|needs_expert. rule_backed=룰엔진 판정 기반 여부. asset_id=결과가 유래한 도면(교체 감지용). selection_key=결과가 근거한 선택 지문(재선택 감지용). 하단 상담 CTA(빠른 상담폼) 포함.'
    },
    FloorplanConfirm: {
      props: z.object({
        selectedRegionId: z.string().optional(),
        confidence: z.union([z.number(), z.string()]).optional()
      }),
      description: '도면 세그멘테이션 후보 영역 + 분석 신뢰도(0~1) 카드.'
    },
    FloorplanOverlay: {
      props: z.object({
        asset_id: z.string().optional(),
        image: z
          .object({ width: z.number(), height: z.number() })
          .partial()
          .optional(),
        crop: z
          .object({ x: z.number(), y: z.number(), w: z.number(), h: z.number() })
          .optional(),
        regions: z.array(overlayRegion).default([]),
        // 벽 어휘 버전(서버 주입). **카탈로그에 선언해 검증을 통과시켜야 한다** — 이 값이
        // 카드에 닿지 않으면 모든 v4 카드가 v3 저장분으로 오인돼 wall_other(미확정 벽)가
        // 초록 '비내력벽 후보'로 뒤집혀 그려진다. 없으면 v3(저장된 옛 카드)로 본다.
        vocab_version: z.number().optional(),
        // 재제공 카드(show_floorplan_overlay)의 머리말 — 분석 직후 카드에는 없고, 에이전트가
        // "다른/추가 벽을 골라 달라"며 같은 도면 카드를 다시 띄울 때만 실린다. 카탈로그에
        // 선언해야 Zod 가 strip 하지 않는다(#overlay-reshow).
        reason: z.string().optional()
      }),
      description:
        '도면 위에 AI 분석 영역(벽/공간)을 폴리곤 오버레이로 표시하고 비내력벽 후보를 선택받는 카드(OVERLAY). vocab_version=벽 어휘 버전(없으면 v3 저장분). reason=재제공 카드의 안내 문장(있으면 재선택 모드).'
    },
    ConsultationHandoff: {
      props: z.object({
        reason: z.string().optional(),
        prefill_address: z.string().optional(),
        from_session: z.string().optional()
      }),
      description:
        '사전검토가 리포트까지 못 가고 상담 전환(HOLD_OR_HANDOFF)될 때, 안내 + 상담 신청 폼을 인라인으로 보여 주는 카드.'
    }
  },
  // 카드 인터랙션은 useChatActions(상위 컨텍스트)로 처리하므로 json-render 액션은 없음.
  actions: {}
});

// props 는 카탈로그 Zod 로 이미 검증됐다 — 카드 payload 타입으로 좁혀 전달한다.
const { registry: a2uiRegistry } = defineRegistry(a2uiCatalog, {
  components: {
    FloorplanRequest: ({ props }) => (
      <FloorplanRequestCard payload={props as FloorplanRequestPayload} />
    ),
    AddressCandidates: ({ props }) => (
      <AddressCandidatesCard payload={props as AddressCandidatesPayload} />
    ),
    JudgmentSummary: ({ props }) => (
      <JudgmentSummaryCard payload={props as JudgmentSummaryPayload} />
    ),
    FloorplanConfirm: ({ props }) => (
      <FloorplanConfirmCard payload={props as FloorplanConfirmPayload} />
    ),
    FloorplanOverlay: ({ props }) => (
      <FloorplanOverlayCard payload={props as FloorplanOverlayPayload} />
    ),
    ConsultationHandoff: ({ props }) => (
      <ConsultationHandoffCard payload={props as ConsultationHandoffPayload} />
    )
  }
});

export { a2uiRegistry };

/** kind(자체 포맷) → json-render 컴포넌트 타입 매핑(하위호환 어댑터에서 사용). */
export const A2UI_TYPE_BY_KIND: Record<string, string> = {
  'floorplan-request': 'FloorplanRequest',
  'address-candidates': 'AddressCandidates',
  'judgment-summary': 'JudgmentSummary',
  'floorplan-confirm': 'FloorplanConfirm',
  'floorplan-overlay': 'FloorplanOverlay',
  'consultation-handoff': 'ConsultationHandoff'
};

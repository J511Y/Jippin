'use client';

/**
 * A2UI `FloorplanOverlay` 카드 — 도면 위 분석 영역 오버레이 + 비내력벽 선택 (CMP-DIRECT).
 *
 * 기능명세서 §2.5 OVERLAY-001/002, SDD §4.5 OVERLAY 모듈의 프론트 정본.
 * - OVERLAY-001: AI 분석 결과(폴리곤/클래스)를 평면도 위에 반투명 색상 + 레이블 + 범례로
 *   오버레이. SVG 기반(폴리곤=DOM 요소 → 클릭/키보드/접근성 용이, 의존성 0). 핀치/휠 줌·
 *   드래그/스와이프 팬. stroke 는 non-scaling 이라 줌 무관 일정 두께(149개에서도 안 뭉갬).
 * - OVERLAY-002: 비내력벽 후보(wall_nonbearing)와 창호(window)를 클릭/키보드로 단일·복수
 *   선택 → selected_walls/selected_windows 로 판단스키마에 기록. 창호는 거실-발코니 통합
 *   (경계 창호 철거) 검토용 — 외기 접촉 여부 판정은 에이전트(LLM)가 대화·도면 관찰로 내린다.
 *
 * 색·접근성: 클래스 색은 전부 CSS 토큰(`--floorplan-*`). "선택 가능/불가"를 색만이 아니라
 * **선 모양**(선택가능=점선 → 선택=흰 실선)과 **범례 라벨**(선택 가능/불가)로도 인코딩해
 * 적록색맹·오독을 방지한다(WCAG 1.4.1).
 *
 * 안전 어휘(모델 카드 + BRAND): '후보/추정/검토 필요'만, '철거 가능 확정/내력벽 확정' 금지.
 */

import { ActionIcon, Box, Button, Group, Loader, Stack, Text } from '@mantine/core';
import {
  IconCircleCheck,
  IconHammer,
  IconHandFinger,
  IconMinus,
  IconPhotoExclamation,
  IconPlus,
  IconVectorTriangle,
  IconZoomReset
} from '@tabler/icons-react';
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';

import { useChatActions } from '@/components/agent/chat-actions';
import {
  trackPrecheckOverlayView,
  trackPrecheckWallSelect
} from '@/lib/analytics/sessions-funnel';
import {
  getFloorplanAssetSignedUrl,
  getSession,
  updateSelectedWalls
} from '@/lib/sessions/api';

import { CardHeader, CardRule, CardShell } from './CardShell';

export type OverlayRegion = {
  region_id: string;
  class_name: string;
  polygon: number[];
  bbox?: number[];
  score?: number;
  requires_hitl?: boolean;
};

export type CropFrame = { x: number; y: number; w: number; h: number };

export type FloorplanOverlayPayload = {
  asset_id?: string;
  image?: { width?: number; height?: number };
  /** 검출 엔티티를 감싼 크롭 프레임(원본 픽셀). viewBox 로 써서 여백을 잘라낸다(MASK 대체). */
  crop?: CropFrame;
  regions?: OverlayRegion[];
};

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/** payload.regions 를 방어적으로 정규화 — polygon 이 짝수 좌표(>=6)인 것만 채택. */
function normalizeRegions(raw: unknown): OverlayRegion[] {
  if (!Array.isArray(raw)) return [];
  const out: OverlayRegion[] = [];
  for (const item of raw) {
    if (!isPlainObject(item)) continue;
    const poly = item.polygon;
    const cls = item.class_name;
    const rid = item.region_id;
    if (typeof cls !== 'string' || typeof rid !== 'string') continue;
    if (
      !Array.isArray(poly) ||
      poly.length < 6 ||
      poly.length % 2 !== 0 ||
      !poly.every((n) => typeof n === 'number' && Number.isFinite(n))
    ) {
      continue;
    }
    out.push({
      region_id: rid,
      class_name: cls,
      polygon: poly as number[],
      score: typeof item.score === 'number' ? item.score : undefined,
      requires_hitl: item.requires_hitl === true
    });
  }
  return out;
}

/** flat [x1,y1,...] → SVG points "x1,y1 x2,y2". */
function toPoints(poly: number[]): string {
  const parts: string[] = [];
  for (let i = 0; i + 1 < poly.length; i += 2) {
    parts.push(`${poly[i]},${poly[i + 1]}`);
  }
  return parts.join(' ');
}

/** 폴리곤 무게중심(좌표 평균) — 선택 핀을 꽂을 위치. */
function centroidOf(poly: number[]): { x: number; y: number } {
  let sx = 0;
  let sy = 0;
  let n = 0;
  for (let i = 0; i + 1 < poly.length; i += 2) {
    sx += poly[i] ?? 0;
    sy += poly[i + 1] ?? 0;
    n += 1;
  }
  return n > 0 ? { x: sx / n, y: sy / n } : { x: 0, y: 0 };
}

type ViewBox = { x: number; y: number; w: number; h: number };

const MIN_ZOOM = 1;
const MAX_ZOOM = 8;

export function FloorplanOverlayCard({ payload }: { payload: FloorplanOverlayPayload }) {
  const actions = useChatActions();
  const titleId = useId();
  const sessionId = actions?.sessionId;
  const assetId = typeof payload.asset_id === 'string' ? payload.asset_id : undefined;

  const regions = useMemo(() => normalizeRegions(payload.regions), [payload.regions]);

  // 원본 이미지 크기 — <image> 가 이 좌표계로 그려진다. payload.image 우선, 없으면
  // 폴리곤 bbox 로 추정.
  const imgDims = useMemo(() => {
    const w = payload.image?.width;
    const h = payload.image?.height;
    if (typeof w === 'number' && typeof h === 'number' && w > 0 && h > 0) {
      return { w, h };
    }
    let maxX = 1;
    let maxY = 1;
    for (const r of regions) {
      for (let i = 0; i + 1 < r.polygon.length; i += 2) {
        maxX = Math.max(maxX, r.polygon[i] ?? 0);
        maxY = Math.max(maxY, r.polygon[i + 1] ?? 0);
      }
    }
    return { w: Math.ceil(maxX), h: Math.ceil(maxY) };
  }, [payload.image, regions]);

  // 표시 프레임 — 검출 엔티티를 감싼 크롭(서버 계산). viewBox 로 써서 도면 외곽 여백
  // (치수·표제란)을 잘라낸 채 같은 비율로 확대 표시한다(MASK 대체). 좌표 변환은 없다 —
  // 이미지와 폴리곤이 같은 원본 좌표계라 viewBox 만 좁히면 둘 다 같은 비율로 커진다.
  const frame = useMemo<CropFrame>(() => {
    const c = payload.crop;
    if (
      isPlainObject(c) &&
      typeof c.x === 'number' &&
      typeof c.y === 'number' &&
      typeof c.w === 'number' &&
      typeof c.h === 'number' &&
      Number.isFinite(c.x) &&
      Number.isFinite(c.y) &&
      c.w > 0 &&
      c.h > 0
    ) {
      return { x: c.x, y: c.y, w: c.w, h: c.h };
    }
    return { x: 0, y: 0, w: imgDims.w, h: imgDims.h };
  }, [payload.crop, imgDims]);

  // 선택 대상은 비내력벽 후보(wall_nonbearing) + 미확정 벽(wall_other/wall_unknown) +
  // 창호(window) — 나머지 벽/공간은 도면 이미지에 이미 보이므로 겹치지 않는다(선택 대상이
  // 한눈에 또렷해진다). 미확정 벽도 철거 희망 대상일 수 있어 선택은 허용하되, 선택 시
  // 에이전트가 '확인 필요' 흐름을 탄다(내력 단정 금지). 창호는 거실-발코니 사이 경계
  // 창호 철거(공간 통합) 검토용으로 함께 노출한다 — 외창/내창 구분은 여기서 하지 않고
  // 에이전트가 판단한다(#window-boundary-llm).
  //
  // 비내력 후보군 = wall_nonbearing ∪ wall_other 지만 **신뢰 등급이 다르다**(모델 v4):
  // wall_nonbearing 은 전문가가 확정한 비내력 패턴, wall_other 는 도면만으로 판단을
  // 보류한 벽이다. 확정분만 초록(선택 권장)으로 두고 보류분은 회색으로 분리해, 사용자가
  // 무엇이 확실하고 무엇이 확인 대상인지 색으로 구분하게 한다. wall_unknown 은 v3 이하
  // 과거 세션 데이터 호환용으로 같은 회색에 묶는다.
  const wallRegions = useMemo(
    () => regions.filter((r) => r.class_name === 'wall_nonbearing'),
    [regions]
  );
  const uncertainWallRegions = useMemo(
    () =>
      regions.filter(
        (r) => r.class_name === 'wall_other' || r.class_name === 'wall_unknown'
      ),
    [regions]
  );
  const windowRegions = useMemo(
    () => regions.filter((r) => r.class_name === 'window'),
    [regions]
  );
  const selectableRegions = useMemo(
    () => [...wallRegions, ...uncertainWallRegions, ...windowRegions],
    [wallRegions, uncertainWallRegions, windowRegions]
  );
  const windowIds = useMemo(
    () => new Set(windowRegions.map((r) => r.region_id)),
    [windowRegions]
  );
  const uncertainWallIds = useMemo(
    () => new Set(uncertainWallRegions.map((r) => r.region_id)),
    [uncertainWallRegions]
  );

  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [imageFailed, setImageFailed] = useState(false);
  const [loading, setLoading] = useState<boolean>(() => Boolean(sessionId));
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const interactive = actions !== null;
  const streaming = actions?.busy ?? false;

  // 노출 분석 이벤트 — 카드가 처음 렌더될 때 1회. wall_nonbearing_count 는 비내력벽 지표
  // 정본이라 창호를 섞지 않고 window_count 로 따로 집계한다(#wall-metric-purity).
  const viewedRef = useRef(false);
  useEffect(() => {
    if (viewedRef.current) return;
    viewedRef.current = true;
    trackPrecheckOverlayView(
      wallRegions.length,
      windowRegions.length,
      uncertainWallRegions.length
    );
  }, [wallRegions.length, windowRegions.length, uncertainWallRegions.length]);

  // 표시용 서명 URL 발급 + 기존 선택 복원(judgment_schema.selected_walls/windows).
  useEffect(() => {
    if (!sessionId) return;
    let ignore = false;
    void (async () => {
      try {
        const [url, session] = await Promise.all([
          assetId
            ? getFloorplanAssetSignedUrl(sessionId, assetId).catch(() => null)
            : Promise.resolve(null),
          getSession(sessionId).catch(() => null)
        ]);
        if (ignore) return;
        if (url) setImageUrl(url);
        else setImageFailed(true);
        const prevWalls = session?.judgment_schema?.selected_walls;
        const prevWindows = session?.judgment_schema?.selected_windows;
        const restored = [
          ...(Array.isArray(prevWalls) ? prevWalls : []),
          ...(Array.isArray(prevWindows) ? prevWindows : [])
        ].filter((x): x is string => typeof x === 'string');
        if (restored.length > 0) {
          setSelected(new Set(restored));
          setSubmitted(true); // 이미 제출된 선택 복원.
        }
      } catch {
        if (!ignore) setImageFailed(true);
      } finally {
        if (!ignore) setLoading(false);
      }
    })();
    return () => {
      ignore = true;
    };
  }, [sessionId, assetId]);

  // 토글은 **로컬 상태만** 바꾼다(자동 저장 안 함) — 아래 '제출' 버튼으로 확정한다.
  const toggle = useCallback((regionId: string) => {
    setSubmitted(false);
    setSelected((cur) => {
      const next = new Set(cur);
      if (next.has(regionId)) next.delete(regionId);
      else next.add(regionId);
      return next;
    });
  }, []);

  const clearSelection = useCallback(() => {
    setSubmitted(false);
    setSelected(new Set());
  }, []);

  // 제출 — 선택한 비내력벽·창호를 철거 검토 대상으로 확정 + 대화로 이어 검토 요청.
  // 핵심: 도면 제출과 동일하게 **버튼을 누르면 user 메시지가 항상 발화**되어야 한다.
  // selected_walls/windows 영속은 best-effort 로(실패해도 메시지 발화는 막지 않는다 —
  // 영속 실패가 sendMessage 를 건너뛰게 하던 버그 수정).
  const submit = useCallback(async () => {
    if (!actions || selected.size === 0 || submitting || streaming) return;
    setSubmitting(true);
    try {
      const wallIds = [...selected].filter((id) => !windowIds.has(id));
      const winIds = [...selected].filter((id) => windowIds.has(id));
      if (sessionId) {
        try {
          await updateSelectedWalls(sessionId, wallIds, winIds);
        } catch {
          /* 영속 실패는 무시 — 메시지 발화로 흐름은 이어간다 */
        }
      }
      trackPrecheckWallSelect(selected.size);
      setSubmitted(true);
      // 선택 구성에 맞는 자연어 발화 — 창호가 섞이면 에이전트가 경계(외기/발코니-실)
      // 판단 플로우를 타도록 창호를, 미확정 벽이 섞이면 '확인 필요' 흐름을 타도록
      // 미확정 벽을 각각 명시한다(전부 '비내력벽'으로 뭉뚱그리지 않는다).
      const nonloadIds = wallIds.filter((id) => !uncertainWallIds.has(id));
      const uncertainIds = wallIds.filter((id) => uncertainWallIds.has(id));
      const parts: string[] = [];
      if (nonloadIds.length > 0) parts.push(`비내력벽 ${nonloadIds.length}곳`);
      if (uncertainIds.length > 0)
        parts.push(`구조가 아직 확인되지 않은 벽 ${uncertainIds.length}곳`);
      if (winIds.length > 0) parts.push(`창호 ${winIds.length}곳`);
      await actions.sendMessage(
        `도면에서 ${parts.join('과 ')}을 철거 검토 대상으로 골랐어요. 철거할 수 있는지 검토해 주세요.`
      );
    } finally {
      setSubmitting(false);
    }
  }, [actions, sessionId, selected, windowIds, uncertainWallIds, submitting, streaming]);

  const hasSelectable = selectableRegions.length > 0;
  const submitDisabled =
    selected.size === 0 || submitting || submitted || streaming || !interactive;
  const submitLabel = submitting
    ? '제출 중…'
    : submitted
      ? `철거 검토 요청을 보냈어요 · ${selected.size}곳`
      : selected.size > 0
        ? `선택한 ${selected.size}곳 철거 검토하기`
        : '철거할 벽이나 창호를 먼저 골라 주세요';

  return (
    <CardShell accent="blueprint" labelledBy={titleId}>
      <CardHeader
        icon={<IconVectorTriangle size={17} aria-hidden />}
        eyebrow="철거 대상 선택"
        title="철거할 벽·창호를 골라 제출해 주세요"
        titleId={titleId}
      />
      <CardRule />

      <Stack gap="sm">
        {/* 창호 안내는 실제로 창호가 검출된 도면에서만 — 없는 파란 영역을 찾게 하지 않는다. */}
        <Text size="sm" c="var(--jippin-brand-copy)" style={{ lineHeight: 1.55 }}>
          철거가 가능한 건 <b>비내력벽(초록)</b>이에요.{' '}
          {uncertainWallRegions.length > 0 ? (
            <>
              <b>회색 벽</b>은 도면만으로는 아직 구조를 확인하지 못한 벽이에요 — 골라
              주시면 추가 확인이 필요한 부분을 함께 안내해 드려요.{' '}
            </>
          ) : null}
          {windowRegions.length > 0 ? (
            <>
              거실과 발코니 사이 <b>창호(파랑)</b>를 철거해 공간을 합치는 것도 검토할 수
              있어요 — 단, 바깥 공기와 바로 닿는 바깥쪽 창은 철거할 수 없어요.{' '}
            </>
          ) : null}
          영역을 눌러 고른 뒤(여러 곳 가능) <b>제출</b> 버튼을 눌러 주세요. 표시는 AI 추정
          후보예요.
        </Text>

        {loading ? (
          <div
            className="fp-skeleton"
            style={{ aspectRatio: `${frame.w} / ${frame.h}` }}
            role="status"
            aria-label="도면을 불러오는 중"
          />
        ) : (
          <OverlayCanvas
            key={`${frame.x},${frame.y},${frame.w},${frame.h}:${selectableRegions.length}`}
            frame={frame}
            imgDims={imgDims}
            regions={selectableRegions}
            imageUrl={imageUrl}
            imageFailed={imageFailed}
            selected={selected}
            onToggle={toggle}
            onImageError={() => setImageFailed(true)}
          />
        )}

        <Group justify="space-between" wrap="nowrap" gap="xs">
          <Text size="xs" c="var(--jippin-brand-copy)">
            {hasSelectable
              ? [
                  wallRegions.length > 0 ? `비내력벽 후보 ${wallRegions.length}곳` : null,
                  uncertainWallRegions.length > 0
                    ? `미확정 벽 ${uncertainWallRegions.length}곳`
                    : null,
                  windowRegions.length > 0 ? `창호 ${windowRegions.length}곳` : null,
                  `선택 ${selected.size}곳`
                ]
                  .filter(Boolean)
                  .join(' · ')
              : '선택 가능한 비내력벽·창호가 없어요. 다른 도면이 필요할 수 있어요.'}
          </Text>
          {selected.size > 0 ? (
            // 터치 타깃 ≥44px (DESIGN.md §4.7) — 시각은 작게, 히트 영역만 확보.
            <Button
              variant="subtle"
              color="gray"
              size="xs"
              mih={44}
              onClick={clearSelection}
              disabled={submitting}
            >
              선택 해제
            </Button>
          ) : null}
        </Group>

        {hasSelectable ? (
          // 1차 액션(제품 기능 진입: 선택 제출) — jippin filled. coral 은 전환 CTA 전용.
          <Button
            color="jippin"
            size="md"
            radius="md"
            fullWidth
            disabled={submitDisabled}
            onClick={submit}
            leftSection={
              submitting ? (
                <Loader size={16} color="white" />
              ) : submitted ? (
                <IconCircleCheck size={18} />
              ) : (
                <IconHammer size={18} />
              )
            }
          >
            {submitLabel}
          </Button>
        ) : null}
      </Stack>
    </CardShell>
  );
}

/** SVG 오버레이 + 줌/팬. viewBox 를 조작해 휠/핀치 줌, 드래그/스와이프 팬을 지원한다.
 *
 * ``frame`` 은 표시 프레임(크롭 영역, 원본 좌표계), ``imgDims`` 는 이미지 자연 크기다.
 * 이미지는 (0,0,imgDims) 로 그대로 그리고 viewBox 만 frame 으로 좁혀, 도면 여백을 잘라낸
 * 채 이미지와 오버레이를 같은 비율로 확대 표시한다(MASK 대체 — 좌표 변환 없음). */
function OverlayCanvas({
  frame,
  imgDims,
  regions,
  imageUrl,
  imageFailed,
  selected,
  onToggle,
  onImageError
}: {
  frame: ViewBox;
  imgDims: { w: number; h: number };
  regions: OverlayRegion[];
  imageUrl: string | null;
  imageFailed: boolean;
  selected: Set<string>;
  onToggle: (regionId: string) => void;
  onImageError: () => void;
}) {
  // 부모가 frame/regions 변화 시 key 로 remount 하므로 view 초기값을 crop 프레임으로 두면
  // 충분하다. 줌/팬 클램프 경계도 이 프레임 기준이다(이미지 전체가 아니라 크롭 영역).
  const full: ViewBox = useMemo(
    () => ({ x: frame.x, y: frame.y, w: frame.w, h: frame.h }),
    [frame]
  );
  const [view, setView] = useState<ViewBox>(full);

  const svgRef = useRef<SVGSVGElement | null>(null);
  const pointers = useRef<Map<number, { x: number; y: number }>>(new Map());
  const pinchPrev = useRef<number | null>(null);
  const panMoved = useRef(false);

  // 진입 펄스 힌트(선택 가능 벽 강조) — 1회, 모션 비선호 시 CSS 가 생략.
  const [hint, setHint] = useState(true);
  useEffect(() => {
    const t = setTimeout(() => setHint(false), 2600);
    return () => clearTimeout(t);
  }, []);

  const zoom = full.w / view.w;

  const clampView = useCallback(
    (v: ViewBox): ViewBox => {
      const w = Math.min(full.w, Math.max(full.w / MAX_ZOOM, v.w));
      const h = w * (full.h / full.w);
      // 크롭 프레임 원점(full.x/full.y) 기준으로 클램프 — 0 이 아니라 프레임 안으로 가둔다.
      const x = Math.min(Math.max(full.x, v.x), full.x + full.w - w);
      const y = Math.min(Math.max(full.y, v.y), full.y + full.h - h);
      return { x, y, w, h };
    },
    [full]
  );

  const zoomAt = useCallback(
    (clientX: number, clientY: number, factor: number) => {
      setView((v) => {
        const rect = svgRef.current?.getBoundingClientRect();
        if (!rect) return v;
        const px = (clientX - rect.left) / rect.width;
        const py = (clientY - rect.top) / rect.height;
        const focusX = v.x + px * v.w;
        const focusY = v.y + py * v.h;
        const nextZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, (full.w / v.w) * factor));
        const nw = full.w / nextZoom;
        const nh = nw * (full.h / full.w);
        return clampView({ x: focusX - px * nw, y: focusY - py * nh, w: nw, h: nh });
      });
    },
    [clampView, full.h, full.w]
  );

  // 버튼 줌은 화면 중앙 기준(좌상단 기준이 부자연스럽다는 리뷰 반영).
  const zoomCenter = useCallback(
    (factor: number) => {
      const rect = svgRef.current?.getBoundingClientRect();
      if (!rect) return;
      zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, factor);
    },
    [zoomAt]
  );

  // 휠 줌은 네이티브 non-passive 리스너로 단다 — React 의 onWheel 은 passive 라
  // preventDefault 가 무시돼 부모(채팅 스크롤)가 함께 스크롤된다(#scroll-chain).
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const handler = (e: WheelEvent) => {
      e.preventDefault();
      zoomAt(e.clientX, e.clientY, e.deltaY < 0 ? 1.15 : 1 / 1.15);
    };
    el.addEventListener('wheel', handler, { passive: false });
    return () => el.removeEventListener('wheel', handler);
  }, [zoomAt]);

  const onPointerDown = useCallback((e: React.PointerEvent<SVGSVGElement>) => {
    (e.target as Element).setPointerCapture?.(e.pointerId);
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    panMoved.current = false;
    pinchPrev.current = null;
  }, []);

  const onPointerMove = useCallback(
    (e: React.PointerEvent<SVGSVGElement>) => {
      const pts = pointers.current;
      if (!pts.has(e.pointerId)) return;
      const prev = pts.get(e.pointerId)!;
      const dx = e.clientX - prev.x;
      const dy = e.clientY - prev.y;
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });

      if (pts.size >= 2) {
        const [a, b] = [...pts.values()];
        if (a && b) {
          const dist = Math.hypot(a.x - b.x, a.y - b.y);
          if (pinchPrev.current != null && pinchPrev.current > 0) {
            zoomAt((a.x + b.x) / 2, (a.y + b.y) / 2, dist / pinchPrev.current);
          }
          pinchPrev.current = dist;
        }
        panMoved.current = true;
        return;
      }
      if (Math.abs(dx) > 2 || Math.abs(dy) > 2) panMoved.current = true;
      setView((v) => {
        const rect = svgRef.current?.getBoundingClientRect();
        if (!rect) return v;
        return clampView({
          ...v,
          x: v.x - (dx / rect.width) * v.w,
          y: v.y - (dy / rect.height) * v.h
        });
      });
    },
    [clampView, zoomAt]
  );

  const onPointerUp = useCallback((e: React.PointerEvent<SVGSVGElement>) => {
    pointers.current.delete(e.pointerId);
    if (pointers.current.size < 2) pinchPrev.current = null;
  }, []);

  return (
    <Box
      className="fp-overlay"
      data-hint={hint ? '1' : '0'}
      style={{
        position: 'relative',
        borderRadius: 12,
        overflow: 'hidden',
        border: '1px solid var(--jippin-brand-border)',
        background: '#fff',
        // 줌/팬 제스처가 부모(채팅) 스크롤로 새지 않게 체이닝 차단.
        overscrollBehavior: 'contain',
        touchAction: 'none'
      }}
    >
      <svg
        ref={svgRef}
        viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
        role="img"
        aria-label="도면 분석 오버레이"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        style={{
          display: 'block',
          width: '100%',
          aspectRatio: `${full.w} / ${full.h}`,
          touchAction: 'none',
          cursor: zoom > 1 ? 'grab' : 'default',
          // 캔버스 배경은 흰 표면 — 옛 회색(#f8f9fa)은 격자 캔버스 위에서 회색 섬이 된다.
          background: '#ffffff'
        }}
      >
        {imageUrl && !imageFailed ? (
          <image
            href={imageUrl}
            x={0}
            y={0}
            width={imgDims.w}
            height={imgDims.h}
            preserveAspectRatio="xMidYMid meet"
            onError={onImageError}
          />
        ) : null}

        {regions.map((r) => {
          // 부모가 선택 가능 영역(wall_nonbearing 비내력벽 후보 + wall_other/wall_unknown
          // 미확정 벽 + window 창호)만 넘긴다.
          const isSel = selected.has(r.region_id);
          const isWindow = r.class_name === 'window';
          const isUncertainWall =
            r.class_name === 'wall_other' || r.class_name === 'wall_unknown';
          const color = isWindow
            ? 'var(--floorplan-window)'
            : isUncertainWall
              ? 'var(--floorplan-wall-uncertain)'
              : 'var(--floorplan-wall-nonload)';
          const kindLabel = isWindow
            ? '창호'
            : isUncertainWall
              ? '미확정 벽'
              : '비내력벽 후보';
          return (
            <polygon
              key={r.region_id}
              className="fp-poly fp-poly-selectable"
              data-selected={isSel ? '1' : '0'}
              points={toPoints(r.polygon)}
              vectorEffect="non-scaling-stroke"
              fill={color}
              fillOpacity={isSel ? 0.7 : 0.22}
              stroke={isSel ? '#ffffff' : color}
              strokeOpacity={0.95}
              strokeWidth={isSel ? 4 : 1.6}
              strokeDasharray={isSel ? undefined : '5 3'}
              tabIndex={0}
              role="button"
              aria-pressed={isSel}
              aria-label={`${kindLabel}, 누르면 철거 검토 대상으로 ${isSel ? '해제' : '선택'}`}
              onClick={() => {
                if (panMoved.current) return; // 팬 끝의 클릭은 무시(드래그/선택 구분).
                onToggle(r.region_id);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onToggle(r.region_id);
                }
              }}
            >
              <title>
                {isSel
                  ? '철거 검토 대상으로 선택됨 — 누르면 해제'
                  : `${kindLabel} — 누르면 철거 검토 대상으로 선택`}
              </title>
            </polygon>
          );
        })}

        {/* 선택된 벽에 핀을 꽂아 직관적으로 표시(색 변화만으로는 구분이 어려움).
            크기를 view.w 비율로 잡아 줌과 무관하게 화면상 일정 크기로 보이게 한다. */}
        {regions
          .filter((r) => selected.has(r.region_id))
          .map((r) => {
            const c = centroidOf(r.polygon);
            const r0 = (view.w * 0.045) / 2; // 핀 반지름(user 단위, 화면상 ~일정).
            return (
              <g
                key={`pin-${r.region_id}`}
                transform={`translate(${c.x} ${c.y})`}
                pointerEvents="none"
                aria-hidden
              >
                {/* 선택 마커는 Blueprint Navy — coral 은 전환 CTA 전용(마커 사용 금지). */}
                <path
                  d={`M 0 0 C ${-r0} ${-r0 * 1.3}, ${-r0} ${-r0 * 2.7}, 0 ${-r0 * 2.7} C ${r0} ${-r0 * 2.7}, ${r0} ${-r0 * 1.3}, 0 0 Z`}
                  fill="var(--jippin-brand-professional)"
                  stroke="#ffffff"
                  strokeWidth={r0 * 0.2}
                />
                <circle cx={0} cy={-r0 * 1.75} r={r0 * 0.5} fill="#ffffff" />
              </g>
            );
          })}
      </svg>

      {/* 줌 컨트롤 — 터치 타깃 ≥44px(DESIGN.md §4.7). lg 는 34px 라 미달, xl(44px) 사용. */}
      <Group gap={6} style={{ position: 'absolute', right: 8, bottom: 8 }} wrap="nowrap">
        <ActionIcon
          variant="default"
          size="xl"
          radius="md"
          aria-label="축소"
          onClick={() => zoomCenter(1 / 1.4)}
        >
          <IconMinus size={18} />
        </ActionIcon>
        <ActionIcon
          variant="default"
          size="xl"
          radius="md"
          aria-label="확대"
          onClick={() => zoomCenter(1.4)}
        >
          <IconPlus size={18} />
        </ActionIcon>
        <ActionIcon
          variant="default"
          size="xl"
          radius="md"
          aria-label="원래 크기로"
          onClick={() => setView(full)}
        >
          <IconZoomReset size={18} />
        </ActionIcon>
      </Group>

      {imageFailed ? (
        <Group
          gap={6}
          wrap="nowrap"
          style={{
            position: 'absolute',
            left: 8,
            top: 8,
            padding: '4px 8px',
            borderRadius: 8,
            background: 'rgba(255,255,255,0.92)'
          }}
        >
          <IconPhotoExclamation size={14} color="var(--mantine-color-warning-7)" />
          <Text size="11px" c="var(--jippin-brand-copy)">
            도면 이미지를 못 불러와 영역만 표시해요
          </Text>
        </Group>
      ) : (
        <Group
          gap={5}
          wrap="nowrap"
          aria-hidden
          style={{
            position: 'absolute',
            left: 8,
            top: 8,
            padding: '4px 8px',
            borderRadius: 8,
            background: 'rgba(255,255,255,0.85)'
          }}
        >
          <IconHandFinger size={13} color="var(--jippin-brand-professional)" />
          <Text size="11px" c="var(--jippin-brand-copy)">
            {/* 실제 검출된 클래스만 안내 — 없는 파란 창/회색 벽을 찾게 하지 않는다. */}
            {[
              regions.some((r) => r.class_name === 'wall_nonbearing')
                ? '초록 점선 벽'
                : null,
              regions.some(
                (r) => r.class_name === 'wall_other' || r.class_name === 'wall_unknown'
              )
                ? '회색 점선 벽'
                : null,
              regions.some((r) => r.class_name === 'window') ? '파란 점선 창' : null
            ]
              .filter(Boolean)
              .join('·') + '을 눌러 선택'}
          </Text>
        </Group>
      )}
    </Box>
  );
}
